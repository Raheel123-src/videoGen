from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import random
import re
from typing import Optional, Tuple
from app import (
    download_audio_file,
    transcribe_audio,
    create_srt_file,
    create_word_srt_file,
    create_audio_segments,
    create_segments_file,
    VideoGenerator,
    ALLOWED_EXTENSIONS,
    UPLOAD_FOLDER,
    TRANSCRIPTS_FOLDER,
    SEGMENTS_FOLDER
)
import uuid
from dotenv import load_dotenv
import requests
import difflib

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID") or "ftDdhfYtmfGP0tFlBYA1"


def generate_audio_from_script(text: str, speed: float = 1.0, voice_id: str = "ftDdhfYtmfGP0tFlBYA1", stability: float = 0.35, similarity_boost: float = 0.40) -> tuple[str, str]:
    """Generate audio from script using ElevenLabs API and save to uploads folder. Returns (filename, filepath)."""
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

def extract_proper_nouns(script):
    # Simple regex: words with Capitalized First Letter, not at start of sentence
    import re
    # This will match words with a capital letter not at the start of a sentence
    return set(re.findall(r'(?<![\.!?]\s)(?<!^)(\b[A-Z][a-zA-Z]+\b)', script))

def correct_proper_nouns_in_transcript(proper_nouns, sentence_segments, word_segments):
    # Lowercase map for fuzzy matching
    transcript_words = set(w['text'] for w in word_segments)
    for noun in proper_nouns:
        # Fuzzy match in transcript words (case-insensitive)
        matches = difflib.get_close_matches(noun.lower(), [w.lower() for w in transcript_words], n=1, cutoff=0.8)
        if matches:
            wrong = matches[0]
            # Replace in word_segments
            for w in word_segments:
                if w['text'].lower() == wrong:
                    w['text'] = noun
            # Replace in sentence_segments
            for s in sentence_segments:
                s['text'] = ' '.join([noun if word.lower() == wrong else word for word in s['text'].split()])
    return sentence_segments, word_segments

app = FastAPI()

# Optional: Enable CORS if needed
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
        # Validate inputs
        if not audio_file and not audio_url and not script:
            return JSONResponse({"error": "Please provide either an audio file, audio URL, or a script."}, status_code=400)
        if not video_name:
            return JSONResponse({"error": "Video name is required"}, status_code=400)
        # Sanitize video name
        video_name_clean = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
        if not video_name_clean:
            return JSONResponse({"error": "Invalid video name"}, status_code=400)
        print(f"[COMBINED API] Starting combined process for video: {video_name_clean}")
        # Step 1: Process audio (transcribe and create segments)
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
        # Ensure audio file is fully present before transcription
        if not os.path.exists(filepath):
            return JSONResponse({"error": "Audio file not found after upload/generation."}, status_code=500)
        # Transcribe audio
        print(f"[COMBINED API] Transcribing audio...")
        sentence_segments, word_segments = transcribe_audio(filepath)
        # If both audio and script are provided, correct transcript using script
        if audio_file and script:
            proper_nouns = extract_proper_nouns(script)
            sentence_segments, word_segments = correct_proper_nouns_in_transcript(proper_nouns, sentence_segments, word_segments)
        # Create SRT files
        base_filename = filename.rsplit('.', 1)[0] if filename and '.' in filename else filename or f"audio_{random.randint(1000,9999)}"
        srt_filename = f"{base_filename}_sentences.srt"
        srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        word_srt_filename = f"{base_filename}_words.srt"
        word_srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        # Create segments file
        audio_segments = create_audio_segments(sentence_segments, 15)
        segments_filename = f"{base_filename}_segments.json"
        segments_filepath = os.path.join(SEGMENTS_FOLDER, segments_filename)
        create_segments_file(audio_segments, segments_filepath)
        print(f"[COMBINED API] Audio processing completed")
        # Step 2: Generate images
        print(f"[COMBINED API] Generating images with optimized parallel processing...")
        try:
            import subprocess
            result = subprocess.run(['venv/bin/python', 'generate_images_ideogram_optimized.py'], 
                                 capture_output=True, text=True, check=True)
            print(f"[COMBINED API] Image generation completed with optimization")
        except Exception as e:
            print(f"[COMBINED API] Image generation failed: {e}")
        # Step 3: Add highlights
        print(f"[COMBINED API] Adding highlights...")
        try:
            import subprocess
            result = subprocess.run(['python3', 'gpt_highlight_bullets.py'], 
                                 capture_output=True, text=True, check=True)
            print(f"[COMBINED API] Highlights added")
        except Exception as e:
            print(f"[COMBINED API] Highlight script failed: {e}")
        # Step 4: Generate video
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
        return {"success": True, "video_filename": os.path.basename(output_video), "message": "Complete video generated successfully"}
    except Exception as e:
        print(f"[COMBINED API ERROR] Process failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500) 