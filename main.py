import os
import re
import json
import random
import subprocess
import time
from urllib.parse import urlparse
from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from pydantic import BaseModel
from starlette.responses import FileResponse
from starlette.background import BackgroundTask
from dotenv import load_dotenv
from video_generator import VideoGenerator
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from pydub import AudioSegment
import requests
import boto3
from botocore.exceptions import NoCredentialsError

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

# --- Helper functions from app.py ---
def download_audio_file(url):
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

def transcribe_audio(audio_path):
    import whisper
    if not audio_path.lower().endswith('.mp3'):
        audio = AudioSegment.from_file(audio_path)
        mp3_path = audio_path.rsplit('.', 1)[0] + '.mp3'
        audio.export(mp3_path, format='mp3')
        audio_path = mp3_path
    model = whisper.load_model("base")
    result = model.transcribe(audio_path, word_timestamps=True)
    if result and 'segments' in result:
        sentence_segments = []
        for segment in result['segments']:
            sentence_segments.append({
                'start': segment['start'],
                'end': segment['end'],
                'text': segment['text'].strip()
            })
        word_segments = []
        for segment in result['segments']:
            if 'words' in segment:
                for word in segment['words']:
                    word_segments.append({
                        'start': word['start'],
                        'end': word['end'],
                        'text': word['word'].strip()
                    })
        return sentence_segments, word_segments
    else:
        raise Exception("No transcript found")

def create_srt_file(segments, output_path):
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        milliseconds = int((secs % 1) * 1000)
        secs = int(secs)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, 1):
            start_time = format_time(segment['start'])
            end_time = format_time(segment['end'])
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{segment['text']}\n\n")
    return True

def create_word_srt_file(word_segments, output_path):
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        milliseconds = int((secs % 1) * 1000)
        secs = int(secs)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, word in enumerate(word_segments, 1):
            start_time = format_time(word['start'])
            end_time = format_time(word['end'])
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{word['text']}\n\n")
    return True

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

def create_segments_file(segments, output_path):
    segments_data = {"segments": []}
    for i, segment in enumerate(segments):
        segment_data = {
            "segment_id": i + 1,
            "start_time": segment['start'],
            "end_time": segment['end'],
            "duration": segment['end'] - segment['start'],
            "text": segment['text']
        }
        segments_data["segments"].append(segment_data)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(segments_data, f, indent=2, ensure_ascii=False)
    return True

# --- Empty space detection logic ---
SLIDES_JSON_PATH = 'segments/slides.json'
FONT_PATH = 'circular-std-font-family/CircularStd-Book.ttf'
TITLE_FONT_SIZE = 72
BODY_FONT_SIZE = 36
SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
LEFT_MARGIN = 80
TOP_MARGIN = 120
BULLET_SPACING = 44
SUBTITLE_HEIGHT = 60
BOTTOM_MARGIN = 80

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

# --- FastAPI endpoint ---
from fastapi import APIRouter
router = APIRouter()

@app.post('/process_and_generate_video')
async def process_and_generate_video(
    request: Request,
    audio_file: Optional[UploadFile] = File(None),
    audio_url: Optional[str] = Form(''),
    video_name: str = Form(...),
    show_subtitles: str = Form('true'),
    selected_background: str = Form('')
):
    try:
        # Validate inputs
        if not audio_file and not audio_url:
            return JSONResponse({'error': 'Please provide either an audio file or audio URL'}, status_code=400)
        if not video_name:
            return JSONResponse({'error': 'Video name is required'}, status_code=400)
        video_name_sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
        if not video_name_sanitized:
            return JSONResponse({'error': 'Invalid video name'}, status_code=400)
        print(f"[COMBINED API] Starting combined process for video: {video_name_sanitized}")
        # Step 1: Process audio
        if audio_file:
            filename = audio_file.filename
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            with open(filepath, 'wb') as f:
                f.write(await audio_file.read())
            print(f"[COMBINED API] Saved uploaded file: {filepath}")
        else:
            filename, filepath = download_audio_file(audio_url)
            print(f"[COMBINED API] Downloaded file: {filepath}")
        # Transcribe audio
        print(f"[COMBINED API] Transcribing audio...")
        sentence_segments, word_segments = transcribe_audio(filepath)
        # Create SRT files
        srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
        srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
        word_srt_filepath = os.path.join(TRANSCRIPTS_FOLDER, word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        # Create segments file
        audio_segments = create_audio_segments(sentence_segments, 15)
        segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
        segments_filepath = os.path.join(SEGMENTS_FOLDER, segments_filename)
        create_segments_file(audio_segments, segments_filepath)
        print(f"[COMBINED API] Audio processing completed")
        # Step 2: Generate images
        print(f"[COMBINED API] Generating images with optimized parallel processing...")
        try:
            result = subprocess.run(['venv/bin/python', 'generate_images_ideogram_optimized.py'], capture_output=True, text=True, check=True)
            print(f"[COMBINED API] Image generation completed with optimization")
        except Exception as e:
            print(f"[COMBINED API] Image generation failed: {e}")
        # Step 3: Add highlights
        print(f"[COMBINED API] Adding highlights...")
        try:
            result = subprocess.run(['python3', 'gpt_highlight_bullets.py'], capture_output=True, text=True, check=True)
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
        output_video = os.path.join(UPLOAD_FOLDER, f"{video_name_sanitized}.mp4")
        video_gen.generate_video(segments_filepath, word_srt_filepath, filepath, output_video, show_subtitles=(show_subtitles.lower() == 'true'), selected_background=selected_bg)
        print(f"[COMBINED API] Video generated successfully: {output_video}")
        # --- Calculate and save heygen_empty_spaces.json ---
        try:
            try:
                title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
                body_font = ImageFont.truetype(FONT_PATH, BODY_FONT_SIZE)
            except Exception:
                title_font = ImageFont.load_default()
                body_font = ImageFont.load_default()
            with open(SLIDES_JSON_PATH, 'r', encoding='utf-8') as f:
                slides = json.load(f)
            empty_spaces = []
            for slide in slides:
                result = calculate_empty_space(slide, title_font, body_font)
                if result:
                    empty_spaces.append(result)
            with open('heygen_empty_spaces.json', 'w', encoding='utf-8') as f:
                json.dump(empty_spaces, f, indent=2)
            print(f"[COMBINED API] Identified empty spaces for {len(empty_spaces)} slides (formats 2 & 3). Saved to heygen_empty_spaces.json.")
        except Exception as e:
            print(f"[COMBINED API] Empty space detection failed: {e}")
        # --- Overlay HeyGen avatar videos in empty spaces ---
        try:
            heygen_output_dir = 'heygen_videos'
            os.makedirs(heygen_output_dir, exist_ok=True)
            s3_links_path = os.path.join(heygen_output_dir, 's3_links.txt')
            with open(s3_links_path, 'w') as f:
                f.write('')
            S3_BUCKET = os.getenv('S3_BUCKET_NAME')
            heygen_api_key = os.getenv('HEYGEN_API_KEY')
            heygen_avatar_id = 'Jocelyn_sitting_office_side'
            audio_file_path = filepath
            with open('heygen_empty_spaces.json', 'r', encoding='utf-8') as f:
                empty_spaces = json.load(f)
            if not empty_spaces:
                print("[COMBINED API] No empty spaces found for HeyGen overlays")
                overlay_filename = None
            else:
                print(f"[COMBINED API] Found {len(empty_spaces)} slides for HeyGen avatar overlays")
                segments_file = segments_filepath
                with open(segments_file, 'r', encoding='utf-8') as f:
                    segments_data = json.load(f)
                segments = segments_data.get('segments', [])
                if not heygen_api_key or heygen_api_key == 'YOUR_HEYGEN_API_KEY':
                    print("[COMBINED API] HeyGen API key not configured, skipping avatar overlays")
                    overlay_filename = None
                elif not S3_BUCKET:
                    print("[COMBINED API] S3 bucket not configured, skipping avatar overlays")
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
                    print(f"[COMBINED API] Generating HeyGen videos for {len(slide_segments)} slides...")
                    for slide in slide_segments:
                        slide_number = slide.get('slide_number')
                        start_time = slide.get('start_time')
                        end_time = slide.get('end_time')
                        min_dim, max_dim = 128, 4096
                        width = int(slide['empty_space']['width'])
                        height = int(slide['empty_space']['height'])
                        heygen_width = max(min_dim, min(width, max_dim))
                        heygen_height = max(min_dim, min(height, max_dim))
                        print(f"[COMBINED API] Extracting and uploading audio for slide {slide_number}...")
                        audio = AudioSegment.from_file(audio_file_path)
                        segment_audio = audio[start_time * 1000:end_time * 1000]
                        segment_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_audio.mp3')
                        segment_audio.export(segment_path, format='mp3')
                        s3_key = f'heygen_segments/slide_{slide_number}_audio.mp3'
                        s3_url = upload_file_to_s3(segment_path, s3_key, bucket_name=S3_BUCKET)
                        if s3_url:
                            with open(s3_links_path, 'a') as f:
                                f.write(s3_url + '\n')
                        if not s3_url:
                            print(f"[COMBINED API] Failed to upload audio for slide {slide_number}")
                            continue
                        post_headers = {
                            'Authorization': f'Bearer {heygen_api_key}',
                            'Content-Type': 'application/json',
                        }
                        payload = {
                            "video_inputs": [
                                {
                                    "character": {
                                        "type": "avatar",
                                        "avatar_id": heygen_avatar_id
                                    },
                                    "voice": {
                                        "type": "audio",
                                        "audio_url": s3_url
                                    }
                                }
                            ]
                        }
                        try:
                            resp = requests.post("https://api.heygen.com/v2/video/generate", json=payload, headers=post_headers)
                            resp.raise_for_status()
                            data = resp.json()
                            video_id = data['data']['video_id']
                            print(f'[COMBINED API] Video requested, id: {video_id}')
                        except Exception as e:
                            print(f'[COMBINED API] HeyGen API error for slide {slide_number}: {e}')
                            continue
                        status_url = f'https://api.heygen.com/v1/video_status.get?video_id={video_id}'
                        get_headers = {
                            'accept': 'application/json',
                            'x-api-key': heygen_api_key,
                        }
                        time.sleep(5)
                        poll_count = 0
                        video_url = None
                        while True:
                            try:
                                status_resp = requests.get(status_url, headers=get_headers)
                                if status_resp.status_code == 404:
                                    print(f'[{poll_count}] Video not found yet, retrying...')
                                    time.sleep(3)
                                    poll_count += 1
                                    continue
                                status_resp.raise_for_status()
                                status_json = status_resp.json()
                                print(f'[{poll_count}] Full response: {status_json}')
                                status = status_json['data']['status']
                                if status == 'completed':
                                    video_url = status_json['data']['video_url']
                                    print(f'[COMBINED API] Video ready at: {video_url}')
                                    break
                                elif status == 'failed':
                                    print(f'[COMBINED API] HeyGen video generation failed for slide {slide_number}. Status response: {status_json}')
                                    break
                                print(f'[{poll_count}] Current status: {status}')
                            except requests.exceptions.RequestException as e:
                                print(f'Error polling status: {e}')
                            time.sleep(5)
                            poll_count += 1
                        if not video_url:
                            continue
                        try:
                            parsed_url = urlparse(video_url)
                            base_name = os.path.basename(parsed_url.path)
                            video_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen.mp4')
                            with requests.get(video_url, stream=True) as r:
                                r.raise_for_status()
                                with open(video_path, 'wb') as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        f.write(chunk)
                            print(f'[COMBINED API] HeyGen video downloaded to: {video_path}')
                        except Exception as e:
                            print(f'[COMBINED API] Error downloading HeyGen video for slide {slide_number}: {e}')
                            continue
                        try:
                            heygen_clip = VideoFileClip(video_path)
                            noaudio_clip = heygen_clip.without_audio()
                            noaudio_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio.mp4')
                            noaudio_clip.write_videofile(noaudio_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
                            heygen_clip.close()
                            noaudio_clip.close()
                            resized_clip = VideoFileClip(noaudio_path)
                            orig_w, orig_h = resized_clip.size
                            target_w, target_h = width, height
                            scale = min(target_w / orig_w, target_h / orig_h)
                            new_w, new_h = int(orig_w * scale), int(orig_h * scale)
                            resized_clip = resized_clip.resize((new_w, new_h))
                            resized_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio_resized.mp4')
                            resized_clip.write_videofile(resized_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
                            resized_clip.close()
                            os.remove(noaudio_path)
                        except Exception as e:
                            print(f'[COMBINED API] Error processing HeyGen video for slide {slide_number}: {e}')
                            continue
                    print('[COMBINED API] Overlaying HeyGen videos on main video...')
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
                            target_w = int(space['width'])
                            target_h = int(space['height'])
                            slide_format = slide.get('format', 2)
                            heygen_vid_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio_resized.mp4')
                            if not os.path.exists(heygen_vid_path):
                                print(f'[COMBINED API] Warning: HeyGen video not found for slide {slide_number}, skipping overlay for this slide.')
                                continue
                            try:
                                overlay_clip = VideoFileClip(heygen_vid_path)
                                ow, oh = overlay_clip.size
                                if slide_format == 2:
                                    pos_x = x + (target_w - ow)
                                else:
                                    pos_x = x
                                pos_y = y + (target_h - oh) // 2
                                heygen_clip = overlay_clip.set_start(start).set_end(end).set_position((pos_x, pos_y))
                                overlays.append(heygen_clip)
                            except Exception as e:
                                print(f'[COMBINED API] Error loading overlay for slide {slide_number}: {e}')
                        if overlays:
                            final = CompositeVideoClip([main_video] + overlays, size=main_video.size)
                            overlay_output = os.path.join(UPLOAD_FOLDER, f"heygen_overlay_{video_name_sanitized}.mp4")
                            final.write_videofile(overlay_output, codec='libx264', audio_codec='aac', fps=main_video.fps, threads=4, verbose=False, logger=None)
                            final.close()
                            overlay_filename = os.path.basename(overlay_output)
                            print(f'[COMBINED API] Final video with HeyGen overlays saved: {overlay_output}')
                        else:
                            print('[COMBINED API] No HeyGen overlays to apply.')
                            overlay_filename = None
                        main_video.close()
                    except Exception as e:
                        print(f'[COMBINED API] Error during HeyGen overlay: {e}')
                        overlay_filename = None
        except Exception as e:
            print(f"[COMBINED API] HeyGen overlay step failed: {e}")
            overlay_filename = None
        return JSONResponse({
            'success': True,
            'video_filename': os.path.basename(output_video),
            'overlay_video_filename': overlay_filename,
            'overlay_video_preview_url': f"/download_video/{overlay_filename}" if overlay_filename else None,
            'message': 'Complete video generated successfully'
        })
    except Exception as e:
        print(f"[COMBINED API ERROR] Process failed: {e}")
        return JSONResponse({'error': str(e)}, status_code=500) 