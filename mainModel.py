import os
import re
import random
import uuid
import requests
import time
from typing import Optional, Tuple
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydub import AudioSegment
import json
from video_generator import VideoGenerator
import sys
from urllib.parse import urlparse
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Fix PIL ANTIALIAS compatibility issue
try:
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS
    print("[PIL] ANTIALIAS compatibility fix applied")
except Exception as e:
    print(f"[PIL] Warning: Could not apply ANTIALIAS fix: {e}")

from openai import OpenAI
import difflib
import concurrent.futures
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import BGM processor
from bgm_processor import BGMProcessor

# Supabase integration removed - using container concurrency for session management

# Load environment variables
load_dotenv()

# Constants and folders
UPLOAD_FOLDER = 'uploads'
TRANSCRIPTS_FOLDER = 'transcripts'
SEGMENTS_FOLDER = 'segments'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'aac', 'ogg'}

# Create base folders
for folder in [UPLOAD_FOLDER, TRANSCRIPTS_FOLDER, SEGMENTS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def create_session_directories(session_id: str):
    """Create unique directories for each request session to handle concurrency"""
    session_uploads = os.path.join(UPLOAD_FOLDER, session_id)
    session_transcripts = os.path.join(TRANSCRIPTS_FOLDER, session_id)
    session_segments = os.path.join(SEGMENTS_FOLDER, session_id)
    
    for folder in [session_uploads, session_transcripts, session_segments]:
        if not os.path.exists(folder):
            os.makedirs(folder)
    
    return session_uploads, session_transcripts, session_segments

def cleanup_session_files(session_id: str):
    """Clean up temporary files for a session"""
    try:
        session_uploads = os.path.join(UPLOAD_FOLDER, session_id)
        session_transcripts = os.path.join(TRANSCRIPTS_FOLDER, session_id)
        session_segments = os.path.join(SEGMENTS_FOLDER, session_id)
        
        for folder in [session_uploads, session_transcripts, session_segments]:
            if os.path.exists(folder):
                import shutil
                shutil.rmtree(folder)
    except Exception as e:
        print(f"[WARNING] Failed to cleanup session {session_id}: {e}")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID") or "ftDdhfYtmfGP0tFlBYA1"

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# Constants - Original 1920x1080 resolution
SLIDES_JSON_PATH = 'segments/slides.json'
FONT_PATH = 'circular-std-font-family/CircularStd-Book.ttf'
TITLE_FONT_SIZE = 72  # Original font size
BODY_FONT_SIZE = 36   # Original font size
SLIDE_WIDTH = 1920  # Original resolution
SLIDE_HEIGHT = 1080   # Original resolution
LEFT_MARGIN = 80
TOP_MARGIN = 120
BULLET_SPACING = 44
SUBTITLE_HEIGHT = 60
# --- HeyGen Avatar Configuration ---
MIN_AVATAR_SIZE = 185  # Minimum avatar size in pixels
MAX_AVATAR_SIZE = 250  # Maximum avatar size in pixels  
AVATAR_SAFETY_MARGIN = 20  # Safety margin from text
BOTTOM_MARGIN = 80

# --- HeyGen Overlay Constants ---
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

# --- HeyGen Overlay Helper Functions ---
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
        print(f"[HEYGEN SKIP] Slide {slide.get('slide_number')}: format {format_type} not supported (only 2,3), skipping overlay")
        return None
    
    title = slide.get('title', '')
    bullets = slide.get('bullets', [])
    
    # 🎯 NEW RULE: Skip HeyGen avatar if slide has more than 4 bullets
    if len(bullets) > 4:
        print(f"[HEYGEN SKIP] Slide {slide.get('slide_number')}: too many bullets ({len(bullets)} > 4), skipping overlay")
        return None
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
    
    # 🎯 FIXED: Always start at the bottom, not where bullets end
    empty_space_top = subtitle_y - MIN_AVATAR_SIZE - AVATAR_SAFETY_MARGIN
    empty_space_bottom = subtitle_y
    empty_space_height = max(0, empty_space_bottom - empty_space_top)
    
    # 🎯 ENHANCED: Check if available height is sufficient for minimum avatar size
    if empty_space_height < MIN_AVATAR_SIZE + AVATAR_SAFETY_MARGIN:
        print(f"[HEYGEN SKIP] Slide {slide.get('slide_number')}: insufficient height ({empty_space_height}px < {MIN_AVATAR_SIZE + AVATAR_SAFETY_MARGIN}px), skipping overlay")
        return None
    
    # 🎯 FIXED: Correct positioning logic for extreme left/right
    if format_type == 2:
        # Format 2: Extreme LEFT
        x = LEFT_MARGIN
        max_width = SLIDE_WIDTH // 2 - 2 * LEFT_MARGIN
        position_info = "EXTREME LEFT"
    else:  # format_type == 3
        # Format 3: Extreme RIGHT  
        x = SLIDE_WIDTH // 2 + (SLIDE_WIDTH // 2 - MIN_AVATAR_SIZE - LEFT_MARGIN)
        max_width = SLIDE_WIDTH // 2 - 2 * LEFT_MARGIN
        position_info = "EXTREME RIGHT"
    
    # 🎯 NEW: Check if text content overlaps with avatar area
    avatar_area_top = empty_space_top
    avatar_area_bottom = empty_space_top + MIN_AVATAR_SIZE
    avatar_area_left = x
    avatar_area_right = x + MIN_AVATAR_SIZE
    
    # Check if any text content overlaps with the avatar area
    text_overlaps_avatar = False
    
    # Check title overlap
    title_bottom = TOP_MARGIN
    for line in title_lines:
        title_bottom += title_font.size + 10
    title_bottom += 120  # Spacing after title
    
    if title_bottom > avatar_area_top:
        print(f"[HEYGEN SKIP] Slide {slide.get('slide_number')}: title overlaps with avatar area (title ends at {title_bottom}px, avatar starts at {avatar_area_top}px)")
        return None
    
    # Check bullets overlap
    current_y = title_bottom
    for bullet in bullets:
        bullet_lines = wrap_text(bullet, body_font, max_text_width, draw)
        for line in bullet_lines:
            current_y += body_font.size + 8
        current_y += 24
        
        # If bullets extend into avatar area, skip HeyGen
        if current_y > avatar_area_top:
            print(f"[HEYGEN SKIP] Slide {slide.get('slide_number')}: bullets overlap with avatar area (bullets end at {current_y}px, avatar starts at {avatar_area_top}px)")
            return None
    
    # 🎯 ENHANCED: Calculate optimal avatar size within our range
    avatar_size = min(max_width, empty_space_height - AVATAR_SAFETY_MARGIN, MAX_AVATAR_SIZE)
    avatar_size = max(avatar_size, MIN_AVATAR_SIZE)  # Ensure minimum size
    
    # 🎯 ENHANCED: Final size validation with detailed debug
    if avatar_size < MIN_AVATAR_SIZE:
        print(f"[HEYGEN SKIP] Slide {slide.get('slide_number')}: calculated avatar too small ({avatar_size}px < {MIN_AVATAR_SIZE}px), skipping overlay")
        return None
    elif avatar_size > MAX_AVATAR_SIZE:
        print(f"[HEYGEN ADJUST] Slide {slide.get('slide_number')}: avatar too large ({avatar_size}px > {MAX_AVATAR_SIZE}px), reducing to {MAX_AVATAR_SIZE}px")
        avatar_size = MAX_AVATAR_SIZE
    
    # Use calculated avatar size
    width = avatar_size
    height = avatar_size
    
    # 🎯 ENHANCED: Detailed debug information
    print(f"[HEYGEN CALC] Slide {slide.get('slide_number')}: format={format_type}, position={position_info}")
    print(f"[HEYGEN CALC] Avatar: size={avatar_size}px, x={x}, y={empty_space_top}")
    print(f"[HEYGEN CALC] Available: height={empty_space_height}px, max_width={max_width}px")
    
    return {
        'slide_number': slide.get('slide_number'),
        'format': format_type,
        'empty_space': {
            'x': x,
            'y': empty_space_top,
            'width': width,
            'height': height
        }
    }

def upload_video_to_s3(video_path: str, filename: str) -> Optional[str]:
    """Upload video to S3 and return the URL"""
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_DEFAULT_REGION
        )
        s3.upload_file(video_path, S3_BUCKET_NAME, filename, ExtraArgs={'ContentType': 'video/mp4'})
        return f"https://{S3_BUCKET_NAME}.s3.{AWS_DEFAULT_REGION}.amazonaws.com/{filename}"
    except Exception as e:
        print(f"Error uploading video to S3: {e}")
        return None

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
        # Log audio file path and size
        file_size = os.path.getsize(audio_path)
        print(f"[DEBUG] Transcribing file: {audio_path} (size: {file_size} bytes)")
        # Use OpenAI Whisper API instead of local model
        client = get_openai_client()
        with open(audio_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
        # Print the raw API response as JSON
        try:
            print("[DEBUG] OpenAI Whisper API response (JSON):", json.dumps(result.model_dump(), indent=2))
        except Exception as e:
            print(f"[DEBUG] Could not dump API response as JSON: {e}")
            print("[DEBUG] Raw API response:", result)
        # If segments are present and not None, use them
        if result and hasattr(result, 'segments') and result.segments:
            sentence_segments = []
            for segment in result.segments:
                sentence_segments.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text.strip()
                })
            word_segments = []
            for segment in result.segments:
                words = segment.text.strip().split()
                if words:
                    total_duration = segment.end - segment.start
                    time_per_word = total_duration / len(words)
                    for i, word in enumerate(words):
                        word_start = segment.start + (i * time_per_word)
                        word_end = segment.start + ((i + 1) * time_per_word)
                        word_segments.append({
                            'start': word_start,
                            'end': word_end,
                            'text': word.strip()
                        })
            # Get the actual audio duration from the words
            audio_duration = result.words[-1].end if result.words else 0
            print(f"[DEBUG] Audio duration from words: {audio_duration:.2f}s")
            
            return sentence_segments, word_segments, audio_duration
        # If segments is None but words and text are present, use those
        elif hasattr(result, 'words') and result.words and hasattr(result, 'text') and result.text:
            print("[DEBUG] Falling back to words/text fields for sentence/word segments.")
            
            # Get the actual audio duration from the words
            audio_duration = result.words[-1].end if result.words else 0
            print(f"[DEBUG] Audio duration from words: {audio_duration:.2f}s")
            
            # Split the text into sentences and create sentence segments
            import re
            sentences = re.split(r'[.!?]+', result.text.strip())
            sentences = [s.strip() for s in sentences if s.strip()]
            
            if sentences:
                # Distribute sentences across the audio duration
                sentence_segments = []
                time_per_sentence = audio_duration / len(sentences)
                
                for i, sentence in enumerate(sentences):
                    start_time = i * time_per_sentence
                    end_time = (i + 1) * time_per_sentence
                    sentence_segments.append({
                        'start': start_time,
                        'end': end_time,
                        'text': sentence
                    })
                
                print(f"[DEBUG] Created {len(sentence_segments)} sentence segments from words/text fallback")
            else:
                # If no sentences found, create one segment spanning the entire duration
                sentence_segments = [{
                    'start': result.words[0].start if result.words else 0,
                    'end': result.words[-1].end if result.words else 0,
                    'text': result.text.strip()
                }]
                print("[DEBUG] Created single sentence segment from words/text fallback")
            
            # Create word segments from the words
            word_segments = []
            for word in result.words:
                word_segments.append({
                    'start': word.start,
                    'end': word.end,
                    'text': word.word.strip()
                })
            
            return sentence_segments, word_segments, audio_duration
        else:
            print("[DEBUG] No segments or words found in Whisper API response.")
            print("[DEBUG] Full API response:", result)
            raise Exception("No transcript found")
    except Exception as e:
        print(f"[DEBUG] Exception in transcribe_audio: {e}")
        raise Exception(f"Error transcribing audio: {str(e)}")

def create_audio_segments(sentence_segments, segment_duration=15):
    """
    Create audio segments with smart logic to avoid very short final segments.
    If the remaining time is less than 10 seconds, merge it with the previous segment.
    """
    if not sentence_segments:
        return []
    
    total_duration = sentence_segments[-1]['end']
    segments = []
    segment_start = 0
    
    while segment_start < total_duration:
        # Calculate the end time for this segment
        segment_end = min(segment_start + segment_duration, total_duration)
        
        # Check if this would be the last segment and if it's too short
        remaining_time = total_duration - segment_start
        
        # If remaining time is less than 10 seconds and we already have segments,
        # merge the remaining content with the last segment instead of creating a new one
        if remaining_time < 10 and segments:
            print(f"[DEBUG] Remaining time ({remaining_time:.1f}s) is less than 10s, merging with previous segment")
            # Extend the last segment to include all remaining content
            last_segment = segments[-1]
            last_segment['end'] = total_duration
            
            # Add remaining text to the last segment
            remaining_text = ""
            for sentence in sentence_segments:
                sentence_start = sentence['start']
                sentence_end = sentence['end']
                if (sentence_start >= segment_start and sentence_end <= total_duration):
                    if remaining_text:
                        remaining_text += " " + sentence['text']
                    else:
                        remaining_text = sentence['text']
            
            if remaining_text.strip():
                if last_segment['text']:
                    last_segment['text'] += " " + remaining_text.strip()
                else:
                    last_segment['text'] = remaining_text.strip()
            
            # Update sentences list for the last segment
            last_segment['sentences'] = [s for s in sentence_segments if s['start'] < total_duration and s['end'] > last_segment['start']]
            break
        
        # Normal segment creation
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
    
    # Log segment information
    print(f"[DEBUG] Created {len(segments)} segments:")
    for i, seg in enumerate(segments):
        duration = seg['end'] - seg['start']
        print(f"[DEBUG] Segment {i+1}: {seg['start']:.1f}s - {seg['end']:.1f}s (duration: {duration:.1f}s)")
    
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

def preprocess_script_for_tts(script: str) -> str:
    """
    Replace company names and tricky words with phonetic/alternate spellings for better TTS pronunciation.
    Extend the replacements dictionary as needed.
    """
    replacements = {
        # Example: 'AcmeCorp' is pronounced as 'Ack-mee Corp'
        'AcmeCorp': 'Ack-mee Corp',
        'NeuroTemp': 'Neuron Temp',
        'OpenAI': 'Open A I',
        # Add more company/product names as needed
    }
    for original, replacement in replacements.items():
        script = script.replace(original, replacement)
    return script

def generate_audio_from_script(text: str, speed: float = 1.0, voice_id: str = "ftDdhfYtmfGP0tFlBYA1", stability: float = 0.35, similarity_boost: float = 0.40) -> Tuple[str, str]:
    if not ELEVENLABS_API_KEY:
        raise Exception("ELEVENLABS_API_KEY not set in environment.")
    if not voice_id:
        voice_id = ELEVENLABS_DEFAULT_VOICE_ID
    # Preprocess script for TTS pronunciation
    text = preprocess_script_for_tts(text)
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


def upload_file_to_s3(local_file_path, s3_key, bucket_name=None, acl='public-read'):
    bucket = bucket_name or S3_BUCKET_NAME
    s3 = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_DEFAULT_REGION
    )
    try:
        s3.upload_file(local_file_path, bucket, s3_key, ExtraArgs={'ContentType': 'audio/mpeg'})
        url = f'https://{bucket}.s3.{AWS_DEFAULT_REGION}.amazonaws.com/{s3_key}'
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

# Helper to get OpenAI client
def get_openai_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_environment_prompt_for_target_audience(target_audience: str) -> str:
    """Generate dynamic environment prompt based on target audience"""
    client = get_openai_client()
    
    prompt = f'''
You are an expert at creating detailed, photorealistic image prompts for different professional environments.

Given the target audience: "{target_audience}", create a comprehensive environment prompt that includes:

1. **Professional Setting**: Describe the specific workplace environment (office, factory, hospital, retail store, etc.)
2. **Character Requirements**: Describe the professionals who would work in this environment
3. **Environment Details**: Include specific equipment, furniture, lighting, and atmosphere
4. **Cultural Context**: If applicable, include relevant cultural or regional elements
5. **Professional Atmosphere**: Describe the mood and tone appropriate for this workplace

**Requirements:**
- Be specific and detailed
- Focus on photorealistic, professional visuals
- Include diverse professionals appropriate for the environment
- Describe the setting, lighting, and atmosphere
- Make it suitable for corporate training/educational content
- Keep it under 200 words

**Example format:**
"Professional setting with specific details, diverse professionals in appropriate attire, environment description with equipment/furniture, natural/artificial lighting, professional atmosphere, photorealistic quality"

Target Audience: {target_audience}

Return ONLY the environment prompt, no explanations or additional text.
'''
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert at creating detailed environment prompts for professional settings."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=300,
        temperature=0.3
    )
    
    environment_prompt = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
    
    # Fallback if no response
    if not environment_prompt:
        environment_prompt = f"Professional {target_audience} environment with diverse professionals, modern equipment, natural lighting, clean and organized workspace, photorealistic quality"
    
    return environment_prompt

# Function to generate slide JSON content using GPT-4o
def generate_slide_json_content(segment_text, segment_index, segment_duration, segment_title=None, previous_format=None, target_audience=None):
    client = get_openai_client()
    
    prompt = f'''
You are a presentation expert specializing in creating dynamic, context-aware slides.

Given the following transcript segment and its duration, output a single JSON object for the slide with these fields:
- slide_number (integer)
- format (integer, 2-4)
- title (string)
- bullets (array of strings, each may contain <highlight> tags, or empty array if not needed)
- image_prompt (string, required for all formats 2, 3, or 4; do NOT include the word 'ideogram')

**CRITICAL FORMAT RULE:**
- You MUST randomly select a format number between 2-4 for each slide
- NEVER use the same format as the previous slide (previous_format={previous_format})
- If previous_format is {previous_format}, choose ANY format except {previous_format}
- Do NOT use format 1 or format 5. Do NOT favor any particular format - truly randomize your choice

**SLIDE-CONTENT-FOCUSED IMAGE GENERATION:**

**PRINCIPLE: The image should directly represent what the slide is talking about.**

**ANALYZE THE SLIDE CONTENT:**
- What is the main topic being discussed?
- What specific objects, concepts, or processes are mentioned?
- What would help the audience understand this content visually?

**CREATE IMAGE PROMPT:**
- **Focus on the actual content** of the slide
- **Show what the slide is talking about**
- **Make it appropriate for the target audience** (simpler for younger audiences, more detailed for professionals)
- **Use clear, high-quality visuals** that help explain the content

**TARGET AUDIENCE: {target_audience or "General professional"}**

**AUDIENCE ADJUSTMENTS:**
- **Professional/Adult**: Detailed, clean, professional quality
- **High School**: Clear, educational, age-appropriate detail
- **Elementary**: Simple, colorful, easy to understand
- **University**: Academic, comprehensive, detailed

**EXAMPLES:**

**Slide Content:** "The brain processes information through neural networks."
**Image Prompt:** "Brain neural network diagram, detailed neural connections, information processing visualization, professional quality, photorealistic"

**Slide Content:** "Supply chains connect manufacturers to consumers."
**Image Prompt:** "Supply chain flowchart, manufacturing to consumer process, business connection diagram, professional quality, photorealistic"

**Slide Content:** "Photosynthesis converts sunlight into energy."
**Image Prompt:** "Plant photosynthesis diagram, sunlight to energy conversion, natural process visualization, professional quality, photorealistic"

**Slide Content:** "Customer feedback improves product quality."
**Image Prompt:** "Customer feedback loop diagram, product improvement process, quality enhancement visualization, professional quality, photorealistic"

**QUALITY REQUIREMENTS:**
- **Directly related to slide content**
- **Clear, understandable visuals**
- **High-quality, photorealistic**
- **Appropriate complexity for target audience**
- **No generic people or office scenes**

**YOUR TASK:**
Analyze this slide content and create an image prompt that directly represents what the slide is talking about:

Transcript:
"""{segment_text}"""
Duration: {segment_duration:.2f} seconds
Title: {segment_title or f"Slide {segment_index+1}"}
Target Audience: {target_audience or "General professional"}

Create an image prompt that shows exactly what this slide is discussing, with appropriate complexity for the target audience.
'''
    def try_parse_json(raw):
        import json
        try:
            return json.loads(raw)
        except Exception:
            import re
            cleaned = re.sub(r'```json|```', '', raw).strip()
            try:
                return json.loads(cleaned)
            except Exception:
                return None

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a presentation content expert. Output only the JSON object, no commentary."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=700,
        temperature=0.4
    )
    raw_json = response.choices[0].message.content.strip() if response.choices[0].message.content and response.choices[0].message.content.strip() else ""
    slide_json = try_parse_json(raw_json)
    if slide_json is None:
        fix_prompt = f"Fix this JSON and return only the corrected JSON object, no commentary:\n{raw_json}"
        fix_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a JSON fixer. Output only the corrected JSON object, no commentary."},
                {"role": "user", "content": fix_prompt}
            ],
            max_tokens=700,
            temperature=0.2
        )
        fixed_json = fix_response.choices[0].message.content.strip() if fix_response.choices[0].message.content and fix_response.choices[0].message.content.strip() else ""
        slide_json = try_parse_json(fixed_json)
        if slide_json is None:
            raise Exception(f"Failed to parse/fix JSON for segment {segment_index}. Raw: {raw_json}")
    return slide_json

# Function to create slides.json from segments

def create_slides_json_from_segments(segments, slides_json_path, target_audience=None):
    """Create slides.json from pre-created segments (with 'format' field)"""
    slides = []
    total_segments = len(segments)
    previous_format = None
    print(f"[DEBUG] Creating {total_segments} slides from segments")
    if target_audience:
        print(f"[DEBUG] Using target audience: {target_audience}")
    for i, segment in enumerate(segments):
        percent = int((i+1)/total_segments*100)
        duration = segment['end'] - segment['start']
        format_type = segment.get('format', None)
        print(f"Generating slide JSON for segment {i+1}/{total_segments} ({percent}%) - Duration: {duration:.1f}s, Format: {format_type}", flush=True)
        slide_json = generate_slide_json_content(segment['text'], i, duration, previous_format=previous_format, target_audience=target_audience)
        # Overwrite the format in slide_json to match the pre-assigned format
        if format_type is not None:
            slide_json['format'] = format_type
        previous_format = format_type
        slides.append(slide_json)
    print(f"[DEBUG] Created {len(slides)} slides from segments")
    with open(slides_json_path, 'w', encoding='utf-8') as f:
        import json
        json.dump(slides, f, indent=2, ensure_ascii=False)
    print(f"Slides JSON saved: {slides_json_path}")

def parse_srt_to_segments(srt_content):
    """Parse SRT content back into segments for slide generation"""
    import re
    segments = []
    lines = srt_content.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or not line.isdigit():
            i += 1
            continue
        
        # Skip the sequence number
        i += 1
        if i >= len(lines):
            break
            
        # Parse timestamp
        if i < len(lines):
            timestamp_line = lines[i].strip()
            if ' --> ' in timestamp_line:
                start_time_str, end_time_str = timestamp_line.split(' --> ')
                start_time = parse_timestamp_to_seconds(start_time_str)
                end_time = parse_timestamp_to_seconds(end_time_str)
            else:
                i += 1
                continue
        else:
            break
            
        i += 1
        
        # Collect text lines
        text_lines = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1
            
        if text_lines:
            # Remove HTML tags from text
            text = ' '.join(text_lines)
            text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags like <b>
            text = text.strip()
            
            if text:
                segments.append({
                    'start': start_time,
                    'end': end_time,
                    'text': text
                })
        
        i += 1  # Skip empty line
    
    return segments

def parse_timestamp_to_seconds(timestamp):
    """Convert SRT timestamp (HH:MM:SS,mmm) to seconds"""
    try:
        time_part, ms_part = timestamp.split(',')
        h, m, s = map(int, time_part.split(':'))
        ms = int(ms_part)
        return h * 3600 + m * 60 + s + ms / 1000.0
    except:
        return 0.0

def create_slides_json_from_corrected_srt(corrected_sentence_srt, slides_json_path, target_audience=None, audio_duration=None):
    """Create slides.json from corrected SRT content with smart segment logic"""
    print("[DEBUG] Creating slides from corrected SRT content...")
    if target_audience:
        print(f"[DEBUG] Using target audience: {target_audience}")
    
    # Parse the corrected SRT back into segments
    corrected_segments = parse_srt_to_segments(corrected_sentence_srt)
    print(f"[DEBUG] Parsed {len(corrected_segments)} segments from corrected SRT")
    
    if not corrected_segments:
        print("[WARNING] No segments found in corrected SRT")
        return
    
    # Use audio_duration if provided, otherwise use SRT duration
    if audio_duration is not None:
        print(f"[DEBUG] Using provided audio duration: {audio_duration:.2f}s")
        total_duration = audio_duration
    else:
        total_duration = corrected_segments[-1]['end']
        print(f"[DEBUG] Using SRT duration: {total_duration:.2f}s")
    slides = []
    segment_start = 0
    segment_index = 0
    previous_format = None
    
    while segment_start < total_duration:
        # Calculate the end time for this segment
        segment_end = min(segment_start + 15, total_duration)
        
        # Check if this would be the last segment and if it's too short
        remaining_time = total_duration - segment_start
        
        # If remaining time is less than 10 seconds and we already have slides,
        # merge the remaining content with the last slide instead of creating a new one
        if remaining_time < 10 and slides:
            print(f"[DEBUG] Remaining time ({remaining_time:.1f}s) is less than 10s, merging with previous slide")
            # Extend the last slide to include all remaining content
            last_slide = slides[-1]
            
            # Add remaining text to the last slide
            remaining_text = ""
            for sentence in corrected_segments:
                sentence_start = sentence['start']
                sentence_end = sentence['end']
                if (sentence_start >= segment_start and sentence_end <= total_duration):
                    if remaining_text:
                        remaining_text += " " + sentence['text']
                    else:
                        remaining_text = sentence['text']
            
            if remaining_text.strip():
                # Update the slide content with merged text
                merged_text = last_slide.get('text', '') + " " + remaining_text.strip()
                print(f"Generating updated slide JSON for merged segment {segment_index} (extended duration)")
                updated_slide_json = generate_slide_json_content(merged_text.strip(), segment_index-1, total_duration - last_slide.get('start_time', segment_start-15), previous_format=previous_format, target_audience=target_audience)
                
                # Update the last slide with new content
                slides[-1] = updated_slide_json
            break
        
        # Normal slide creation
        segment_text = ""
        for sentence in corrected_segments:
            sentence_start = sentence['start']
            sentence_end = sentence['end']
            if (sentence_start < segment_end and sentence_end > segment_start):
                if segment_text:
                    segment_text += " " + sentence['text']
                else:
                    segment_text = sentence['text']
        
        if segment_text.strip():
            print(f"Generating slide JSON for corrected segment {segment_index+1} ({segment_start:.1f}s - {segment_end:.1f}s)")
            slide_json = generate_slide_json_content(segment_text.strip(), segment_index, segment_end - segment_start, previous_format=previous_format, target_audience=target_audience)
            previous_format = slide_json.get('format', previous_format)
            slides.append(slide_json)
            segment_index += 1
            
        segment_start = segment_end
    
    # Log slide information
    print(f"[DEBUG] Created {len(slides)} slides from corrected SRT")
    
    with open(slides_json_path, 'w', encoding='utf-8') as f:
        import json
        json.dump(slides, f, indent=2, ensure_ascii=False)
    print(f"Slides JSON saved from corrected SRT: {slides_json_path}")

def extract_proper_nouns(script):
    import re
    proper_nouns = set(re.findall(r'(?<![\.!?]\s)(?<!^)(\b[A-Z][a-zA-Z]+\b)', script))
    print(f"[DEBUG] Extracted proper nouns from script: {proper_nouns}")
    return proper_nouns

def correct_proper_nouns_in_transcript(proper_nouns, sentence_segments, word_segments):
    transcript_words = set(w['text'] for w in word_segments)
    print(f"[DEBUG] Transcript words before correction: {transcript_words}")
    for noun in proper_nouns:
        matches = difflib.get_close_matches(noun.lower(), [w.lower() for w in transcript_words], n=1, cutoff=0.8)
        print(f"[DEBUG] Fuzzy matches for '{noun}': {matches}")
        if matches:
            wrong = matches[0]
            print(f"[DEBUG] Replacing '{wrong}' with '{noun}' in transcripts.")
            for w in word_segments:
                if w['text'].lower() == wrong:
                    print(f"[DEBUG] Word-level: '{w['text']}' -> '{noun}'")
                    w['text'] = noun
            for s in sentence_segments:
                before = s['text']
                s['text'] = ' '.join([noun if word.lower() == wrong else word for word in s['text'].split()])
                if before != s['text']:
                    print(f"[DEBUG] Sentence-level: '{before}' -> '{s['text']}'")
    print(f"[DEBUG] Word segments after correction: {word_segments}")
    print(f"[DEBUG] Sentence segments after correction: {sentence_segments}")
    return sentence_segments, word_segments

# Image generation functions (integrated from generate_images_ideogram_optimized.py)
def generate_image_ideogram_optimized(prompt, aspect_ratio, slide_number):
    """Generate image using Ideogram 3.0 with optimized settings"""
    IDEOGRAM_API_KEY = os.getenv('IDEOGRAM_API_KEY')
    
    print(f"🎨 Generating image for slide {slide_number}...")
    
    try:
        # Optimized API call with faster settings
        response = requests.post(
            "https://api.ideogram.ai/v1/ideogram-v3/generate",
            headers={
                "Api-Key": IDEOGRAM_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "prompt": prompt,
                "rendering_speed": "TURBO",  # Fastest rendering
                "aspect_ratio": aspect_ratio,
                "quality": "standard"  # Faster than high quality
            },
            timeout=30  # Reduced timeout for faster failure detection
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Get the image URL from the response
        image_url = result['data'][0]['url']
        print(f"✅ Image generated for slide {slide_number}")
        
        # Download the image with optimized settings
        image_response = requests.get(
            image_url, 
            timeout=15,  # Faster timeout
            stream=True  # Stream for better memory management
        )
        image_response.raise_for_status()
        image_bytes = image_response.content
        
        return image_bytes, slide_number
        
    except Exception as e:
        print(f"❌ Error generating image for slide {slide_number}: {e}")
        return None, slide_number

def save_image_optimized(image_data, slide_info):
    """Save image bytes to file with progress tracking"""
    image_bytes, slide_number = image_data
    if image_bytes is None:
        return False, slide_number
    
    try:
        # Get format type from slide info
        format_type = slide_info.get('format', 2)
        filename = f"generated_images_ideogram/slide_{slide_number}_format_{format_type}.png"
        
        with open(filename, 'wb') as f:
            f.write(image_bytes)
        
        print(f"💾 Saved: {filename}")
        return True, slide_number
        
    except Exception as e:
        print(f"❌ Error saving image for slide {slide_number}: {e}")
        return False, slide_number

def process_slide_parallel(slide):
    """Process a single slide with image generation"""
    slide_number = slide['slide_number']
    format_type = slide['format']
    image_prompt = slide.get('image_prompt')
    
    # Skip slides without image prompts
    if not image_prompt:
        print(f"⏭️ Skipping slide {slide_number} (format {format_type}) - no image prompt")
        return None
    
    # Determine aspect ratio based on format
    if format_type in [2, 3]:
        aspect_ratio = "1x1"  # Square for formats 2 and 3
    elif format_type == 4:
        aspect_ratio = "16x9"  # Landscape for format 4
    else:
        print(f"⏭️ Skipping slide {slide_number} (format {format_type}) - no image needed")
        return None
    
    # Generate image
    image_data = generate_image_ideogram_optimized(image_prompt, aspect_ratio, slide_number)
    
    if image_data[0]:
        # Save image
        success, _ = save_image_optimized(image_data, slide)
        if success:
            print(f"✅ Slide {slide_number} completed")
        else:
            print(f"❌ Slide {slide_number} failed")
        return success
    else:
        print(f"❌ Slide {slide_number} failed")
        return False

def generate_images_from_slides(slides_json_path='segments/slides.json'):
    """Generate images for all slides that need them"""
    # Check if API key is available
    IDEOGRAM_API_KEY = os.getenv('IDEOGRAM_API_KEY')
    if not IDEOGRAM_API_KEY:
        print("❌ Error: IDEOGRAM_API_KEY not found in .env file")
        print("Please add your Ideogram API key to the .env file:")
        print("IDEOGRAM_API_KEY=your_api_key_here")
        return False
    
    # Load slides.json
    try:
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {slides_json_path} not found")
        return False
    
    # Create images directory if it doesn't exist
    os.makedirs('generated_images_ideogram', exist_ok=True)
    
    # Filter slides that need images
    slides_with_images = [slide for slide in slides if slide.get('image_prompt')]
    total_images = len(slides_with_images)
    
    print(f"🚀 Starting optimized image generation for {total_images} slides")
    print(f"⚡ Using parallel processing for faster generation")
    print("=" * 60)
    
    # Use ThreadPoolExecutor for parallel processing
    # Use up to 10 concurrent requests with GPU T4 for maximum performance
    max_workers = min(10, total_images)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_slide = {
            executor.submit(process_slide_parallel, slide): slide 
            for slide in slides_with_images
        }
        
        # Process completed tasks
        for future in as_completed(future_to_slide):
            slide = future_to_slide[future]
            try:
                result = future.result()
                if result:
                    print(f"✅ Completed: Slide {slide['slide_number']}")
                else:
                    print(f"❌ Failed: Slide {slide['slide_number']}")
            except Exception as e:
                print(f"❌ Exception for slide {slide['slide_number']}: {e}")
    
    print(f"\n🎉 Image generation complete!")
    print(f"📁 Check the 'generated_images_ideogram' folder for all generated images.")
    return True

# Highlight functions (integrated from gpt_highlight_bullets.py)
def add_highlights_to_slides(slides_json_path='segments/slides.json'):
    """Add highlights to slides (dummy logic for now)"""
    try:
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)
        
        # Dummy highlight logic for now: highlight the first word in the first bullet of each slide
        for slide in slides:
            bullets = slide.get('bullets', [])
            for i, bullet in enumerate(bullets):
                if '<highlight>' not in bullet and i == 0:
                    words = bullet.split()
                    if len(words) > 1:
                        words[1] = f'<highlight>{words[1]}</highlight>'
                        bullets[i] = ' '.join(words)
            slide['bullets'] = bullets
        
        with open(slides_json_path, 'w', encoding='utf-8') as f:
            json.dump(slides, f, ensure_ascii=False, indent=2)
        
        print('[DEBUG] Slides updated with highlights.')
        return True
    except Exception as e:
        print(f'[ERROR] Failed to add highlights: {e}')
        return False

def gpt_refactor_transcripts(script, sentence_segments, word_segments):
    client = get_openai_client()
    # Prepare prompt
    prompt = f'''
You are a transcript correction expert. Given the following user script and the audio transcript (both sentence-level and word-level), compare them and correct the transcript for proper nouns, company names, and any semantic errors. Use the script as the ground truth. Return the corrected sentence-level and word-level transcripts as .srt files.

User Script:
"""
{script}
"""

Sentence-level transcript (list of dicts with 'start', 'end', 'text'):
{json.dumps(sentence_segments, ensure_ascii=False, indent=2)}

Word-level transcript (list of dicts with 'start', 'end', 'text'):
{json.dumps(word_segments, ensure_ascii=False, indent=2)}

Return a JSON object with two keys: 'sentences' (corrected sentence segments) and 'words' (corrected word segments). Do not add any commentary.
'''
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a transcript correction expert."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=4096,
        temperature=0.0
    )
    import re
    import json as pyjson
    raw = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
    print("[DEBUG] Raw GPT response:\n" + raw)
    # Try to extract JSON from the response
    try:
        # Remove markdown if present
        if raw.startswith('```json'):
            raw = re.sub(r'^```json', '', raw)
        if raw.endswith('```'):
            raw = raw[:-3]
        data = pyjson.loads(raw)
        return data['sentences'], data['words']
    except Exception as e:
        print(f"[DEBUG] Failed to parse GPT response: {e}\nRaw: {raw}")
        raise Exception("Failed to parse GPT-corrected transcripts.")

def gpt_refactor_transcripts_srt(script, srt_sentence_content, srt_word_content):
    print("[DEBUG] GPT SRT correction function triggered.")
    client = get_openai_client()
    prompt = f'''
You are a transcript correction expert. Given the following user script and the audio transcript SRTs (sentence-level and word-level), compare them and correct the SRTs for proper nouns, company names, and any semantic errors. Use the script as the ground truth.

IMPORTANT: You must return the COMPLETE corrected SRT content for both files, clearly separated and labeled. Do not truncate or omit any content.

Return ONLY the corrected SRT content in this exact format:

---BEGIN SENTENCE SRT---
<complete corrected sentence-level SRT here>
---END SENTENCE SRT---

---BEGIN WORD SRT---
<complete corrected word-level SRT here>
---END WORD SRT---

Do not add any commentary, explanations, or extra text outside these markers.

User Script:
"""
{script}
"""

Sentence-level SRT:
{srt_sentence_content}

Word-level SRT:
{srt_word_content}
'''
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a transcript correction expert."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=8000,
        temperature=0.0
    )
    raw = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
    # Save raw GPT response to a test file for debugging
    test_path = os.path.join(TRANSCRIPTS_FOLDER, 'TEST_gpt_srt_response.txt')
    with open(test_path, 'w', encoding='utf-8') as f:
        f.write(raw)
    print(f"[DEBUG] GPT response length: {len(raw)} characters")
    
    import re
    # Extract the SRTs from the response with more robust parsing
    sentence_srt = ''
    word_srt = ''
    
    # Try to find sentence SRT
    m1 = re.search(r'---BEGIN SENTENCE SRT---(.*?)---END SENTENCE SRT---', raw, re.DOTALL)
    if m1:
        sentence_srt = m1.group(1).strip()
        print(f"[DEBUG] Found sentence SRT, length: {len(sentence_srt)} characters")
    else:
        print("[DEBUG] Could not find sentence SRT markers")
    
    # Try to find word SRT
    m2 = re.search(r'---BEGIN WORD SRT---(.*?)---END WORD SRT---', raw, re.DOTALL)
    if m2:
        word_srt = m2.group(1).strip()
        print(f"[DEBUG] Found word SRT, length: {len(word_srt)} characters")
    else:
        print("[DEBUG] Could not find word SRT markers")
        # Try to find partial word SRT (in case it was truncated)
        partial_match = re.search(r'---BEGIN WORD SRT---(.*)', raw, re.DOTALL)
        if partial_match:
            print("[DEBUG] Found partial word SRT (no end marker)")
            word_srt = partial_match.group(1).strip()
    
    if not sentence_srt:
        print(f"[DEBUG] No sentence SRT found. Raw response preview: {raw[:500]}...")
        raise Exception("Failed to extract sentence SRT from GPT response.")
    
    if not word_srt:
        print(f"[DEBUG] No word SRT found. Raw response preview: {raw[-500:] if len(raw) > 500 else raw}")
        raise Exception("Failed to extract word SRT from GPT response.")
    
    return sentence_srt, word_srt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple job status tracking (in-memory dict for now, can be replaced with persistent store)
job_status = {}

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
    target_audience: Optional[str] = Form(None),
    heygen_avatar_id: Optional[str] = Form(None),
    bgm_volume: Optional[int] = Form(50),  # BGM volume (1-100)
    bgm_crossfade: Optional[int] = Form(2000)  # Crossfade duration in milliseconds
):
    session_id = f"{video_name}_{uuid.uuid4().hex[:8]}"
    job_status[session_id] = {"status": "pending", "result": None, "error": None}
    def background_job(audio_file_content=None):
        try:
            job_status[session_id]["status"] = "processing"
            # Generate unique session ID for this request
            # session_id is already set
            session_uploads, session_transcripts, session_segments = create_session_directories(session_id)
            if not audio_file and not audio_url and not script:
                job_status[session_id]["status"] = "error"
                job_status[session_id]["error"] = "Please provide either an audio file, audio URL, or a script."
                return
            if not video_name:
                job_status[session_id]["status"] = "error"
                job_status[session_id]["error"] = "Video name is required"
                return
            video_name_clean = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
            if not video_name_clean:
                job_status[session_id]["status"] = "error"
                job_status[session_id]["error"] = "Invalid video name"
                return
            print(f"[COMBINED API] Starting combined process for video: {video_name_clean} (session: {session_id})")
            if audio_file_content is not None:
                filename = audio_file.filename or f"audio_{random.randint(1000,9999)}.mp3"
                filepath = os.path.join(session_uploads, filename)
                with open(filepath, "wb") as f:
                    f.write(audio_file_content)
                print(f"[COMBINED API] Saved uploaded file: {filepath}")
            elif audio_url:
                filename, filepath = download_audio_file(audio_url)
                if not filename:
                    filename = f"audio_{random.randint(1000,9999)}.mp3"
                if not filepath:
                    job_status[session_id]["status"] = "error"
                    job_status[session_id]["error"] = "Failed to download audio file."
                    return
                # Move downloaded file to session directory
                session_filepath = os.path.join(session_uploads, filename)
                import shutil
                shutil.move(filepath, session_filepath)
                filepath = session_filepath
                print(f"[COMBINED API] Downloaded file: {filepath}")
            elif script:
                use_speed = speed if speed is not None else 1.0
                use_voice_id = voice_id if voice_id else ELEVENLABS_DEFAULT_VOICE_ID
                use_stability = stability if stability is not None else 0.35
                use_similarity_boost = similarity_boost if similarity_boost is not None else 0.40
                filename, filepath = generate_audio_from_script(script, use_speed, use_voice_id, use_stability, use_similarity_boost)
                # Move generated file to session directory
                session_filepath = os.path.join(session_uploads, filename)
                import shutil
                shutil.move(filepath, session_filepath)
                filepath = session_filepath
                print(f"[COMBINED API] Generated audio from script: {filepath}")
            else:
                job_status[session_id]["status"] = "error"
                job_status[session_id]["error"] = "No valid audio input provided."
                return
            if not os.path.exists(filepath):
                job_status[session_id]["status"] = "error"
                job_status[session_id]["error"] = "Audio file not found after upload/generation."
                return
            print(f"[COMBINED API] Transcribing audio...")
            sentence_segments, word_segments, audio_duration = transcribe_audio(filepath)
            base_filename = filename.rsplit('.', 1)[0] if filename and '.' in filename else filename or f"audio_{random.randint(1000,9999)}"
            srt_filename = f"{base_filename}_sentences.srt"
            srt_filepath = os.path.join(session_transcripts, srt_filename)
            create_srt_file(sentence_segments, srt_filepath)
            word_srt_filename = f"{base_filename}_words.srt"
            word_srt_filepath = os.path.join(session_transcripts, word_srt_filename)
            create_word_srt_file(word_segments, word_srt_filepath)
            # If a script is provided, always run SRT correction after transcription (regardless of audio source)
            if script:
                print("[DEBUG] Sending SRTs and script to GPT for correction...")
                with open(srt_filepath, 'r', encoding='utf-8') as f:
                    srt_sentence_content = f.read()
                with open(word_srt_filepath, 'r', encoding='utf-8') as f:
                    srt_word_content = f.read()
                try:
                    corrected_sentence_srt, corrected_word_srt = gpt_refactor_transcripts_srt(script, srt_sentence_content, srt_word_content)
                except Exception as e:
                    print(f"[ERROR] GPT SRT correction failed: {e}")
                    return JSONResponse({"error": f"GPT SRT correction failed: {e}"}, status_code=500)
                # Overwrite the SRT files with the corrected SRTs
                with open(srt_filepath, 'w', encoding='utf-8') as f:
                    f.write(corrected_sentence_srt)
                with open(word_srt_filepath, 'w', encoding='utf-8') as f:
                    f.write(corrected_word_srt)
            
            # --- Ensure slides.json is generated ---
            slides_json_path = os.path.join(session_segments, 'slides.json')
            # If SRT correction was run, create slides and segments from corrected SRT
            if script:
                print("[DEBUG] Creating slides and segments from GPT-corrected SRT content...")
                corrected_segments = parse_srt_to_segments(corrected_sentence_srt)
                audio_segments = segment_transcript_variable_duration(corrected_segments, srt_filepath, audio_duration)
                create_slides_json_from_segments(audio_segments, slides_json_path, target_audience=target_audience)
            else:
                # Use original transcription for slides and segments
                print("[DEBUG] Creating slides and segments from original transcription...")
                audio_segments = segment_transcript_variable_duration(sentence_segments, srt_filepath, audio_duration)
                create_slides_json_from_segments(audio_segments, slides_json_path, target_audience=target_audience)
            # Create segments.json for video generation (always use the segments from above)
            segments_filename = f"{base_filename}_segments.json"
            segments_filepath = os.path.join(session_segments, segments_filename)
            segments_data = {
                "segments": [
                    {
                        "segment_id": i + 1,
                        "start_time": seg["start"] if isinstance(seg, dict) and "start" in seg else 0,
                        "end_time": seg["end"] if isinstance(seg, dict) and "end" in seg else 0,
                        "duration": (seg["end"] - seg["start"]) if isinstance(seg, dict) and "end" in seg and "start" in seg else 0,
                        "text": seg["text"] if isinstance(seg, dict) and "text" in seg else "",
                        "format": seg.get("format", None)
                    } for i, seg in enumerate(audio_segments) if isinstance(seg, dict)
                ]
            }
            with open(segments_filepath, 'w', encoding='utf-8') as f:
                json.dump(segments_data, f, indent=2, ensure_ascii=False)
            print(f"[COMBINED API] Audio processing completed")
            print(f"[COMBINED API] Generating images with optimized parallel processing...")
            try:
                success = generate_images_from_slides(slides_json_path)
                if success:
                    print(f"[COMBINED API] Image generation completed with optimization")
                else:
                    print(f"[COMBINED API] Image generation failed")
            except Exception as e:
                print(f"[COMBINED API] Image generation failed: {e}")
            print(f"[COMBINED API] Adding highlights...")
            try:
                success = add_highlights_to_slides(slides_json_path)
                if success:
                    print(f"[COMBINED API] Highlights added")
                else:
                    print(f"[COMBINED API] Highlight addition failed")
            except Exception as e:
                print(f"[COMBINED API] Highlight script failed: {e}")
            
            # --- BGM Processing ---
            print(f"[COMBINED API] Starting BGM processing...")
            try:
                # Process BGM directly (since we're already in a background thread)
                bgm_processed_audio_path = process_bgm_audio(
                    original_audio_path=filepath,
                    transcription_file=srt_filepath,
                    segments_file=segments_filepath,
                    bgm_volume=bgm_volume,  # Use user-provided BGM volume
                    crossfade_duration=bgm_crossfade  # Use user-provided crossfade duration
                )
                
                # Use processed audio for video generation
                video_audio_path = bgm_processed_audio_path
                print(f"[COMBINED API] BGM processing completed, using: {video_audio_path}")
                
            except Exception as e:
                print(f"[COMBINED API] BGM processing failed, using original audio: {e}")
                video_audio_path = filepath
            
            print(f"[COMBINED API] Generating video...")
            # Always use 1.jpg as background
            selected_bg = '1.jpg'
            
            print(f"[COMBINED API] Initializing VideoGenerator...")
            video_gen = VideoGenerator(
                segments_folder=session_segments,
                transcripts_folder=session_transcripts,
                font_folder='circular-std-font-family'
            )
            
            output_video = os.path.join(session_uploads, f"{video_name_clean}.mp4")
            print(f"[COMBINED API] Output video path: {output_video}")
            print(f"[COMBINED API] Input files:")
            print(f"[COMBINED API]   - Segments: {segments_filepath}")
            print(f"[COMBINED API]   - Word SRT: {word_srt_filepath}")
            print(f"[COMBINED API]   - Audio: {video_audio_path}")
            print(f"[COMBINED API]   - Background: {selected_bg}")
            print(f"[COMBINED API]   - Show subtitles: {show_subtitles.lower() == 'true'}")
            
            print(f"[COMBINED API] Starting video generation...")
            import time
            video_start_time = time.time()
            
            try:
                video_gen.generate_video(segments_filepath, word_srt_filepath, video_audio_path, output_video, 
                                       show_subtitles=(show_subtitles.lower() == 'true'), selected_background=selected_bg)
                video_time = time.time() - video_start_time
                print(f"[COMBINED API] Video generation completed successfully in {video_time:.2f}s")
                print(f"[COMBINED API] Video generated successfully: {output_video}")
                
                # Check if file was actually created
                if os.path.exists(output_video):
                    file_size = os.path.getsize(output_video) / (1024*1024)  # MB
                    print(f"[COMBINED API] Video file created: {file_size:.2f} MB")
                else:
                    print(f"[COMBINED API][ERROR] Video file not found after generation!")
                    
            except Exception as e:
                video_time = time.time() - video_start_time
                print(f"[COMBINED API][ERROR] Video generation failed after {video_time:.2f}s: {e}")
                import traceback
                print(f"[COMBINED API][ERROR] Full traceback:")
                traceback.print_exc()
                raise
            
            # --- Calculate and save heygen_empty_spaces.json ---
            heygen_empty_spaces_path = os.path.join(session_segments, 'heygen_empty_spaces.json')
            calculate_and_save_heygen_empty_spaces(slides_json_path, heygen_empty_spaces_path)
            # --- Overlay HeyGen avatar videos in empty spaces ---
            heygen_overlay_result = overlay_heygen_avatars(
                heygen_empty_spaces_path=heygen_empty_spaces_path,
                segments_filepath=segments_filepath,
                filepath=video_audio_path,  # Use processed audio for HeyGen
                session_uploads=session_uploads,
                session_segments=session_segments,
                session_id=session_id,
                heygen_avatar_id=heygen_avatar_id  # <-- pass avatar id
            )
            
            # --- Composite HeyGen overlays into the base video ---
            heygen_composited_video_path = os.path.join(session_uploads, f"{video_name_clean}_with_heygen.mp4")
            try:
                heygen_output_dir = os.path.join(session_uploads, 'heygen_videos')
                create_heygen_overlay_video(
                    base_video_path=output_video,
                    heygen_videos_dir=heygen_output_dir,
                    heygen_empty_spaces_path=heygen_empty_spaces_path,
                    segments_json_path=segments_filepath,
                    output_path=heygen_composited_video_path
                )
                heygen_composited_s3_url = upload_video_to_s3(heygen_composited_video_path, os.path.basename(heygen_composited_video_path))
            except Exception as e:
                print(f"[HEYGEN OVERLAY ERROR] Failed to composite overlays: {e}")
                heygen_composited_s3_url = None
            
            # Upload to S3 using put_object
            filename = os.path.basename(output_video)
            s3_url = upload_video_to_s3(output_video, filename)
            # Optionally, upload a sample HeyGen overlay video if created
            heygen_overlay_video_path = None
            heygen_overlay_s3_url = None
            heygen_output_dir = os.path.join(session_uploads, 'heygen_videos')
            if os.path.exists(heygen_output_dir):
                # Find the first heygen overlay video (resized or noaudio)
                for f in os.listdir(heygen_output_dir):
                    if f.endswith('_heygen_noaudio_resized.mp4') or f.endswith('_heygen_noaudio.mp4'):
                        heygen_overlay_video_path = os.path.join(heygen_output_dir, f)
                        break
            if heygen_overlay_video_path and os.path.exists(heygen_overlay_video_path):
                heygen_overlay_filename = os.path.basename(heygen_overlay_video_path)
                heygen_overlay_s3_url = upload_video_to_s3(heygen_overlay_video_path, heygen_overlay_filename)
            
            # Store final result in Supabase when everything completes successfully
            # Session result stored in memory (container concurrency)
            print(f"✅ Session {session_id} completed successfully")
            
            # Clean up session files after successful upload
            cleanup_session_files(session_id)
            
            job_status[session_id]["status"] = "done"
            job_status[session_id]["result"] = {
                'success': True,
                'video_filename': filename,
                's3_url': s3_url,
                'heygen_overlay_video': heygen_composited_s3_url,
                'message': 'Complete video generated successfully',
                'session_id': session_id
            }
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] Session {session_id} failed: {error_msg}")
            
            # Session error logged in memory (container concurrency)
            print(f"❌ Session {session_id} failed: {error_msg}")
            
            job_status[session_id]["status"] = "error"
            job_status[session_id]["error"] = error_msg
            
            # Clean up on error too
            cleanup_session_files(session_id)

    audio_file_content = await audio_file.read() if audio_file is not None else None
    threading.Thread(target=background_job, args=(audio_file_content,), daemon=True).start()
    return JSONResponse({"session_id": session_id, "status": "pending"})

@app.get("/video_status")
def video_status(session_id: str = None):
    """
    Get video generation status by session_id
    
    Args:
        session_id: Session identifier (query parameter)
        
    Returns:
        Status information for the session
    """
    if not session_id:
        return JSONResponse({"error": "session_id parameter is required"}, status_code=400)
        
    if session_id not in job_status:
        return JSONResponse({"error": "Invalid session_id"}, status_code=404)
    status = job_status[session_id]["status"]
    
    # Get video generation progress if available
    from video_generator import get_video_generation_status
    video_progress = get_video_generation_status()
    
    response = {
        "session_id": session_id,
        "status": status,
        "video_generation_progress": video_progress
    }
    
    if status == "done":
        response["result"] = job_status[session_id]["result"]
    elif status == "error":
        response["error"] = job_status[session_id]["error"]
    
    return JSONResponse(response)

@app.get("/session_result/{session_id}")
async def get_session_result(session_id: str):
    """
    Retrieve session result by session_id from memory (container concurrency)
    
    Args:
        session_id: Session identifier provided by user
        
    Returns:
        Session result with S3 URLs and status
    """
    """
    Retrieve session result by session_id from memory (container concurrency)
    
    Args:
        session_id: Session identifier provided by user
        
    Returns:
        Session result with S3 URLs and status
    """
    if session_id not in job_status:
        return JSONResponse(
            {"error": "Session not found", "session_id": session_id}, 
            status_code=404
        )
    
    status_data = job_status[session_id]
    
    if status_data["status"] == "error":
        return JSONResponse({
            "session_id": session_id,
            "status": "error",
            "error_message": status_data.get("error", "Unknown error"),
            "created_at": status_data.get("created_at")
        })
    
    if status_data["status"] == "done":
        result = status_data.get("result", {})
        return JSONResponse({
            "session_id": session_id,
            "status": "completed",
            "video_name": result.get("video_name"),
            "s3_url": result.get("s3_url"),
            "heygen_s3_url": result.get("heygen_overlay_video"),
            "heygen_overlay_video": result.get("heygen_overlay_video"),
            "video_filename": result.get("video_filename"),
            "result_data": result
        })
    
    return JSONResponse({
        "session_id": session_id,
        "status": status_data["status"],
        "message": "Session still processing"
    })

@app.get("/download_video/{session_id}")
async def download_video(session_id: str):
    """
    Download video by session_id
    
    Args:
        session_id: Session identifier provided by user
        
    Returns:
        Video file or redirect to S3 URL
    """
    if session_id not in job_status:
        return JSONResponse(
            {"error": "Session not found", "session_id": session_id}, 
            status_code=404
        )
    
    status_data = job_status[session_id]
    
    if status_data["status"] != "done":
        return JSONResponse({
            "error": "Video not ready",
            "session_id": session_id,
            "status": status_data["status"]
        }, status_code=400)
    
    result = status_data.get("result", {})
    s3_url = result.get("s3_url")
    
    if not s3_url:
        return JSONResponse({
            "error": "Video URL not found",
            "session_id": session_id
        }, status_code=404)
    
    return JSONResponse({
        "session_id": session_id,
        "download_url": s3_url,
        "video_name": result.get("video_name"),
        "heygen_overlay_video": result.get("heygen_overlay_video")
    })



# --- Calculate and save heygen_empty_spaces.json ---
def calculate_and_save_heygen_empty_spaces(slides_json_path, output_path):
    try:
        try:
            title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
            body_font = ImageFont.truetype(FONT_PATH, BODY_FONT_SIZE)
        except Exception:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)
        empty_spaces = []
        for slide in slides:
            result = calculate_empty_space(slide, title_font, body_font)
            if result:
                empty_spaces.append(result)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(empty_spaces, f, indent=2)
        print(f"[COMBINED API] Identified empty spaces for {len(empty_spaces)} slides (formats 2 & 3). Saved to {output_path}.")
    except Exception as e:
        print(f"[COMBINED API] Empty space detection failed: {e}")

# --- Overlay HeyGen avatar videos in empty spaces ---
def overlay_heygen_avatars(
    heygen_empty_spaces_path,
    segments_filepath,
    filepath,
    session_uploads,
    session_segments,
    session_id,
    heygen_avatar_id=None  # <-- accept avatar id
):
    import concurrent.futures
    overlay_filename = None
    try:
        heygen_output_dir = os.path.join(session_uploads, 'heygen_videos')
        os.makedirs(heygen_output_dir, exist_ok=True)
        s3_links_path = os.path.join(heygen_output_dir, 's3_links.txt')
        with open(s3_links_path, 'w') as f:
            f.write('')
        heygen_api_key = os.getenv('HEYGEN_API_KEY')
        heygen_avatar_id = heygen_avatar_id or 'Jocelyn_sitting_office_side'
        audio_file_path = filepath
        import json as pyjson
        with open(heygen_empty_spaces_path, 'r', encoding='utf-8') as f:
            empty_spaces = pyjson.load(f)
        if not empty_spaces:
            print("[COMBINED API] No empty spaces found for HeyGen overlays")
            overlay_filename = None
        else:
            print(f"[COMBINED API] Found {len(empty_spaces)} slides for HeyGen avatar overlays")
            with open(segments_filepath, 'r', encoding='utf-8') as f:
                segments_data = pyjson.load(f)
            segments = segments_data.get('segments', [])
            if not heygen_api_key or heygen_api_key == 'YOUR_HEYGEN_API_KEY':
                print("[COMBINED API] HeyGen API key not configured, skipping avatar overlays")
                overlay_filename = None
            elif not S3_BUCKET_NAME:
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
                # --- Concurrent HeyGen API calls ---
                def post_and_poll_heygen(slide):
                    import requests, time
                    slide_number = slide['slide_number']
                    start_time = slide['start_time']
                    end_time = slide['end_time']
                    area = slide['empty_space']
                    empty_w, empty_h = int(area['width']), int(area['height'])
                    max_side = min(empty_w, empty_h)
                    
                    # 🎯 ENHANCED: Check for minimum and maximum size
                    if max_side <= 0:
                        print(f"[HEYGEN OVERLAY WARNING] max_side is {max_side} for slide {slide_number}, skipping overlay.")
                        return None
                    elif max_side < MIN_AVATAR_SIZE:
                        print(f"[HEYGEN OVERLAY SKIP] Avatar too small ({max_side}px < {MIN_AVATAR_SIZE}px) for slide {slide_number}, skipping overlay.")
                        return None
                    elif max_side > MAX_AVATAR_SIZE:
                        print(f"[HEYGEN OVERLAY ADJUST] Avatar too large ({max_side}px > {MAX_AVATAR_SIZE}px) for slide {slide_number}, reducing to {MAX_AVATAR_SIZE}px")
                        max_side = MAX_AVATAR_SIZE
                    
                    print(f"[HEYGEN PROCESS] Slide {slide_number}: processing avatar with size {max_side}px")
                    segment_audio = AudioSegment.from_file(audio_file_path)[start_time * 1000:end_time * 1000]
                    segment_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_audio.mp3')
                    segment_audio.export(segment_path, format='mp3')
                    s3_key = f'heygen_segments/{session_id}/slide_{slide_number}_audio.mp3'
                    s3_url = upload_file_to_s3(segment_path, s3_key, bucket_name=S3_BUCKET_NAME)
                    if s3_url:
                        with open(s3_links_path, 'a') as f:
                            f.write(s3_url + '\n')
                    if not s3_url:
                        print(f"[COMBINED API] Failed to upload audio for slide {slide_number}")
                        return None
                    post_headers = {
                        'Authorization': f'Bearer {heygen_api_key}',
                        'Content-Type': 'application/json',
                    }
                    payload = {
                        "video_inputs": [
                            {
                                "character": {
                                    "type": "avatar",
                                    "avatar_id": heygen_avatar_id,
                                    "avatar_style": "circle"
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
                        "dimensions": {
                            "width": max_side,
                            "height": max_side
                        }
                    }
                    try:
                        resp = requests.post("https://api.heygen.com/v2/video/generate", json=payload, headers=post_headers)
                        resp.raise_for_status()
                        data = resp.json()
                        video_id = data['data']['video_id']
                        print(f'[COMBINED API] Video requested, id: {video_id}')
                    except Exception as e:
                        print(f'[COMBINED API] HeyGen API error for slide {slide_number}: {e}')
                        return None
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
                        return None
                    # Download video
                    try:
                        import requests
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
                        return None
                    # Mute audio and save no-audio file first
                    heygen_noaudio_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio.mp4')
                    heygen_clip = VideoFileClip(video_path)
                    noaudio_clip = heygen_clip.without_audio()
                    noaudio_clip.write_videofile(heygen_noaudio_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
                    heygen_clip.close()
                    noaudio_clip.close()
                    # Now check for existence and load for overlay
                    if not os.path.exists(heygen_noaudio_path):
                        print(f"[HEYGEN OVERLAY WARNING] HeyGen video not found for slide {slide_number}: {heygen_noaudio_path}")
                        return None
                    try:
                        heygen_clip = VideoFileClip(heygen_noaudio_path)
                    except Exception as e:
                        print(f"[HEYGEN OVERLAY WARNING] Could not load HeyGen video for slide {slide_number}: {e}")
                        return None
                    # --- CROP to center square before resizing ---
                    w, h = heygen_clip.size
                    side = min(w, h)
                    x_center = w // 2
                    y_center = h // 2
                    x1 = x_center - side // 2
                    y1 = y_center - side // 2
                    heygen_clip_cropped = heygen_clip.crop(x1=x1, y1=y1, x2=x1+side, y2=y1+side)

                    # Resize, subclip, and set duration
                    heygen_clip_final = heygen_clip_cropped.resize((max_side, max_side))
                    actual_overlay_duration = min(duration, heygen_clip_final.duration)
                    heygen_clip_final = heygen_clip_final.subclip(0, actual_overlay_duration)
                    heygen_clip_final = heygen_clip_final.set_position((x, y)).set_start(start_time).set_duration(actual_overlay_duration)

                    print(f"[DEBUG] Overlaying slide {slide_number}: x={x}, y={y}, size={max_side}, start={start_time}, end={end_time}, base=({base_clip.w},{base_clip.h})")
                    overlay_clips.append(heygen_clip_final)
                    return True
                # Run all HeyGen jobs concurrently
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                    futures = [executor.submit(post_and_poll_heygen, slide) for slide in slide_segments]
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            print(f'[COMBINED API] Exception in HeyGen concurrent job: {e}')
    except Exception as e:
        print(f"[COMBINED API] HeyGen overlay generation failed: {e}")
    return overlay_filename 

# --- Utility: Create HeyGen overlay video using test script logic ---
def create_heygen_overlay_video(base_video_path, heygen_videos_dir, heygen_empty_spaces_path, segments_json_path, output_path):
    import json
    from moviepy.editor import VideoFileClip, CompositeVideoClip
    import os
    # Load base video
    base_clip = VideoFileClip(base_video_path)
    # Load heygen empty space info
    with open(heygen_empty_spaces_path, 'r', encoding='utf-8') as f:
        empty_spaces = json.load(f)
    # Load segment timing info
    with open(segments_json_path, 'r', encoding='utf-8') as f:
        segments_data = json.load(f)
    segment_map = {seg['segment_id']: seg for seg in segments_data['segments']}
    # Prepare overlay clips
    overlay_clips = []
    for space in empty_spaces:
        area = space['empty_space']
        slide_number = space.get('slide_number', 1)
        segment = segment_map.get(slide_number)
        if not segment:
            print(f"[HEYGEN OVERLAY WARNING] No segment timing for slide {slide_number}, skipping overlay.")
            continue
        start_time = segment.get('start_time', 0)
        end_time = segment.get('end_time', base_clip.duration)
        duration = end_time - start_time
        empty_w, empty_h = int(area['width']), int(area['height'])
        max_side = min(empty_w, empty_h)
        if max_side <= 0:
            print(f"[HEYGEN OVERLAY WARNING] max_side is {max_side} for slide {slide_number}, skipping overlay.")
            continue
        format_type = space.get('format', 2)
        if format_type == 2:
            x = area['x']
        elif format_type == 3:
            x = area['x'] + empty_w - max_side
        else:
            x = area['x']
        y = area['y']
        x = max(0, min(x, base_clip.w - max_side))
        y = max(0, min(y, base_clip.h - max_side))
        # Find the corresponding heygen overlay video for this slide
        heygen_video_path = os.path.join(heygen_videos_dir, f'slide_{slide_number}_heygen_noaudio.mp4')
        if not os.path.exists(heygen_video_path):
            print(f"[HEYGEN OVERLAY WARNING] No heygen overlay video for slide {slide_number}: {heygen_video_path}")
            continue
        heygen_clip_orig = VideoFileClip(heygen_video_path).without_audio()
        # --- CROP to center square before resizing ---
        w, h = heygen_clip_orig.size
        side = min(w, h)
        x_center = w // 2
        y_center = h // 2
        x1 = x_center - side // 2
        y1 = y_center - side // 2
        heygen_clip_cropped = heygen_clip_orig.crop(x1=x1, y1=y1, x2=x1+side, y2=y1+side)
        # Resize, subclip, and set duration
        heygen_clip = heygen_clip_cropped.resize((max_side, max_side))
        actual_overlay_duration = min(duration, heygen_clip.duration)
        heygen_clip = heygen_clip.subclip(0, actual_overlay_duration)
        heygen_clip = heygen_clip.set_position((x, y)).set_start(start_time).set_duration(actual_overlay_duration)
        print(f"[DEBUG] Overlaying slide {slide_number}: x={x}, y={y}, size={max_side}, start={start_time}, end={end_time}, base=({base_clip.w},{base_clip.h})")
        overlay_clips.append(heygen_clip)
        heygen_clip_orig.close()
    # Composite overlays onto base video
    final = CompositeVideoClip([base_clip] + overlay_clips)
    final.write_videofile(output_path, codec='libx264', audio_codec='aac')
    print(f"[DONE] Overlay video saved to: {output_path}")
    base_clip.close()
    for c in overlay_clips:
        c.close()

def process_bgm_audio(original_audio_path: str, transcription_file: str, segments_file: str, bgm_volume: int = 50, crossfade_duration: int = 2000) -> str:
    """
    Process audio with BGM overlay in a separate thread
    """
    try:
        print(f"[BGM] Starting BGM processing for: {original_audio_path}")
        processor = BGMProcessor()
        
        # Process audio with BGM
        processed_audio_path = processor.process_audio_with_bgm(
            original_audio_path=original_audio_path,
            transcription_file=transcription_file,
            segments_json_path=segments_file,
            bgm_volume=bgm_volume,
            crossfade_duration=crossfade_duration
        )
        
        print(f"[BGM] BGM processing completed: {processed_audio_path}")
        return processed_audio_path
        
    except Exception as e:
        print(f"[BGM] Error processing BGM: {e}")
        # Return original audio path if BGM processing fails
        return original_audio_path

def create_session_directories(session_id: str):
    """Create unique directories for each request session to handle concurrency"""
    session_uploads = os.path.join(UPLOAD_FOLDER, session_id)
    session_transcripts = os.path.join(TRANSCRIPTS_FOLDER, session_id)
    session_segments = os.path.join(SEGMENTS_FOLDER, session_id)
    
    for folder in [session_uploads, session_transcripts, session_segments]:
        if not os.path.exists(folder):
            os.makedirs(folder)
    
    return session_uploads, session_transcripts, session_segments

def segment_transcript_variable_duration(sentence_segments, srt_file_path=None, audio_duration=None):
    """
    Segment transcript into variable-length segments based on assigned format:
    - Format 4: 5-8 seconds
    - Format 2 or 3: 10-20 seconds (based on word count/complexity)
    Ensures no consecutive formats are the same.
    Returns a list of dicts: {start, end, text, format}
    
    Args:
        sentence_segments: List of transcription segments
        srt_file_path: Optional path to SRT file to get content for slide generation
        audio_duration: Optional actual audio duration from words (takes precedence over SRT duration)
    """
    if not sentence_segments:
        return []
    
    # Use audio_duration if provided, otherwise fall back to SRT file or transcription
    if audio_duration is not None:
        print(f"[DEBUG] Using provided audio duration: {audio_duration:.2f}s")
        total_duration = audio_duration
    elif srt_file_path and os.path.exists(srt_file_path):
        print(f"[DEBUG] Using SRT file for duration: {srt_file_path}")
        total_duration = get_srt_duration(srt_file_path)
        print(f"[DEBUG] SRT file duration: {total_duration:.2f}s")
    else:
        total_duration = sentence_segments[-1]['end']
        print(f"[DEBUG] Using transcription duration: {total_duration:.2f}s")
    
    segments = []
    segment_start = 0
    previous_format = None
    i = 0
    while segment_start < total_duration:
        # Assign format (2, 3, or 4), not repeating previous
        possible_formats = [2, 3, 4]
        if previous_format in possible_formats:
            possible_formats.remove(previous_format)
        format_type = random.choice(possible_formats)
        # Pick duration range based on format
        if format_type == 4:
            min_dur, max_dur = 5, 8
        else:
            min_dur, max_dur = 10, 20
        # Try to pick a segment that fits the duration and ends at a sentence boundary
        segment_end = min(segment_start + max_dur, total_duration)
        # Find the last sentence that ends before or at segment_end, but after min_dur
        best_end = None
        for s in sentence_segments:
            if s['end'] <= segment_end and s['end'] - segment_start >= min_dur:
                best_end = s['end']
            if s['end'] > segment_end:
                break
        if best_end is None:
            # If no suitable end found, just use min(segment_start+min_dur, total_duration)
            best_end = min(segment_start + min_dur, total_duration)
        # If this is the last segment or we're close to the end, force it to end at total_duration
        if best_end >= total_duration or segment_end >= total_duration or (total_duration - best_end) < min_dur:
            best_end = total_duration
        # If for any reason best_end did not advance, break to avoid infinite loop
        if best_end <= segment_start:
            best_end = total_duration
            if best_end == segment_start:
                break
        # Collect text for this segment
        segment_text = ''
        for s in sentence_segments:
            if s['start'] < best_end and s['end'] > segment_start:
                if segment_text:
                    segment_text += ' ' + s['text']
                else:
                    segment_text = s['text']
        if segment_text.strip():
            segments.append({
                'start': segment_start,
                'end': best_end,
                'text': segment_text.strip(),
                'format': format_type
            })
            previous_format = format_type
        segment_start = best_end
        i += 1
    # Correction: If due to rounding, the last segment's end is not exactly total_duration, fix it
    if segments and abs(segments[-1]['end'] - total_duration) > 1e-3:
        segments[-1]['end'] = total_duration
    # Debug output: print all segment timings and their sum
    print("[DEBUG] Slide Segments:")
    total = 0
    for idx, seg in enumerate(segments):
        dur = seg['end'] - seg['start']
        total += dur
        print(f"  Segment {idx+1}: {seg['start']:.2f}s - {seg['end']:.2f}s (duration: {dur:.2f}s)")
    print(f"[DEBUG] Sum of slide durations: {total:.2f}s")
    print(f"[DEBUG] Total audio duration: {total_duration:.2f}s")
    return segments

def get_srt_duration(srt_file_path):
    """Get the total duration from an SRT file"""
    try:
        with open(srt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the last timestamp in the SRT file
        import re
        timestamp_pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})'
        matches = re.findall(timestamp_pattern, content)
        
        if matches:
            # Get the end time of the last subtitle
            last_match = matches[-1]
            end_h, end_m, end_s, end_ms = map(int, last_match[4:])
            total_duration = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000
            return total_duration
        else:
            print(f"[WARNING] No timestamps found in SRT file: {srt_file_path}")
            return 0
    except Exception as e:
        print(f"[ERROR] Failed to read SRT file {srt_file_path}: {e}")
        return 0
