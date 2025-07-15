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
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import boto3
from botocore.exceptions import NoCredentialsError
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, status, Response, Depends
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

# Load environment variables
load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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

# Whisper model
whisper_model = None
def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        whisper_model = whisper.load_model("base")
    return whisper_model

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_valid_audio_url(url):
    return url.lower().endswith(tuple(ALLOWED_EXTENSIONS))

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
                if isinstance(segment, dict):
                    sentence_segments.append({
                        'start': segment.get('start', 0),
                        'end': segment.get('end', 0),
                        'text': segment.get('text', '').strip()
                    })
            word_segments = []
            for segment in result['segments']:
                if isinstance(segment, dict) and 'words' in segment:
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
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(segments):
                start = str(timedelta(seconds=int(seg['start'])))
                end = str(timedelta(seconds=int(seg['end'])) if seg['end'] else timedelta(seconds=int(seg['start'])+1))
                f.write(f"{i+1}\n{start} --> {end}\n{seg['text']}\n\n")
    except Exception as e:
        raise Exception(f"Error writing SRT: {str(e)}")

def create_word_srt_file(word_segments, output_path):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, word in enumerate(word_segments):
                start = str(timedelta(seconds=int(word['start'])) if word['start'] else 0)
                end = str(timedelta(seconds=int(word['end'])) if word['end'] else 0)
                f.write(f"{i+1}\n{start} --> {end}\n{word['text']}\n\n")
    except Exception as e:
        raise Exception(f"Error writing word SRT: {str(e)}")

def create_segments_file(segments, output_path):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({'segments': segments}, f, indent=2)
    except Exception as e:
        raise Exception(f"Error writing segments file: {str(e)}")

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

# 1. Index route (GET, POST)
@app.get("/", response_class=HTMLResponse)
async def index_get(request: Request):
    background_images = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
    return templates.TemplateResponse("index.html", {"request": request, "message": "", "srt_file_path": None, "word_srt_file_path": None, "segments_file_path": None, "background_images": background_images, "selected_background": None})

@app.post("/", response_class=HTMLResponse)
async def index_post(request: Request, audio_file: Optional[UploadFile] = File(None), audio_url: Optional[str] = Form(None), selected_background: Optional[str] = Form(None)):
    background_images = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
    message = ''
    srt_file_path = None
    word_srt_file_path = None
    segments_file_path = None
    if audio_file is not None:
        filename = audio_file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(await audio_file.read())
        try:
            sentence_segments, word_segments = transcribe_audio(filepath)
            srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
            srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, srt_filename)
            create_srt_file(sentence_segments, srt_filepath)
            word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
            word_srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, word_srt_filename)
            create_word_srt_file(word_segments, word_srt_filepath)
            audio_segments = create_audio_segments(sentence_segments, 15)
            segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
            segments_filepath = os.path.join(SEGMENTS_FOLDER, segments_filename)
            create_segments_file(audio_segments, segments_filepath)
            message = f'Processing complete! Files: {srt_filename}, {word_srt_filename}, {segments_filename}'
            srt_file_path = srt_filepath
            word_srt_file_path = word_srt_filepath
            segments_file_path = segments_filepath
        except Exception as e:
            message = f'Error processing audio: {str(e)}'
    elif audio_url:
        if is_valid_audio_url(audio_url):
            try:
                filename, filepath = download_audio_file(audio_url)
                sentence_segments, word_segments = transcribe_audio(filepath)
                srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
                srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, srt_filename)
                create_srt_file(sentence_segments, srt_filepath)
                word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
                word_srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, word_srt_filename)
                create_word_srt_file(word_segments, word_srt_filepath)
                audio_segments = create_audio_segments(sentence_segments, 15)
                segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
                segments_filepath = os.path.join(SEGMENTS_FOLDER, segments_filename)
                create_segments_file(audio_segments, segments_filepath)
                message = f'Processing complete! Files: {srt_filename}, {word_srt_filename}, {segments_filename}'
                srt_file_path = srt_filepath
                word_srt_file_path = word_srt_filepath
                segments_file_path = segments_filepath
            except Exception as e:
                message = f'Error processing audio: {str(e)}'
        else:
            message = 'Invalid audio URL. Please provide a URL ending with an audio file extension (mp3, wav, m4a, aac, ogg)'
    else:
        message = 'Please either upload a file or provide an audio URL'
    return templates.TemplateResponse("index.html", {"request": request, "message": message, "srt_file_path": srt_file_path, "word_srt_file_path": word_srt_file_path, "segments_file_path": segments_file_path, "background_images": background_images, "selected_background": selected_background})

# 2. /api/transcribe (POST)
@app.post("/api/transcribe")
async def api_transcribe(data: dict):
    audio_url = data.get('audio_url', '').strip()
    if not audio_url:
        return JSONResponse({'error': 'audio_url is required'}, status_code=400)
    if not is_valid_audio_url(audio_url):
        return JSONResponse({'error': 'Invalid audio URL format'}, status_code=400)
    filename, filepath = download_audio_file(audio_url)
    sentence_segments, word_segments = transcribe_audio(filepath)
    srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
    srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, srt_filename)
    create_srt_file(sentence_segments, srt_filepath)
    word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
    word_srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, word_srt_filename)
    create_word_srt_file(word_segments, word_srt_filepath)
    audio_segments = create_audio_segments(sentence_segments, 15)
    segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
    segments_filepath = os.path.join(SEGMENTS_FOLDER, segments_filename)
    create_segments_file(audio_segments, segments_filepath)
    return JSONResponse({
        'success': True,
        'sentence_file': srt_filename,
        'word_file': word_srt_filename,
        'segments_file': segments_filename,
        'sentence_segments': sentence_segments,
        'word_segments': word_segments,
        'audio_segments': audio_segments,
        'sentence_download_url': f'/download/{srt_filename}',
        'word_download_url': f'/download/{word_srt_filename}',
        'segments_download_url': f'/download/{segments_filename}'
    })

# 3. /api/health (GET)
@app.get("/api/health")
async def api_health():
    return JSONResponse({
        'status': 'healthy',
        'model': 'whisper-base',
        'supported_formats': list(ALLOWED_EXTENSIONS),
        'output_types': ['sentences', 'words', 'segments'],
        'openai_configured': os.getenv('OPENAI_API_KEY') is not None and os.getenv('OPENAI_API_KEY') != 'your_openai_api_key_here'
    })

# 4. /download/{filename} (GET)
@app.get("/download/{filename}")
async def download_srt(filename: str):
    if filename.endswith('.md'):
        file_path = os.path.join(SEGMENTS_FOLDER, filename)
    else:
        file_path = os.path.join(TRANSCRIPTS_FOLDER, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    else:
        return RedirectResponse(url="/")

# 5. /download_markdown/{filename} (GET)
@app.get("/download_markdown/{filename}")
async def download_markdown(filename: str):
    file_path = os.path.join(SEGMENTS_FOLDER, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type='text/markdown')
    else:
        return RedirectResponse(url="/")

# 6. /generate_video/{filename} (GET)
@app.get("/generate_video/{filename}")
async def generate_video(filename: str, show_subtitles: Optional[str] = None, background: Optional[str] = None):
    try:
        show_subtitles = show_subtitles == '1' if show_subtitles is not None else True
        selected_background = background
        base_name = filename.rsplit('_segments.json', 1)[0]
        segments_file = os.path.join(SEGMENTS_FOLDER, filename)
        word_srt_file = os.path.join(TRANSCRIPTS_FOLDER, f"{base_name}_words.srt")
        audio_file = None
        for ext in ['mp3', 'wav', 'm4a', 'aac', 'ogg']:
            potential_audio = os.path.join(UPLOAD_FOLDER, f"{base_name}.{ext}")
            if os.path.exists(potential_audio):
                audio_file = potential_audio
                break
        if not audio_file or not os.path.exists(segments_file) or not os.path.exists(word_srt_file):
            return RedirectResponse(url="/")
        # Run Ideogram image generation
        try:
            import subprocess
            result = subprocess.run(['venv/bin/python', 'generate_images_ideogram.py'], capture_output=True, text=True, check=True)
        except Exception:
            pass
        # Run highlight script
        try:
            import subprocess
            result = subprocess.run(['python3', 'gpt_highlight_bullets.py'], capture_output=True, text=True, check=True)
        except Exception:
            pass
        video_gen = VideoGenerator(
            segments_folder=SEGMENTS_FOLDER,
            transcripts_folder=TRANSCRIPTS_FOLDER,
            font_folder='circular-std-font-family'
        )
        output_video = os.path.join(UPLOAD_FOLDER, f"{base_name}_video.mp4")
        video_gen.generate_video(segments_file, word_srt_file, audio_file, output_video, show_subtitles=show_subtitles, selected_background=selected_background)
        return RedirectResponse(url="/")
    except Exception:
        return RedirectResponse(url="/")

# 7. /process_and_generate_video (POST)
@app.post("/process_and_generate_video")
async def process_and_generate_video(request: Request, audio_file: Optional[UploadFile] = File(None), audio_url: Optional[str] = Form(None), video_name: str = Form(...), show_subtitles: Optional[str] = Form('true'), selected_background: Optional[str] = Form(None)):
    try:
        import subprocess
        import time
        from moviepy.editor import VideoFileClip, CompositeVideoClip
        from pydub import AudioSegment
        heygen_output_dir = 'heygen_videos'
        os.makedirs(heygen_output_dir, exist_ok=True)
        s3_links_path = os.path.join(heygen_output_dir, 's3_links.txt')
        # Clear the file at the start of each run
        with open(s3_links_path, 'w') as f:
            f.write('')
        S3_BUCKET = os.getenv('S3_BUCKET_NAME')
        heygen_api_key = os.getenv('HEYGEN_API_KEY')
        heygen_avatar_id = 'Angela-inblackskirt-20220820'
        # Step 1: Process audio
        filename = None
        filepath = None
        if audio_file is not None:
            filename = audio_file.filename
            if not filename or not isinstance(filename, str):
                return JSONResponse({'error': 'No audio file provided.'}, status_code=400)
            filepath = os.path.join(UPLOAD_FOLDER, filename) if filename else ''
            with open(filepath, "wb") as f:
                f.write(await audio_file.read())
        elif audio_url:
            filename, filepath = download_audio_file(audio_url)
            if not filename or not isinstance(filename, str) or not filepath or not isinstance(filepath, str):
                return JSONResponse({'error': 'Audio file could not be downloaded or is empty.'}, status_code=400)
        else:
            return JSONResponse({'error': 'No audio file or URL provided.'}, status_code=400)
        # Defensive check: file exists and is not empty
        if not filepath or not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return JSONResponse({'error': 'Audio file could not be downloaded or is empty.'}, status_code=400)
        sentence_segments, word_segments = transcribe_audio(filepath)
        # Defensive check: transcription output
        if not sentence_segments:
            return JSONResponse({'error': 'No speech detected in audio.'}, status_code=400)
        if not word_segments:
            return JSONResponse({'error': 'No words detected in audio.'}, status_code=400)
        if filename and isinstance(filename, str) and '.' in filename:
            base_filename = filename.rsplit('.', 1)[0]
        else:
            base_filename = 'audio'
        srt_filename = f"{base_filename}_sentences.srt"
        srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        word_srt_filename = f"{base_filename}_words.srt"
        word_srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        audio_segments = create_audio_segments(sentence_segments, 15)
        # Defensive check: segment creation
        if not audio_segments:
            return JSONResponse({'error': 'No segments could be created from the audio.'}, status_code=400)
        segments_filename = f"{base_filename}_segments.json"
        segments_filepath = os.path.join(SEGMENTS_FOLDER, segments_filename)
        create_segments_file(audio_segments, segments_filepath)
        # Step 2: Generate images
        try:
            subprocess.run(['venv/bin/python', 'generate_images_ideogram_optimized.py'], capture_output=True, text=True, check=True)
        except Exception:
            pass
        # Step 3: Add highlights
        try:
            subprocess.run(['python3', 'gpt_highlight_bullets.py'], capture_output=True, text=True, check=True)
        except Exception:
            pass
        # Step 4: Generate video
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
        output_video = os.path.join(UPLOAD_FOLDER, f"{video_name}.mp4")
        video_gen.generate_video(segments_filepath, word_srt_filepath, filepath, output_video, show_subtitles=show_subtitles.lower() == 'true', selected_background=selected_bg)
        # --- Calculate and save heygen_empty_spaces.json ---
        try:
            FONT_PATH = 'circular-std-font-family/CircularStd-Book.ttf'
            TITLE_FONT_SIZE = 72
            BODY_FONT_SIZE = 36
            from PIL import ImageFont, ImageDraw, Image
            with open('segments/slides.json', 'r', encoding='utf-8') as f:
                slides = json.load(f)
            try:
                title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
                body_font = ImageFont.truetype(FONT_PATH, BODY_FONT_SIZE)
            except Exception:
                title_font = ImageFont.load_default()
                body_font = ImageFont.load_default()
            def wrap_text(text, font, max_width, draw):
                words = text.split()
                lines = []
                current_line = ''
                for word in words:
                    test_line = current_line + (' ' if current_line else '') + word
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    width = bbox[2] - bbox[0]
                    if width <= max_width:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                return lines
            def calculate_empty_space(slide, title_font, body_font):
                format_type = slide.get('format')
                if format_type not in [2, 3]:
                    return None
                title = slide.get('title', '')
                bullets = slide.get('bullets', [])
                SLIDE_WIDTH = 1920
                SLIDE_HEIGHT = 1080
                LEFT_MARGIN = 80
                TOP_MARGIN = 120
                BOTTOM_MARGIN = 80
                SUBTITLE_HEIGHT = 60
                max_text_width = SLIDE_WIDTH // 2 - 2 * LEFT_MARGIN
                img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT))
                draw = ImageDraw.Draw(img)
                y = TOP_MARGIN
                title_lines = wrap_text(title, title_font, max_text_width, draw)
                for line in title_lines:
                    y += title_font.size + 10
                y += 120
                for bullet in bullets:
                    bullet_lines = wrap_text(bullet, body_font, max_text_width, draw)
                    for line in bullet_lines:
                        y += body_font.size + 8
                    y += 24
                bullets_end_y = y
                subtitle_y = SLIDE_HEIGHT - BOTTOM_MARGIN - SUBTITLE_HEIGHT
                empty_space_top = bullets_end_y
                empty_space_bottom = subtitle_y
                empty_space_height = max(0, empty_space_bottom - empty_space_top)
                if format_type == 2:
                    x = LEFT_MARGIN
                else:
                    x = SLIDE_WIDTH // 2 + LEFT_MARGIN
                width = SLIDE_WIDTH // 2 - 2 * LEFT_MARGIN
                return {
                    'slide_number': slide.get('slide_number'),
                    'format': format_type,
                    'empty_space': {
                        'x': x,
                        'y': empty_space_top,
                        'width': width,
                        'height': empty_space_height
                    }
                }
            empty_spaces = []
            for slide in slides:
                result = calculate_empty_space(slide, title_font, body_font)
                if result:
                    empty_spaces.append(result)
            with open('heygen_empty_spaces.json', 'w', encoding='utf-8') as f:
                json.dump(empty_spaces, f, indent=2)
        except Exception:
            pass
        # --- Overlay HeyGen avatar videos in empty spaces (formats 2 & 3) ---
        try:
            from moviepy.editor import VideoFileClip, CompositeVideoClip
            import numpy as np
            from pydub import AudioSegment
            import time
            heygen_output_dir = 'heygen_videos'
            os.makedirs(heygen_output_dir, exist_ok=True)
            from main import upload_file_to_s3
            with open('heygen_empty_spaces.json', 'r', encoding='utf-8') as f:
                empty_spaces = json.load(f)
            if not empty_spaces:
                overlay_filename = None
            else:
                with open(segments_filepath, 'r', encoding='utf-8') as f:
                    segments_data = json.load(f)
                segments = segments_data.get('segments', [])
                if not heygen_api_key or heygen_api_key == 'YOUR_HEYGEN_API_KEY':
                    overlay_filename = None
                elif not S3_BUCKET:
                    overlay_filename = None
                else:
                    slide_segments = []
                    for space in empty_spaces:
                        slide_number = space.get('slide_number')
                        segment = next((s for s in segments if s.get('segment_id') == slide_number), None)
                        if not segment:
                            continue
                        slide_segments.append({
                            'slide_number': slide_number,
                            'start_time': segment.get('start_time', 0),
                            'end_time': segment.get('end_time', 0),
                            'empty_space': space['empty_space']
                        })
                    for slide in slide_segments:
                        slide_number = slide['slide_number']
                        start_time = slide['start_time']
                        end_time = slide['end_time']
                        width = int(slide['empty_space']['width'])
                        height = int(slide['empty_space']['height'])
                        audio = AudioSegment.from_file(filepath)
                        segment_audio = audio[start_time * 1000:end_time * 1000]
                        segment_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_audio.mp3')
                        segment_audio.export(segment_path, format='mp3')
                        s3_key = f'heygen_segments/slide_{slide_number}_audio.mp3'
                        s3_url = upload_file_to_s3(segment_path, s3_key, bucket_name=S3_BUCKET)
                        # Store S3 URL in s3_links.txt for debugging
                        if s3_url:
                            with open(s3_links_path, 'a') as f:
                                f.write(s3_url + '\n')
                        if not s3_url:
                            continue
                        headers = {
                            "X-Api-Key": heygen_api_key,
                            "Content-Type": "application/json"
                        }
                        data = {
                            "video_inputs": [
                                {
                                    "character": {
                                        "type": "avatar",
                                        "avatar_id": heygen_avatar_id,
                                        "avatar_style": "normal"
                                    },
                                    "voice": {
                                        "type": "audio",
                                        "audio_url": s3_url
                                    },
                                    "background": {
                                        "type": "color",
                                        "value": "#FFFFFF"
                                    }
                                }
                            ],
                            "dimension": {
                                "width": width,
                                "height": height
                            }
                        }
                        try:
                            resp = requests.post("https://api.heygen.com/v2/video/generate", headers=headers, json=data)
                            if resp.status_code != 200:
                                continue
                            video_id = resp.json()["data"]["video_id"]
                            status_url = f"https://api.heygen.com/v1/video_status.get?video_id={video_id}"
                            while True:
                                status_resp = requests.get(status_url, headers=headers)
                                status_json = status_resp.json()
                                status = status_json["data"]["status"]
                                if status == "completed":
                                    video_url = status_json["data"]["video_url"]
                                    video_content = requests.get(video_url).content
                                    video_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen.mp4')
                                    with open(video_path, "wb") as f:
                                        f.write(video_content)
                                    heygen_clip = VideoFileClip(video_path)
                                    noaudio_clip = heygen_clip.without_audio()
                                    noaudio_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio.mp4')
                                    noaudio_clip.write_videofile(noaudio_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
                                    heygen_clip.close()
                                    noaudio_clip.close()
                                    resized_clip = VideoFileClip(noaudio_path)
                                    resized_clip = resized_clip.resize((width, height))
                                    resized_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio_resized.mp4')
                                    resized_clip.write_videofile(resized_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
                                    resized_clip.close()
                                    os.remove(video_path)
                                    os.remove(noaudio_path)
                                    break
                                elif status == "failed":
                                    break
                                else:
                                    time.sleep(5)
                        except Exception:
                            continue
                    # Overlay HeyGen videos on main video
                    try:
                        main_video = VideoFileClip(output_video)
                        overlays = []
                        for slide in slide_segments:
                            slide_number = slide['slide_number']
                            start = slide['start_time']
                            end = slide['end_time']
                            space = slide['empty_space']
                            x = int(space['x'])
                            y = int(space['y'])
                            heygen_vid_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio_resized.mp4')
                            if not os.path.exists(heygen_vid_path):
                                continue
                            heygen_clip = VideoFileClip(heygen_vid_path).set_start(start).set_end(end).set_position((x, y))
                            overlays.append(heygen_clip)
                        if overlays:
                            final = CompositeVideoClip([main_video] + overlays, size=main_video.size)
                            overlay_output = os.path.join(UPLOAD_FOLDER, f"heygen_overlay_{video_name}.mp4")
                            final.write_videofile(overlay_output, codec='libx264', audio_codec='aac', fps=main_video.fps, threads=4, verbose=False, logger=None)
                            final.close()
                            overlay_filename = os.path.basename(overlay_output)
                        else:
                            overlay_filename = None
                        main_video.close()
                    except Exception:
                        overlay_filename = None
        except Exception:
            overlay_filename = None
        return JSONResponse({
            'success': True,
            'video_filename': os.path.basename(output_video),
            'overlay_video_filename': overlay_filename,
            'overlay_video_preview_url': f"/download_video/{overlay_filename}" if overlay_filename else None,
            'message': 'Complete video generated successfully'
        })
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)

# 8. /generate_video_api (POST)
@app.post("/generate_video_api")
async def generate_video_api(data: dict):
    try:
        video_name = data.get('video_name', '').strip()
        show_subtitles = data.get('show_subtitles', True)
        selected_background = data.get('selected_background', '')
        if not video_name:
            return JSONResponse({'error': 'Video name is required'}, status_code=400)
        import re
        video_name = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
        if not video_name:
            return JSONResponse({'error': 'Invalid video name'}, status_code=400)
        segments_files = glob.glob(os.path.join(SEGMENTS_FOLDER, '*_segments.json'))
        if not segments_files:
            return JSONResponse({'error': 'No processed audio files found. Please process an audio file first.'}, status_code=400)
        segments_file = max(segments_files, key=os.path.getctime)
        base_name = os.path.basename(segments_file).replace('_segments.json', '')
        word_srt_file = os.path.join(TRANSCRIPTS_FOLDER, f"{base_name}_words.srt")
        slides_file = os.path.join(SEGMENTS_FOLDER, 'slides.json')
        if not os.path.exists(word_srt_file) or not os.path.exists(slides_file):
            return JSONResponse({'error': 'Required files not found.'}, status_code=400)
        audio_file = None
        for ext in ['mp3', 'wav', 'm4a', 'aac', 'ogg']:
            potential_audio = os.path.join(UPLOAD_FOLDER, f"{base_name}.{ext}")
            if os.path.exists(potential_audio):
                audio_file = potential_audio
                break
        if not audio_file:
            return JSONResponse({'error': f'Original audio file not found for: {base_name}'}, status_code=400)
        if not selected_background:
            bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
            selected_bg = random.choice(bg_files) if bg_files else None
        else:
            selected_bg = selected_background
            if not os.path.exists(os.path.join('background', selected_bg)):
                bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
                selected_bg = random.choice(bg_files) if bg_files else None
        try:
            import subprocess
            subprocess.run(['venv/bin/python', 'generate_images_ideogram_optimized.py'], capture_output=True, text=True, check=True)
        except Exception:
            pass
        try:
            import subprocess
            subprocess.run(['python3', 'gpt_highlight_bullets.py'], capture_output=True, text=True, check=True)
        except Exception:
            pass
        video_gen = VideoGenerator(
            segments_folder=SEGMENTS_FOLDER,
            transcripts_folder=TRANSCRIPTS_FOLDER,
            font_folder='circular-std-font-family'
        )
        output_video = os.path.join(UPLOAD_FOLDER, f"{video_name}.mp4")
        video_gen.generate_video(segments_file, word_srt_file, audio_file, output_video, show_subtitles=show_subtitles, selected_background=selected_bg)
        return JSONResponse({
            'success': True,
            'video_filename': os.path.basename(output_video),
            'message': 'Video generated successfully'
        })
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)

# 9. /download_video/{filename} (GET)
@app.get("/download_video/{filename}")
async def download_video(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type='video/mp4')
    else:
        return RedirectResponse(url="/")

# 10. /api/test_overlay_empty_space (POST)
@app.post("/api/test_overlay_empty_space")
async def api_test_overlay_empty_space(data: dict):
    try:
        video_filename = data.get('video_filename')
        if not video_filename:
            return JSONResponse({'error': 'Missing video_filename'}, status_code=400)
        final_video_path = os.path.join(UPLOAD_FOLDER, video_filename)
        if not os.path.exists(final_video_path):
            return JSONResponse({'error': f'Video not found: {final_video_path}'}, status_code=404)
        with open('heygen_empty_spaces.json', 'r', encoding='utf-8') as f:
            empty_spaces = json.load(f)
        video = VideoFileClip(final_video_path)
        duration = video.duration
        w, h = video.size
        test_img_url = 'https://picsum.photos/400/400'
        img_response = requests.get(test_img_url)
        from PIL import Image
        from io import BytesIO
        pil_img = Image.open(BytesIO(img_response.content)).convert('RGBA')
        overlays = []
        for space in empty_spaces:
            x = int(space['empty_space']['x'])
            y = int(space['empty_space']['y'])
            width = int(space['empty_space']['width'])
            height = int(space['empty_space']['height'])
            if width <= 0 or height <= 0:
                continue
            img_resized = pil_img.resize((width, height))
            img_clip = ImageClip(np.array(img_resized)).set_duration(duration)
            img_clip = img_clip.set_position((x, y))
            overlays.append(img_clip)
        final = CompositeVideoClip([video] + overlays, size=video.size)
        output_path = os.path.join(UPLOAD_FOLDER, f"test_overlay_{video_filename}")
        final.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=video.fps, threads=4, verbose=False, logger=None)
        video.close()
        final.close()
        return JSONResponse({'success': True, 'output_video': os.path.basename(output_path)})
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500) 