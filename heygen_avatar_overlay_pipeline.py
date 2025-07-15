import os
import json
import requests
import time
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
import numpy as np
from PIL import Image
from io import BytesIO
from pydub import AudioSegment
import sys
sys.path.append('.')
from app import upload_file_to_s3

# --- CONFIGURABLE ---
SEGMENTS_JSON = 'segments/audio_0f90ab1f177c41a6af05ccc938efa290_segments.json'
SLIDES_JSON = 'segments/slides.json'
EMPTY_SPACES_JSON = 'heygen_empty_spaces.json'
MAIN_VIDEO = 'uploads/Team_Management_Intro.mp4'
HEYGEN_API_KEY = os.getenv('HEYGEN_API_KEY', 'YOUR_HEYGEN_API_KEY')
HEYGEN_AVATAR_ID = 'Angela-inblackskirt-20220820'  # Example female avatar_id
HEYGEN_OUTPUT_DIR = 'heygen_videos'
FINAL_OUTPUT = 'uploads/heygen_overlay_Team_Management_Intro.mp4'
AUDIO_FILE = 'uploads/Team_Management_Intro.mp3'  # Main audio file for the video
S3_BUCKET = os.getenv('S3_BUCKET_NAME')

os.makedirs(HEYGEN_OUTPUT_DIR, exist_ok=True)

def extract_slide_segments():
    print('Step 1: Extracting slide-wise timing info...')
    with open(SEGMENTS_JSON, 'r', encoding='utf-8') as f:
        segments_data = json.load(f)
    with open(SLIDES_JSON, 'r', encoding='utf-8') as f:
        slides = json.load(f)
    with open(EMPTY_SPACES_JSON, 'r', encoding='utf-8') as f:
        empty_spaces = json.load(f)
    slide_segments = []
    for space in empty_spaces:
        slide_number = space['slide_number']
        slide = next((s for s in slides if s['slide_number'] == slide_number), None)
        segment = next((seg for seg in segments_data['segments'] if seg['segment_id'] == slide_number), None)
        if not slide or not segment:
            print(f'Warning: Slide or segment not found for slide_number {slide_number}')
            continue
        slide_segments.append({
            'slide_number': slide_number,
            'start_time': segment['start_time'],
            'end_time': segment['end_time'],
            'empty_space': space['empty_space']
        })
    print(f'Found {len(slide_segments)} slides needing HeyGen avatars.')
    return slide_segments

def extract_and_upload_audio_segment(audio_file, start_time, end_time, slide_number):
    print(f'Extracting audio for slide {slide_number}: {start_time}-{end_time}s')
    audio = AudioSegment.from_file(audio_file)
    segment_audio = audio[start_time * 1000:end_time * 1000]
    segment_path = os.path.join(HEYGEN_OUTPUT_DIR, f'slide_{slide_number}_audio.mp3')
    segment_audio.export(segment_path, format='mp3')
    print(f'Uploading audio segment for slide {slide_number} to S3...')
    s3_key = f'heygen_segments/slide_{slide_number}_audio.mp3'
    s3_url = upload_file_to_s3(segment_path, s3_key, bucket_name=S3_BUCKET)
    print(f'S3 URL for slide {slide_number}: {s3_url}')
    return s3_url

def call_heygen_api_audio(audio_url, slide_number, width=512, height=512):
    print(f'Calling HeyGen API for slide {slide_number} with audio...')
    api_key = HEYGEN_API_KEY
    avatar_id = HEYGEN_AVATAR_ID
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal"
                },
                "voice": {
                    "type": "audio",
                    "input_audio": audio_url
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
            print(f'HeyGen API error for slide {slide_number}: {resp.text}')
            return None
        video_id = resp.json()["data"]["video_id"]
        print(f'Video requested, id: {video_id}')
        # Poll for completion
        status_url = f"https://api.heygen.com/v1/video_status.get?video_id={video_id}"
        while True:
            status_resp = requests.get(status_url, headers=headers)
            status_json = status_resp.json()
            status = status_json["data"]["status"]
            if status == "completed":
                video_url = status_json["data"]["video_url"]
                print(f'Video ready: {video_url}')
                video_content = requests.get(video_url).content
                video_path = os.path.join(HEYGEN_OUTPUT_DIR, f'slide_{slide_number}_heygen.mp4')
                with open(video_path, "wb") as f:
                    f.write(video_content)
                print(f'HeyGen video saved: {video_path}')
                return video_path
            elif status == "failed":
                print(f'HeyGen video generation failed for slide {slide_number}.')
                return None
            else:
                print(f'Processing slide {slide_number}...')
                time.sleep(5)
    except Exception as e:
        print(f'Error calling HeyGen API for slide {slide_number}: {e}')
        return None

def strip_audio(video_path):
    print(f'Stripping audio from {video_path}...')
    try:
        clip = VideoFileClip(video_path)
        no_audio_path = video_path.replace('.mp4', '_noaudio.mp4')
        clip = clip.without_audio()
        clip.write_videofile(no_audio_path, codec='libx264', audio=False, verbose=False, logger=None)
        clip.close()
        print(f'Audio stripped: {no_audio_path}')
        return no_audio_path
    except Exception as e:
        print(f'Error stripping audio: {e}')
        return None

def resize_video_to_space(video_path, width, height):
    print(f'Resizing {video_path} to {width}x{height}...')
    try:
        clip = VideoFileClip(video_path)
        resized = clip.resize(newsize=(width, height))
        resized_path = video_path.replace('.mp4', f'_resized.mp4')
        resized.write_videofile(resized_path, codec='libx264', audio=False, verbose=False, logger=None)
        clip.close()
        resized.close()
        print(f'Resized video saved: {resized_path}')
        return resized_path
    except Exception as e:
        print(f'Error resizing video: {e}')
        return None

def overlay_heygen_videos(slide_segments):
    print('Overlaying HeyGen videos on main video...')
    try:
        main_video = VideoFileClip(MAIN_VIDEO)
        overlays = []
        for slide in slide_segments:
            slide_number = slide['slide_number']
            start = slide['start_time']
            end = slide['end_time']
            space = slide['empty_space']
            width = int(space['width'])
            height = int(space['height'])
            x = int(space['x'])
            y = int(space['y'])
            heygen_vid_path = os.path.join(HEYGEN_OUTPUT_DIR, f'slide_{slide_number}_heygen_noaudio_resized.mp4')
            if not os.path.exists(heygen_vid_path):
                print(f'HeyGen video not found for slide {slide_number}, skipping overlay.')
                continue
            try:
                heygen_clip = VideoFileClip(heygen_vid_path).set_start(start).set_end(end).set_position((x, y))
                overlays.append(heygen_clip)
            except Exception as e:
                print(f'Error loading overlay for slide {slide_number}: {e}')
        if overlays:
            final = CompositeVideoClip([main_video] + overlays, size=main_video.size)
            final.write_videofile(FINAL_OUTPUT, codec='libx264', audio_codec='aac', fps=main_video.fps, threads=4, verbose=False, logger=None)
            final.close()
            print(f'Final video with overlays saved: {FINAL_OUTPUT}')
        else:
            print('No overlays to apply.')
        main_video.close()
    except Exception as e:
        print(f'Error during overlay: {e}')

def main():
    slide_segments = extract_slide_segments()
    for slide in slide_segments:
        slide_number = slide['slide_number']
        start_time = slide['start_time']
        end_time = slide['end_time']
        width = int(slide['empty_space']['width'])
        height = int(slide['empty_space']['height'])
        # Step 2: Extract and upload audio segment
        audio_url = extract_and_upload_audio_segment(AUDIO_FILE, start_time, end_time, slide_number)
        print(f'Audio URL: {audio_url}')
        if not audio_url:
            continue
        # Step 3: Call HeyGen API with audio
        heygen_vid = call_heygen_api_audio(audio_url, slide_number, width=width, height=height)
        if not heygen_vid:
            continue
        # Step 4: Strip audio
        noaudio_vid = strip_audio(heygen_vid)
        if not noaudio_vid:
            continue
        # Step 5: Resize to fit empty space
        resized_vid = resize_video_to_space(noaudio_vid, width, height)
        if not resized_vid:
            continue
        # Rename for overlay step
        final_vid_path = os.path.join(HEYGEN_OUTPUT_DIR, f'slide_{slide_number}_heygen_noaudio_resized.mp4')
        os.rename(resized_vid, final_vid_path)
    # Step 6: Overlay all HeyGen videos
    overlay_heygen_videos(slide_segments)

if __name__ == '__main__':
    main() 