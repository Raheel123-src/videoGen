# main.py - FastAPI version of the Flask app
import os
import re
import requests
from urllib.parse import urlparse
import whisper
from pydub import AudioSegment
import json
from datetime import timedelta
from dotenv import load_dotenv
from openai import OpenAI
from video_generator import VideoGenerator
import glob
import random
import subprocess
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import boto3
from botocore.exceptions import NoCredentialsError
import time
import sys  # <-- Add this import

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

# Load environment variables
load_dotenv()

app = FastAPI()

# CORS (optional, for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = 'uploads'
TRANSCRIPTS_FOLDER = 'transcripts'
SEGMENTS_FOLDER = 'segments'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'aac', 'ogg'}

for folder in [UPLOAD_FOLDER, TRANSCRIPTS_FOLDER, SEGMENTS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

whisper_model = None
def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        whisper_model = whisper.load_model("base")
    return whisper_model

def get_openai_client():
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or api_key == 'your_openai_api_key_here':
        raise Exception("OpenAI API key not found. Please set OPENAI_API_KEY in .env file")
    return OpenAI(api_key=api_key)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_valid_audio_url(url):
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        path = parsed.path.lower()
        return any(path.endswith(f'.{ext}') for ext in ALLOWED_EXTENSIONS)
    except:
        return False

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
    except requests.RequestException as e:
        raise Exception(f"Failed to download file: {str(e)}")
    except Exception as e:
        raise Exception(f"Error processing URL: {str(e)}")

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
        if not audio_path or not isinstance(audio_path, str):
            raise Exception("Invalid audio path")
        if not audio_path.lower().endswith('.mp3'):
            audio_path = convert_to_mp3(audio_path)
        model = get_whisper_model()
        result = model.transcribe(audio_path, word_timestamps=True)
        if result and 'segments' in result:
            sentence_segments = []
            for segment in result['segments']:
                if not isinstance(segment, dict):
                    continue
                sentence_segments.append({
                    'start': segment.get('start', 0),
                    'end': segment.get('end', 0),
                    'text': segment.get('text', '').strip()
                })
            word_segments = []
            for segment in result['segments']:
                if not isinstance(segment, dict):
                    continue
                for word in segment.get('words', []):
                    if not isinstance(word, dict):
                        continue
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
    last = sentence_segments[-1] if isinstance(sentence_segments[-1], dict) else None
    total_duration = last.get('end', 0) if last else 0
    segments = []
    segment_start = 0
    while segment_start < total_duration:
        segment_end = min(segment_start + segment_duration, total_duration)
        segment_text = ""
        for sentence in sentence_segments:
            if not isinstance(sentence, dict):
                continue
            sentence_start = sentence.get('start', 0)
            sentence_end = sentence.get('end', 0)
            if (sentence_start < segment_end and sentence_end > segment_start):
                if segment_text:
                    segment_text += " " + sentence.get('text', '')
                else:
                    segment_text = sentence.get('text', '')
        if segment_text.strip():
            segments.append({
                'start': segment_start,
                'end': segment_end,
                'text': segment_text.strip(),
                'sentences': [s for s in sentence_segments if isinstance(s, dict) and s.get('start', 0) < segment_end and s.get('end', 0) > segment_start]
            })
        segment_start = segment_end
    return segments

def create_srt_file(segments, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments):
            start = str(timedelta(seconds=int(seg['start'])))
            end = str(timedelta(seconds=int(seg['end'])) if seg['end'] else timedelta(seconds=int(seg['start'])+1))
            f.write(f"{i+1}\n{start} --> {end}\n{seg['text']}\n\n")

def create_word_srt_file(word_segments, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, word in enumerate(word_segments):
            start = str(timedelta(seconds=int(word['start'])) if word['start'] else 0)
            end = str(timedelta(seconds=int(word['end'])) if word['end'] else 0)
            f.write(f"{i+1}\n{start} --> {end}\n{word['text']}\n\n")

def create_segments_file(segments, output_path):
    """Create both slides.json and segments.json files (timing file)."""
    try:
        # Import the slide JSON generator from app.py or define it here if needed
        from app import generate_slide_json_content
    except ImportError:
        # If not available, define a fallback that raises
        def generate_slide_json_content(*args, **kwargs):
            raise Exception("generate_slide_json_content not found. Please copy it from app.py.")
    try:
        # Create slides.json
        slides = []
        total_segments = len(segments)
        previous_format = None
        for i, segment in enumerate(segments):
            percent = int((i+1)/total_segments*100)
            print(f"Generating slide JSON for segment {i+1}/{total_segments} ({percent}%)", flush=True)
            slide_json = generate_slide_json_content(segment['text'], i, segment['end'] - segment['start'], previous_format=previous_format)
            previous_format = slide_json.get('format', previous_format)
            slides.append(slide_json)
        # Save the slides.json file
        slides_json_path = os.path.join(SEGMENTS_FOLDER, 'slides.json')
        with open(slides_json_path, 'w', encoding='utf-8') as f:
            json.dump(slides, f, indent=2, ensure_ascii=False)
        print(f"Slides JSON saved: {slides_json_path}")
        # Create segments.json with proper timing keys
        segments_data = {
            "segments": []
        }
        for i, segment in enumerate(segments):
            segment_data = {
                "segment_id": i + 1,
                "start_time": segment['start'],
                "end_time": segment['end'],
                "duration": segment['end'] - segment['start'],
                "text": segment['text']
            }
            segments_data["segments"].append(segment_data)
        # Save the segments.json file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(segments_data, f, indent=2, ensure_ascii=False)
        print(f"Segments JSON saved: {output_path}")
        return True
    except Exception as e:
        raise Exception(f"Error creating segments files: {str(e)}")

def upload_file_to_s3(local_file_path, s3_key, bucket_name=None, acl='public-read'):
    bucket = bucket_name or os.getenv('S3_BUCKET_NAME')
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION')
    )
    try:
        s3.upload_file(local_file_path, bucket, s3_key, ExtraArgs={'ContentType': 'audio/mpeg'})
        url = f'https://{bucket}.s3.{os.getenv("AWS_REGION")}.amazonaws.com/{s3_key}'
        return url
    except FileNotFoundError:
        print(f"[S3] The file {local_file_path} was not found.")
        return None
    except NoCredentialsError:
        print("[S3] AWS credentials not available.")
        return None
    except Exception as e:
        print(f"[S3] Error uploading to S3: {e}")
        return None

@app.post("/process_and_generate_video")
async def process_and_generate_video(
    request: Request,
    audio_file: Optional[UploadFile] = File(None),
    audio_url: Optional[str] = Form(None),
    video_name: str = Form(...),
    show_subtitles: Optional[str] = Form('true'),
    selected_background: Optional[str] = Form(None)
):
    try:
        print('--- DEBUG: FastAPI /process_and_generate_video called ---')
        print('Current working directory:', os.getcwd())
        print('audio_file:', audio_file)
        print('audio_url:', audio_url)
        print('video_name:', video_name)
        print('selected_background:', selected_background)
        # Validate inputs
        if not audio_file and not audio_url:
            print('No audio file or URL provided')
            return JSONResponse({'error': 'Please provide either an audio file or audio URL'}, status_code=400)
        if not video_name:
            print('No video name provided')
            return JSONResponse({'error': 'Video name is required'}, status_code=400)
        video_name = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
        if not video_name:
            print('Invalid video name after sanitization')
            return JSONResponse({'error': 'Invalid video name'}, status_code=400)
        # Step 1: Process audio
        filename = None
        filepath = None
        if audio_file:
            filename = audio_file.filename
            if not filename:
                print('No audio file provided (filename is None)')
                return JSONResponse({'error': 'No audio file provided.'}, status_code=400)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            print('Saving uploaded audio file to:', filepath)
            with open(filepath, "wb") as f:
                f.write(await audio_file.read())
        else:
            filename, filepath = download_audio_file(audio_url)
            print('Downloaded audio file:', filename, filepath)
        if not filename or not filepath:
            print('Audio file could not be processed (filename or filepath is None)')
            return JSONResponse({'error': 'Audio file could not be processed.'}, status_code=400)
        print('Audio file exists:', os.path.exists(filepath))
        sentence_segments, word_segments = transcribe_audio(filepath)
        print('sentence_segments:', sentence_segments)
        print('Length of sentence_segments:', len(sentence_segments) if sentence_segments else 0)
        if not sentence_segments:
            print('No speech detected in audio.')
            return JSONResponse({'error': 'No speech detected in audio.'}, status_code=400)
        srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
        srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
        word_srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        audio_segments = create_audio_segments(sentence_segments, 15)
        print('audio_segments:', audio_segments)
        print('Length of audio_segments:', len(audio_segments) if audio_segments else 0)
        segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
        segments_filepath = os.path.join(SEGMENTS_FOLDER, segments_filename)
        create_segments_file(audio_segments, segments_filepath)
        print('segments_filepath:', segments_filepath)
        print('segments file exists:', os.path.exists(segments_filepath))
        # Step 2: Generate images
        try:
            print('About to run image generation script. File exists:', os.path.exists('generate_images_ideogram_optimized.py'))
            subprocess.run([sys.executable, 'generate_images_ideogram_optimized.py'], capture_output=True, text=True, check=True)
        except Exception as e:
            print(f"[FastAPI] Image generation failed: {e}")
        # Step 3: Add highlights
        try:
            print('About to run highlight script. File exists:', os.path.exists('gpt_highlight_bullets.py'))
            # subprocess.run([sys.executable, 'gpt_highlight_bullets.py'], capture_output=True, text=True, check=True)
            print('[DEBUG] Highlight script call is commented out for testing.')
        except Exception as e:
            print(f"[FastAPI] Highlight script failed: {e}")
        # Step 4: Generate video
        if not selected_background:
            bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
            selected_bg = random.choice(bg_files) if bg_files else None
        else:
            selected_bg = selected_background
            if not selected_bg or not os.path.exists(os.path.join('background', selected_bg)):
                bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
                selected_bg = random.choice(bg_files) if bg_files else None
        print('selected_bg:', selected_bg)
        video_gen = VideoGenerator(
            segments_folder=SEGMENTS_FOLDER,
            transcripts_folder=TRANSCRIPTS_FOLDER,
            font_folder='circular-std-font-family'
        )
        output_video = os.path.join(UPLOAD_FOLDER, f"{video_name}.mp4")
        show_subtitles_str = show_subtitles if isinstance(show_subtitles, str) else 'true'
        print('About to generate video. Output path:', output_video)
        video_gen.generate_video(segments_filepath, word_srt_filepath, filepath, output_video, show_subtitles=show_subtitles_str.lower() == 'true', selected_background=selected_bg)
        print('Video generated:', output_video, 'Exists:', os.path.exists(output_video))
        overlay_filename = None
        # --- HeyGen overlay logic (optional, as in Flask) ---
        try:
            # Place HeyGen overlay logic here if needed, as in Flask
            pass
        except Exception as e:
            print(f"[FastAPI] HeyGen overlay step failed: {e}")
            overlay_filename = None
        print('Returning success response')
        return JSONResponse({
            'success': True,
            'video_filename': os.path.basename(output_video),
            'overlay_video_filename': overlay_filename,
            'overlay_video_preview_url': f"/download_video/{overlay_filename}" if overlay_filename else None,
            'message': 'Complete video generated successfully'
        })
    except Exception as e:
        print(f"[FastAPI ERROR] Process failed: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)

@app.get("/download_video/{filename}")
async def download_video(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type='video/mp4')
    else:
        return RedirectResponse(url="/") 