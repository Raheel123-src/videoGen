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
import whisper
from pydub import AudioSegment
import json
from video_generator import VideoGenerator
import sys
import subprocess
from urllib.parse import urlparse
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import cv2
from openai import OpenAI

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

# Face detection cascade classifier
face_cascade = None
def get_face_cascade():
    global face_cascade
    if face_cascade is None:
        # Try to load the cascade classifier
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            print("[FACE DETECTION] Warning: Could not load face cascade classifier")
    return face_cascade

def detect_face_in_video(video_path):
    """Detect face in video and return face coordinates and dimensions"""
    try:
        # Load video
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[FACE DETECTION] Could not open video: {video_path}")
            return None
        
        # Get face cascade
        cascade = get_face_cascade()
        if cascade is None:
            return None
        
        # Read first few frames to find face
        face_detected = False
        face_info = None
        
        for _ in range(10):  # Check first 10 frames
            ret, frame = cap.read()
            if not ret:
                break
            
            # Convert to grayscale for face detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )
            
            if len(faces) > 0:
                # Get the largest face (assuming it's the main person)
                largest_face = max(faces, key=lambda x: x[2] * x[3])
                x, y, w, h = largest_face
                
                # Calculate face center and radius
                center_x = x + w // 2
                center_y = y + h // 2
                radius = max(w, h) // 2
                
                # Ensure radius doesn't exceed frame boundaries
                frame_h, frame_w = frame.shape[:2]
                radius = min(radius, min(center_x, center_y, frame_w - center_x, frame_h - center_y))
                
                face_info = {
                    'center_x': center_x,
                    'center_y': center_y,
                    'radius': radius,
                    'frame_width': frame_w,
                    'frame_height': frame_h
                }
                face_detected = True
                break
        
        cap.release()
        
        if face_detected:
            print(f"[FACE DETECTION] Face detected: center=({face_info['center_x']}, {face_info['center_y']}), radius={face_info['radius']}")
            return face_info
        else:
            print(f"[FACE DETECTION] No face detected in video: {video_path}")
            return None
            
    except Exception as e:
        print(f"[FACE DETECTION] Error detecting face: {e}")
        return None

def create_circular_face_crop(frame, face_info):
    """Create circular crop around detected face, with transparent background and upper body included."""
    try:
        if face_info is None:
            return frame

        h, w = frame.shape[:2]
        center_x = face_info['center_x']
        # Shift the center down to include more of the upper body
        center_y = int(face_info['center_y'] + face_info['radius'] * 0.7)
        # Expand the radius to include upper body and hand gestures
        radius = int(face_info['radius'] * 2.2)

        # Ensure the crop box is within frame bounds
        left = max(center_x - radius, 0)
        right = min(center_x + radius, w)
        top = max(center_y - radius, 0)
        bottom = min(center_y + radius, h)

        # Crop the frame
        cropped = frame[top:bottom, left:right]

        # Ensure even dimensions
        ch, cw = cropped.shape[:2]
        if ch % 2 != 0:
            cropped = cropped[:-1, :]
        if cw % 2 != 0:
            cropped = cropped[:, :-1]
        ch, cw = cropped.shape[:2]

        # Create circular mask
        mask = np.zeros((ch, cw), dtype=np.uint8)
        y_coords, x_coords = np.ogrid[:ch, :cw]
        mask_area = (x_coords - cw // 2) ** 2 + (y_coords - ch // 2) ** 2 <= (min(ch, cw) // 2) ** 2
        mask[mask_area] = 255

        # Create RGBA output
        if cropped.shape[2] == 3:
            rgba = np.dstack([cropped, np.full((ch, cw), 255, dtype=np.uint8)])
        else:
            rgba = cropped.copy()
        rgba[..., 3] = mask  # Set alpha channel
        return rgba
    except Exception as e:
        print(f"[CIRCULAR CROP ERROR] {e}")
        return frame

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

# Function to generate slide JSON content using GPT-4o
def generate_slide_json_content(segment_text, segment_index, segment_duration, segment_title=None, previous_format=None):
    client = get_openai_client()
    prompt = f'''
You are a presentation expert specializing in Indian corporate environments.

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

**INDIAN IMAGE REQUIREMENTS:**
For image_prompt, generate highly detailed prompts that produce realistic Indian human characters in modern pharmaceutical industry settings—such as research labs, production facilities, or clinical environments. The image should directly relate to the slide content and transcript segment.

📌 **Context Integration:**
- **Analyze the transcript segment** and extract key themes, emotions, or concepts
- **Match the image to the slide content** - if the slide talks about stress management, show stressed professionals; if it's about teamwork, show collaborative scenes
- **Incorporate specific elements** mentioned in the transcript (e.g., if "deadlines" are mentioned, show time pressure scenarios)
- **Reflect the tone and mood** of the content (calm, energetic, focused, collaborative, etc.)

📌 **Character Requirements:**
- Use **Indian ethnicity, attire, and context** (e.g., kurta with ID badge, formal shirt, women in saree/blazer, men in formal shirts, Indian facial features)
- Include diverse Indian professionals (different ages, genders, ethnicities within India)
- Pose and expression should match the **emotion or theme of the slide** (empathy, stress, teamwork, productivity, growth, leadership)
- **Facial expressions and body language** should reflect the content's emotional tone

📌 **Office Environment Requirements:**
- **Indian office settings** (open-plan workspace, glass partitions, laptops, Indian-style furniture, indoor plants, name boards in Hindi/English, HR posters in background)
- **Modern Indian corporate atmosphere** (clean desks, Indian corporate culture elements)
- **Natural or soft corporate lighting** (fluorescent or LED lighting common in Indian offices)
- Include subtle Indian cultural elements (calendar with Indian festivals, tea cups, etc.)
- **Scene composition** should support the slide's message (e.g., focused individual work, team meetings, training sessions)

📌 **Quality Requirements:**
- **Photorealistic, professional Indian** visuals only
- Avoid cartoon or generic western-style visuals
- Vary people and angles slightly across slides while maintaining realism
- No logos or copyrighted branding
- **Ensure the image directly supports** the slide's educational or professional development message

**Example image_prompt format:**
"A diverse group of Indian professionals in a modern Bangalore office, men in formal shirts and women in sarees/blazers, gathered around a glass conference table, natural lighting from large windows, laptops and notebooks visible, indoor plants in background, professional corporate atmosphere, photorealistic, 1024x1024"

Transcript:
"""{segment_text}"""
Duration: {segment_duration:.2f} seconds
Title: {segment_title or f"Slide {segment_index+1}"}
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
    raw_json = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
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
        fixed_json = fix_response.choices[0].message.content.strip() if fix_response.choices[0].message.content else ""
        slide_json = try_parse_json(fixed_json)
        if slide_json is None:
            raise Exception(f"Failed to parse/fix JSON for segment {segment_index}. Raw: {raw_json}")
    return slide_json

# Function to create slides.json from segments

def create_slides_json_from_segments(segments, slides_json_path):
    slides = []
    total_segments = len(segments)
    previous_format = None
    for i, segment in enumerate(segments):
        percent = int((i+1)/total_segments*100)
        print(f"Generating slide JSON for segment {i+1}/{total_segments} ({percent}%)", flush=True)
        slide_json = generate_slide_json_content(segment['text'], i, segment['end'] - segment['start'], previous_format=previous_format)
        previous_format = slide_json.get('format', previous_format)
        slides.append(slide_json)
    with open(slides_json_path, 'w', encoding='utf-8') as f:
        import json
        json.dump(slides, f, indent=2, ensure_ascii=False)
    print(f"Slides JSON saved: {slides_json_path}")

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
        # --- Ensure slides.json is generated ---
        slides_json_path = os.path.join(SEGMENTS_FOLDER, 'slides.json')
        create_slides_json_from_segments(audio_segments, slides_json_path)
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
        # TEMPORARILY DISABLED: HeyGen overlay video generation
        overlay_filename = None
        # try:
        #     heygen_output_dir = 'heygen_videos'
        #     os.makedirs(heygen_output_dir, exist_ok=True)
        #     s3_links_path = os.path.join(heygen_output_dir, 's3_links.txt')
        #     with open(s3_links_path, 'w') as f:
        #         f.write('')
        #     heygen_api_key = os.getenv('HEYGEN_API_KEY')
        #     heygen_avatar_id = 'Jocelyn_sitting_office_side'
        #     audio_file_path = filepath
        #     with open('heygen_empty_spaces.json', 'r', encoding='utf-8') as f:
        #         empty_spaces = json.load(f)
        #     if not empty_spaces:
        #         print("[COMBINED API] No empty spaces found for HeyGen overlays")
        #         overlay_filename = None
        #     else:
        #         print(f"[COMBINED API] Found {len(empty_spaces)} slides for HeyGen avatar overlays")
        #         segments_file = segments_filepath
        #         with open(segments_file, 'r', encoding='utf-8') as f:
        #             segments_data = json.load(f)
        #         segments = segments_data.get('segments', [])
        #         if not heygen_api_key or heygen_api_key == 'YOUR_HEYGEN_API_KEY':
        #             print("[COMBINED API] HeyGen API key not configured, skipping avatar overlays")
        #             overlay_filename = None
        #         elif not S3_BUCKET_NAME:
        #             print("[COMBINED API] S3 bucket not configured, skipping avatar overlays")
        #             overlay_filename = None
        #         else:
        #             slide_segments = []
        #             for space in empty_spaces:
        #                 slide_number = space.get('slide_number')
        #                 segment = next((s for s in segments if s.get('segment_id') == slide_number), None)
        #                 if not segment:
        #                     continue
        #                 slide_segments.append({
        #                     'slide_number': slide_number,
        #                     'start_time': segment.get('start_time', 0),
        #                     'end_time': segment.get('end_time', 0),
        #                     'empty_space': space['empty_space']
        #                 })
        #             print(f"[COMBINED API] Generating HeyGen videos for {len(slide_segments)} slides...")
        #             for slide in slide_segments:
        #                 slide_number = slide.get('slide_number')
        #                 start_time = slide.get('start_time')
        #                 end_time = slide.get('end_time')
        #                 min_dim, max_dim = 128, 4096
        #                 width = int(slide['empty_space']['width'])
        #                 height = int(slide['empty_space']['height'])
        #                 heygen_width = max(min_dim, min(width, max_dim))
        #                 heygen_height = max(min_dim, min(height, max_dim))
        #                 print(f"[COMBINED API] Extracting and uploading audio for slide {slide_number}...")
        #                 audio = AudioSegment.from_file(audio_file_path)
        #                 segment_audio = audio[start_time * 1000:end_time * 1000]
        #                 segment_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_audio.mp3')
        #                 segment_audio.export(segment_path, format='mp3')
        #                 s3_key = f'heygen_segments/slide_{slide_number}_audio.mp3'
        #                 s3_url = upload_file_to_s3(segment_path, s3_key, bucket_name=S3_BUCKET_NAME)
        #                 if s3_url:
        #                     with open(s3_links_path, 'a') as f:
        #                         f.write(s3_url + '\n')
        #                 if not s3_url:
        #                     print(f"[COMBINED API] Failed to upload audio for slide {slide_number}")
        #                     continue
        #                 post_headers = {
        #                     'Authorization': f'Bearer {heygen_api_key}',
        #                     'Content-Type': 'application/json',
        #                 }
        #                 payload = {
        #                     "video_inputs": [
        #                         {
        #                             "character": {
        #                                 "type": "avatar",
        #                                 "avatar_id": heygen_avatar_id
        #                             },
        #                             "voice": {
        #                                 "type": "audio",
        #                                 "audio_url": s3_url
        #                             }
        #                         }
        #                     ]
        #                 }
        #                 try:
        #                     resp = requests.post("https://api.heygen.com/v2/video/generate", json=payload, headers=post_headers)
        #                     resp.raise_for_status()
        #                     data = resp.json()
        #                     video_id = data['data']['video_id']
        #                     print(f'[COMBINED API] Video requested, id: {video_id}')
        #                 except Exception as e:
        #                     print(f'[COMBINED API] HeyGen API error for slide {slide_number}: {e}')
        #                     continue
        #                 status_url = f'https://api.heygen.com/v1/video_status.get?video_id={video_id}'
        #                 get_headers = {
        #                     'accept': 'application/json',
        #                     'x-api-key': heygen_api_key,
        #                 }
        #                 time.sleep(5)
        #                 poll_count = 0
        #                 video_url = None
        #                 while True:
        #                     try:
        #                         status_resp = requests.get(status_url, headers=get_headers)
        #                         if status_resp.status_code == 404:
        #                             print(f'[{poll_count}] Video not found yet, retrying...')
        #                             time.sleep(3)
        #                             poll_count += 1
        #                             continue
        #                         status_resp.raise_for_status()
        #                         status_json = status_resp.json()
        #                         print(f'[{poll_count}] Full response: {status_json}')
        #                         status = status_json['data']['status']
        #                         if status == 'completed':
        #                             video_url = status_json['data']['video_url']
        #                             print(f'[COMBINED API] Video ready at: {video_url}')
        #                             break
        #                         elif status == 'failed':
        #                             print(f'[COMBINED API] HeyGen video generation failed for slide {slide_number}. Status response: {status_json}')
        #                             break
        #                         print(f'[{poll_count}] Current status: {status}')
        #                     except requests.exceptions.RequestException as e:
        #                         print(f'Error polling status: {e}')
        #                     time.sleep(5)
        #                     poll_count += 1
        #                 if not video_url:
        #                     continue
        #                 try:
        #                     parsed_url = urlparse(video_url)
        #                     base_name = os.path.basename(parsed_url.path)
        #                     video_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen.mp4')
        #                     with requests.get(video_url, stream=True) as r:
        #                         r.raise_for_status()
        #                         with open(video_path, 'wb') as f:
        #                             for chunk in r.iter_content(chunk_size=8192):
        #                                 f.write(chunk)
        #                     print(f'[COMBINED API] HeyGen video downloaded to: {video_path}')
        #                 except Exception as e:
        #                     print(f'[COMBINED API] Error downloading HeyGen video for slide {slide_number}: {e}')
        #                     continue
        #                 try:
        #                     heygen_clip = VideoFileClip(video_path)
        #                     noaudio_clip = heygen_clip.without_audio()
        #                     noaudio_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio.mp4')
        #                     noaudio_clip.write_videofile(noaudio_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
        #                     heygen_clip.close()
        #                     noaudio_clip.close()
        #                     
        #                     # Detect face in the video
        #                     print(f"[FACE DETECTION] Detecting face in slide {slide_number}...")
        #                     face_info = detect_face_in_video(noaudio_path)
        #                     
        #                     # Resize the video
        #                     resized_clip = VideoFileClip(noaudio_path)
        #                     orig_w, orig_h = resized_clip.size
        #                     target_w, target_h = width, height
        #                     scale = min(target_w / orig_w, target_h / orig_h)
        #                     new_w, new_h = int(orig_w * scale), int(orig_h * scale)
        #                     resized_clip = resized_clip.resize((new_w, new_h))
        #                     
        #                     # Apply circular face crop if face was detected
        #                     if face_info:
        #                         # Scale face info to new dimensions
        #                         scale_factor = new_w / face_info['frame_width']
        #                         scaled_face_info = {
        #                             'center_x': int(face_info['center_x'] * scale_factor),
        #                             'center_y': int(face_info['center_y'] * scale_factor),
        #                             'radius': int(face_info['radius'] * scale_factor),
        #                             'frame_width': new_w,
        #                             'frame_height': new_h
        #                         }
        #                         
        #                         # Apply circular crop to each frame
        #                         def apply_circular_crop(frame):
        #                             return create_circular_face_crop(frame, scaled_face_info)
        #                         circular_clip = resized_clip.fl_image(apply_circular_crop)
        #                         resized_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio_circular.webm')
        #                         circular_clip.write_videofile(resized_path, codec='libvpx', fps=resized_clip.fps, verbose=False, logger=None)
        #                         circular_clip.close()
        #                         print(f"[FACE DETECTION] Circular face crop applied to slide {slide_number}")
        #                     else:
        #                         # No face detected, use regular resized video
        #                         resized_path = os.path.join(heygen_output_dir, f'slide_{slide_number}_heygen_noaudio_resized.mp4')
        #                         resized_clip.write_videofile(resized_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
        #                         print(f"[FACE DETECTION] No face detected, using regular video for slide {slide_number}")
        #                 except Exception as e:
        #                     print(f"[COMBINED API] Error processing HeyGen video for slide {slide_number}: {e}")
        #                     continue
        # except Exception as e:
        #     print(f"[COMBINED API] HeyGen overlay generation failed: {e}")

        # Upload to S3 using put_object
        filename = os.path.basename(output_video)
        s3_url = upload_video_to_s3(output_video, filename)
        
        return JSONResponse({
            'success': True,
            'video_filename': filename,
            'overlay_video_filename': overlay_filename,
            'overlay_video_preview_url': f"/download_video/{overlay_filename}" if overlay_filename else None,
            's3_url': s3_url,
            'message': 'Complete video generated successfully'
        })
    except Exception as e:
        print(f"[COMBINED API ERROR] Process failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500) 