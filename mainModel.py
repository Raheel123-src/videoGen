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

from openai import OpenAI
import difflib
import concurrent.futures
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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
BOTTOM_MARGIN = 80

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
            return sentence_segments, word_segments
        # If segments is None but words and text are present, use those
        elif hasattr(result, 'words') and result.words and hasattr(result, 'text') and result.text:
            print("[DEBUG] Falling back to words/text fields for sentence/word segments.")
            # Treat the whole text as one segment
            sentence_segments = [{
                'start': result.words[0].start if result.words else 0,
                'end': result.words[-1].end if result.words else 0,
                'text': result.text.strip()
            }]
            word_segments = []
            for word in result.words:
                word_segments.append({
                    'start': word.start,
                    'end': word.end,
                    'text': word.word.strip()
                })
            return sentence_segments, word_segments
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
    
    # Generate dynamic environment prompt based on target audience
    if target_audience:
        environment_prompt = generate_environment_prompt_for_target_audience(target_audience)
        print(f"[DEBUG] Generated environment prompt for '{target_audience}': {environment_prompt}")
    else:
        # Fallback to default Indian corporate environment
        environment_prompt = "Indian corporate office environment with diverse professionals in formal attire, modern workspace with glass partitions, laptops, indoor plants, natural lighting, professional atmosphere, photorealistic quality"
    
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

**DYNAMIC IMAGE PROMPT REQUIREMENTS:**
For image_prompt, create highly detailed prompts that:
- Use the provided environment context: "{environment_prompt}"
- **Analyze the transcript segment** and extract key themes, emotions, or concepts
- **Match the image to the slide content** - if the slide talks about stress management, show stressed professionals; if it's about teamwork, show collaborative scenes
- **Incorporate specific elements** mentioned in the transcript (e.g., if "deadlines" are mentioned, show time pressure scenarios)
- **Reflect the tone and mood** of the content (calm, energetic, focused, collaborative, etc.)
- **Integrate the target environment** seamlessly into the scene

**Image Prompt Structure:**
Combine the environment context with the slide content to create a cohesive scene. For example:
- If transcript talks about "team collaboration" and environment is "manufacturing unit": "Team of manufacturing professionals collaborating around production line, {environment_prompt}, focused expressions, teamwork atmosphere"
- If transcript talks about "stress management" and environment is "hospital": "Healthcare professionals in stress management training session, {environment_prompt}, calm and focused atmosphere"

**Quality Requirements:**
- **Photorealistic, professional** visuals only
- Avoid cartoon or generic visuals
- Vary people and angles slightly across slides while maintaining realism
- No logos or copyrighted branding
- **Ensure the image directly supports** the slide's educational or professional development message
- **Seamlessly integrate** the target environment with the slide content

**Example image_prompt format:**
"Team of manufacturing professionals collaborating around production line, {environment_prompt}, focused expressions, teamwork atmosphere, photorealistic, 1024x1024"

Transcript:
"""{segment_text}"""
Duration: {segment_duration:.2f} seconds
Title: {segment_title or f"Slide {segment_index+1}"}
Target Environment: {target_audience or "General corporate"}
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
    """Create slides.json from pre-created segments"""
    slides = []
    total_segments = len(segments)
    previous_format = None
    
    print(f"[DEBUG] Creating {total_segments} slides from segments")
    if target_audience:
        print(f"[DEBUG] Using target audience: {target_audience}")
    
    for i, segment in enumerate(segments):
        percent = int((i+1)/total_segments*100)
        duration = segment['end'] - segment['start']
        print(f"Generating slide JSON for segment {i+1}/{total_segments} ({percent}%) - Duration: {duration:.1f}s", flush=True)
        slide_json = generate_slide_json_content(segment['text'], i, duration, previous_format=previous_format, target_audience=target_audience)
        previous_format = slide_json.get('format', previous_format)
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

def create_slides_json_from_corrected_srt(corrected_sentence_srt, slides_json_path, target_audience=None):
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
        
    total_duration = corrected_segments[-1]['end']
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
    # Limit to 2 concurrent requests for CPU-only processing to avoid overwhelming the API
    max_workers = min(2, total_images)
    
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
    selected_background: str = Form(""),
    target_audience: Optional[str] = Form(None)
):
    # Generate unique session ID for this request
    session_id = f"{video_name}_{uuid.uuid4().hex[:8]}"
    session_uploads, session_transcripts, session_segments = create_session_directories(session_id)
    
    try:
        if not audio_file and not audio_url and not script:
            return JSONResponse({"error": "Please provide either an audio file, audio URL, or a script."}, status_code=400)
        if not video_name:
            return JSONResponse({"error": "Video name is required"}, status_code=400)
        video_name_clean = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
        if not video_name_clean:
            return JSONResponse({"error": "Invalid video name"}, status_code=400)
        print(f"[COMBINED API] Starting combined process for video: {video_name_clean} (session: {session_id})")
        if audio_file:
            filename = audio_file.filename or f"audio_{random.randint(1000,9999)}.mp3"
            filepath = os.path.join(session_uploads, filename)
            with open(filepath, "wb") as f:
                f.write(await audio_file.read())
            print(f"[COMBINED API] Saved uploaded file: {filepath}")
        elif audio_url:
            filename, filepath = download_audio_file(audio_url)
            if not filename:
                filename = f"audio_{random.randint(1000,9999)}.mp3"
            if not filepath:
                return JSONResponse({"error": "Failed to download audio file."}, status_code=400)
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
            return JSONResponse({"error": "No valid audio input provided."}, status_code=400)
        if not os.path.exists(filepath):
            return JSONResponse({"error": "Audio file not found after upload/generation."}, status_code=500)
        print(f"[COMBINED API] Transcribing audio...")
        sentence_segments, word_segments = transcribe_audio(filepath)
        base_filename = filename.rsplit('.', 1)[0] if filename and '.' in filename else filename or f"audio_{random.randint(1000,9999)}"
        srt_filename = f"{base_filename}_sentences.srt"
        srt_filepath = os.path.join(session_transcripts, srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        word_srt_filename = f"{base_filename}_words.srt"
        word_srt_filepath = os.path.join(session_transcripts, word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        # If both audio (file or URL) and script are provided, use GPT to correct SRTs
        if (audio_file or audio_url) and script:
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
        
        # If GPT correction was used, create slides from corrected SRT
        if (audio_file or audio_url) and script:
            print("[DEBUG] Creating slides from GPT-corrected SRT content...")
            create_slides_json_from_corrected_srt(corrected_sentence_srt, slides_json_path, target_audience=target_audience)
        else:
            # Use original transcription for slides
            print("[DEBUG] Creating slides from original transcription...")
            audio_segments = create_audio_segments(sentence_segments, 15)
            create_slides_json_from_segments(audio_segments, slides_json_path, target_audience=target_audience)
        
        # Create segments.json for video generation (always use original segments for timing)
        audio_segments = create_audio_segments(sentence_segments, 15)
        segments_filename = f"{base_filename}_segments.json"
        segments_filepath = os.path.join(session_segments, segments_filename)
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
            segments_folder=session_segments,
            transcripts_folder=session_transcripts,
            font_folder='circular-std-font-family'
        )
        output_video = os.path.join(session_uploads, f"{video_name_clean}.mp4")
        video_gen.generate_video(segments_filepath, word_srt_filepath, filepath, output_video, 
                               show_subtitles=(show_subtitles.lower() == 'true'), selected_background=selected_bg)
        print(f"[COMBINED API] Video generated successfully: {output_video}")
        
        # Upload to S3 using put_object
        filename = os.path.basename(output_video)
        s3_url = upload_video_to_s3(output_video, filename)
        
        # Clean up session files after successful upload
        cleanup_session_files(session_id)
        
        return JSONResponse({
            'success': True,
            'video_filename': filename,
            's3_url': s3_url,
            'message': 'Complete video generated successfully',
            'session_id': session_id
        })
    except Exception as e:
        print(f"[COMBINED API ERROR] Process failed: {e}")
        # Clean up session files on error
        cleanup_session_files(session_id)
        return JSONResponse({"error": str(e)}, status_code=500) 