import os
import re
import random
import uuid
import requests
from typing import Optional, Tuple
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import whisper
from pydub import AudioSegment
import json
from video_generator import VideoGenerator
import sys
import subprocess
from urllib.parse import urlparse
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError

# Load environment variables
load_dotenv()

# Constants and folders
UPLOAD_FOLDER = 'uploads'
TRANSCRIPTS_FOLDER = 'transcripts'
SEGMENTS_FOLDER = 'segments'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'aac', 'ogg'}

for folder in [UPLOAD_FOLDER, TRANSCRIPTS_FOLDER, SEGMENTS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID") or "ftDdhfYtmfGP0tFlBYA1"

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")


def upload_video_to_s3(video_path: str, filename: str) -> str:
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_DEFAULT_REGION
    )
    with open(video_path, "rb") as f:
        s3.put_object(Bucket=S3_BUCKET_NAME, Key=filename, Body=f, ContentType="video/mp4")
    return f"https://{S3_BUCKET_NAME}.s3.{AWS_DEFAULT_REGION}.amazonaws.com/{filename}"

# Whisper model cache
g_whisper_model = None
def get_whisper_model():
    global g_whisper_model
    if g_whisper_model is None:
        g_whisper_model = whisper.load_model("base")
    return g_whisper_model

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def download_audio_file(url):
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename or '.' not in filename:
            filename = f"audio_{hash(url) % 10000}.mp3"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return filename, filepath
    except Exception as e:
        raise Exception(f"Failed to download file: {str(e)}")

def convert_to_mp3(audio_path):
    try:
        audio = AudioSegment.from_file(audio_path)
        mp3_path = audio_path.rsplit('.', 1)[0] + '.mp3'
        audio.export(mp3_path, format='mp3')
        return mp3_path
    except Exception as e:
        raise Exception(f"Error converting audio: {str(e)}")

def transcribe_audio(audio_path):
    try:
        if not audio_path.lower().endswith('.mp3'):
            audio_path = convert_to_mp3(audio_path)
        model = get_whisper_model()
        result = model.transcribe(audio_path, word_timestamps=True)
        if result and 'segments' in result:
            sentence_segments = []
            for segment in result['segments']:
                sentence_segments.append({
                    'start': segment.get('start', 0),
                    'end': segment.get('end', 0),
                    'text': segment.get('text', '').strip()
                })
            word_segments = []
            for segment in result['segments']:
                if not isinstance(segment, dict):
                    continue
                if 'words' in segment and isinstance(segment['words'], list):
                    for word in segment['words']:
                        if isinstance(word, dict):
                            word_segments.append({
                                'start': word.get('start', 0),
                                'end': word.get('end', 0),
                                'text': word.get('word', '').strip()
                            })
            return sentence_segments, word_segments
        else:
            raise Exception("No transcript found")
    except Exception as e:
        raise Exception(f"Error transcribing audio: {str(e)}")

def create_audio_segments(sentence_segments, segment_duration=15):
    if not sentence_segments:
        return []
    total_duration = sentence_segments[-1]['end']
    segments = []
    segment_start = 0
    while segment_start < total_duration:
        segment_end = min(segment_start + segment_duration, total_duration)
        segment_text = ""
        for sentence in sentence_segments:
            sentence_start = sentence['start']
            sentence_end = sentence['end']
            if (sentence_start < segment_end and sentence_end > segment_start):
                if segment_text:
                    segment_text += " " + sentence['text']
                else:
                    segment_text = sentence['text']
        if segment_text.strip():
            segments.append({
                'start': segment_start,
                'end': segment_end,
                'text': segment_text.strip(),
                'sentences': [s for s in sentence_segments if s['start'] < segment_end and s['end'] > segment_start]
            })
        segment_start = segment_end
    return segments

def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    milliseconds = int((secs % 1) * 1000)
    secs = int(secs)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def create_srt_file(segments, output_path):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            idx = 1
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                text = segment.get('text', '')
                start = segment.get('start', 0)
                end = segment.get('end', 0)
                words = text.split() if isinstance(text, str) else []
                n = len(words)
                if n == 0:
                    continue
                total_time = end - start
                time_per_word = total_time / n if n > 0 else 0
                for i in range(0, n, 10):
                    chunk_words = words[i:i+10]
                    chunk_text = ' '.join(chunk_words)
                    chunk_text = f"<b>{chunk_text}</b>"
                    chunk_start = start + i * time_per_word
                    chunk_end = start + min(i+10, n) * time_per_word
                    start_time = format_time(chunk_start)
                    end_time = format_time(chunk_end)
                    f.write(f"{idx}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{chunk_text}\n\n")
                    idx += 1
        return True
    except Exception as e:
        raise Exception(f"Error creating SRT file: {str(e)}")

def create_word_srt_file(word_segments, output_path):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, word in enumerate(word_segments, 1):
                start_time = format_time(word['start'])
                end_time = format_time(word['end'])
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{word['text']}\n\n")
        return True
    except Exception as e:
        raise Exception(f"Error creating word SRT file: {str(e)}")

def generate_audio_from_script(text: str, speed: float = 1.0, voice_id: str = "ftDdhfYtmfGP0tFlBYA1", stability: float = 0.35, similarity_boost: float = 0.40) -> Tuple[str, str]:
    if not ELEVENLABS_API_KEY:
        raise Exception("ELEVENLABS_API_KEY not set in environment.")
    if not voice_id:
        voice_id = ELEVENLABS_DEFAULT_VOICE_ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "speed": speed,
            "stability": stability,
            "similarity_boost": similarity_boost
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"ElevenLabs API error: {response.text}")
    audio_bytes = response.content
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as f:
        f.write(audio_bytes)
    return filename, filepath

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process_and_generate_video")
async def process_and_generate_video(
    audio_file: Optional[UploadFile] = File(None),
    audio_url: Optional[str] = Form(None),
    script: Optional[str] = Form(None),
    speed: Optional[float] = Form(None),
    voice_id: Optional[str] = Form(None),
    stability: Optional[float] = Form(None),
    similarity_boost: Optional[float] = Form(None),
    video_name: str = Form(...),
    show_subtitles: str = Form("true"),
    selected_background: str = Form("")
):
    try:
        if not audio_file and not audio_url and not script:
            return JSONResponse({"error": "Please provide either an audio file, audio URL, or a script."}, status_code=400)
        if not video_name:
            return JSONResponse({"error": "Video name is required"}, status_code=400)
        video_name_clean = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
        if not video_name_clean:
            return JSONResponse({"error": "Invalid video name"}, status_code=400)
        print(f"[COMBINED API] Starting combined process for video: {video_name_clean}")
        if audio_file:
            filename = audio_file.filename or f"audio_{random.randint(1000,9999)}.mp3"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            with open(filepath, "wb") as f:
                f.write(await audio_file.read())
            print(f"[COMBINED API] Saved uploaded file: {filepath}")
        elif audio_url:
            filename, filepath = download_audio_file(audio_url)
            if not filename:
                filename = f"audio_{random.randint(1000,9999)}.mp3"
            if not filepath:
                return JSONResponse({"error": "Failed to download audio file."}, status_code=400)
            print(f"[COMBINED API] Downloaded file: {filepath}")
        elif script:
            use_speed = speed if speed is not None else 1.0
            use_voice_id = voice_id if voice_id else ELEVENLABS_DEFAULT_VOICE_ID
            use_stability = stability if stability is not None else 0.35
            use_similarity_boost = similarity_boost if similarity_boost is not None else 0.40
            filename, filepath = generate_audio_from_script(script, use_speed, use_voice_id, use_stability, use_similarity_boost)
            print(f"[COMBINED API] Generated audio from script: {filepath}")
        else:
            return JSONResponse({"error": "No valid audio input provided."}, status_code=400)
        if not os.path.exists(filepath):
            return JSONResponse({"error": "Audio file not found after upload/generation."}, status_code=500)
        print(f"[COMBINED API] Transcribing audio...")
        sentence_segments, word_segments = transcribe_audio(filepath)
        base_filename = filename.rsplit('.', 1)[0] if filename and '.' in filename else filename or f"audio_{random.randint(1000,9999)}"
        srt_filename = f"{base_filename}_sentences.srt"
        srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        word_srt_filename = f"{base_filename}_words.srt"
        word_srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        audio_segments = create_audio_segments(sentence_segments, 15)
        segments_filename = f"{base_filename}_segments.json"
        segments_filepath = os.path.join(SEGMENTS_FOLDER, segments_filename)
        # Write segments with start_time/end_time keys for Modal/video generator compatibility
        segments_data = {
            "segments": [
                {
                    "segment_id": i + 1,
                    "start_time": seg["start"] if isinstance(seg, dict) and "start" in seg else 0,
                    "end_time": seg["end"] if isinstance(seg, dict) and "end" in seg else 0,
                    "duration": (seg["end"] - seg["start"]) if isinstance(seg, dict) and "end" in seg and "start" in seg else 0,
                    "text": seg["text"] if isinstance(seg, dict) and "text" in seg else ""
                } for i, seg in enumerate(audio_segments) if isinstance(seg, dict)
            ]
        }
        with open(segments_filepath, 'w', encoding='utf-8') as f:
            json.dump(segments_data, f, indent=2, ensure_ascii=False)
        print(f"[COMBINED API] Audio processing completed")
        print(f"[COMBINED API] Generating images with optimized parallel processing...")
        try:
            result = subprocess.run([sys.executable, 'generate_images_ideogram_optimized.py'], 
                                 capture_output=True, text=True, check=True)
            print(f"[COMBINED API] Image generation completed with optimization")
        except Exception as e:
            print(f"[COMBINED API] Image generation failed: {e}")
        print(f"[COMBINED API] Adding highlights...")
        try:
            result = subprocess.run([sys.executable, 'gpt_highlight_bullets.py', 'segments/slides.json'], 
                                 capture_output=True, text=True, check=True)
            print(f"[COMBINED API] Highlights added")
        except Exception as e:
            print(f"[COMBINED API] Highlight script failed: {e}")
        print(f"[COMBINED API] Generating video...")
        if not selected_background:
            bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
            selected_bg = random.choice(bg_files) if bg_files else None
        else:
            selected_bg = selected_background
            if not os.path.exists(os.path.join('background', selected_bg)):
                bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
                selected_bg = random.choice(bg_files) if bg_files else None
        video_gen = VideoGenerator(
            segments_folder=SEGMENTS_FOLDER,
            transcripts_folder=TRANSCRIPTS_FOLDER,
            font_folder='circular-std-font-family'
        )
        output_video = os.path.join(UPLOAD_FOLDER, f"{video_name_clean}.mp4")
        video_gen.generate_video(segments_filepath, word_srt_filepath, filepath, output_video, 
                               show_subtitles=(show_subtitles.lower() == 'true'), selected_background=selected_bg)
        print(f"[COMBINED API] Video generated successfully: {output_video}")
        # Upload to S3 using put_object
        filename = os.path.basename(output_video)
        s3_url = upload_video_to_s3(output_video, filename)
        return {"success": True, "video_filename": filename, "s3_url": s3_url, "message": "Complete video generated and uploaded successfully"}
    except Exception as e:
        print(f"[COMBINED API ERROR] Process failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500) 