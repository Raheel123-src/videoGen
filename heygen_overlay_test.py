import os
import time
import json
import requests
from urllib.parse import urlparse
from moviepy.editor import VideoFileClip, CompositeVideoClip
from dotenv import load_dotenv

load_dotenv()

HEYGEN_API_KEY = os.getenv('HEYGEN_API_KEY')
AVATAR_ID = 'Jocelyn_sitting_office_side'
S3_LINKS_FILE = 'heygen_videos/s3_links.txt'
EMPTY_SPACES_FILE = 'heygen_empty_spaces.json'
MAIN_VIDEO = '/Users/raheel/Desktop/Lisa/Voice-over-to-video/uploads/Team_Management_Intro.mp4'  # Change this to your generated video path
OUTPUT_VIDEO = 'heygen_videos/overlay_test_output.mp4'
HEYGEN_VID_DIR = 'heygen_videos'

os.makedirs(HEYGEN_VID_DIR, exist_ok=True)

def read_audio_links(file_path):
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def read_empty_spaces(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def create_heygen_video(audio_url, avatar_id):
    headers = {
        'Authorization': f'Bearer {HEYGEN_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id
                },
                "voice": {
                    "type": "audio",
                    "audio_url": audio_url
                }
            }
        ]
    }
    response = requests.post('https://api.heygen.com/v2/video/generate', json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data['data']['video_id']

def poll_video_status(video_id):
    status_url = f'https://api.heygen.com/v1/video_status.get?video_id={video_id}'
    headers = {
        'accept': 'application/json',
        'x-api-key': HEYGEN_API_KEY,
    }
    time.sleep(5)
    poll_count = 0
    while True:
        try:
            resp = requests.get(status_url, headers=headers)
            if resp.status_code == 404:
                print(f'[{poll_count}] Video not found yet, retrying...')
                time.sleep(3)
                poll_count += 1
                continue
            resp.raise_for_status()
            data = resp.json()
            status = data['data']['status']
            if status == 'completed':
                return data['data']['video_url']
            elif status == 'failed':
                print(f'HeyGen video generation failed. Status: {data}')
                return None
            print(f'[{poll_count}] Current status: {status}')
        except requests.exceptions.RequestException as e:
            print(f'Error polling status: {e}')
        time.sleep(5)
        poll_count += 1

def download_video(video_url, output_path):
    with requests.get(video_url, stream=True) as r:
        r.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return output_path

def strip_audio_and_resize(input_path, output_path, width, height):
    try:
        clip = VideoFileClip(input_path)
        noaudio_clip = clip.without_audio()
        resized_clip = noaudio_clip.resize((width, height))
        resized_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
        clip.close()
        noaudio_clip.close()
        resized_clip.close()
    except Exception as e:
        print(f'Error processing {input_path}: {e}')

def overlay_heygen_videos(main_video_path, overlays_info, output_path):
    main_video = VideoFileClip(main_video_path)
    overlays = []
    for info in overlays_info:
        try:
            clip = VideoFileClip(info['video_path']).set_start(info['start']).set_end(info['end']).set_position((info['x'], info['y']))
            overlays.append(clip)
        except Exception as e:
            print(f'Error loading overlay {info["video_path"]}: {e}')
    if overlays:
        final = CompositeVideoClip([main_video] + overlays, size=main_video.size)
        final.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=main_video.fps, threads=4, verbose=False, logger=None)
        final.close()
    main_video.close()

def main():
    audio_urls = read_audio_links(S3_LINKS_FILE)
    empty_spaces = read_empty_spaces(EMPTY_SPACES_FILE)
    overlays_info = []
    for idx, (audio_url, space) in enumerate(zip(audio_urls, empty_spaces)):
        slide_number = space.get('slide_number', idx+1)
        start = space.get('start_time', 0)
        end = space.get('end_time', 0)
        x = int(space['empty_space']['x'])
        y = int(space['empty_space']['y'])
        width = int(space['empty_space']['width'])
        height = int(space['empty_space']['height'])
        print(f"\nProcessing slide {slide_number}: {audio_url}")
        try:
            video_id = create_heygen_video(audio_url, AVATAR_ID)
            print(f'Video ID: {video_id}')
            print('Waiting for video to be ready...')
            video_url = poll_video_status(video_id)
            if not video_url:
                print(f'Failed to generate HeyGen video for slide {slide_number}')
                continue
            print(f'Video ready at: {video_url}')
            local_path = os.path.join(HEYGEN_VID_DIR, f'slide_{slide_number}_heygen.mp4')
            print('Downloading video...')
            download_video(video_url, local_path)
            print(f'Video downloaded to: {local_path}')
            # Strip audio and resize
            resized_path = os.path.join(HEYGEN_VID_DIR, f'slide_{slide_number}_heygen_noaudio_resized.mp4')
            strip_audio_and_resize(local_path, resized_path, width, height)
            # Robust: check if resized file exists
            if not os.path.exists(resized_path):
                print(f'Warning: Resized HeyGen video missing for slide {slide_number}, skipping overlay for this slide.')
                continue
            overlays_info.append({
                'video_path': resized_path,
                'start': space.get('start_time', 0),
                'end': space.get('end_time', 0),
                'x': x,
                'y': y
            })
        except Exception as e:
            print(f"Failed to process {audio_url}: {e}")
    # Overlay all HeyGen videos on the main video
    print('Overlaying HeyGen videos on main video...')
    overlay_heygen_videos(MAIN_VIDEO, overlays_info, OUTPUT_VIDEO)
    print(f'Final video with overlays saved to: {OUTPUT_VIDEO}')

if __name__ == '__main__':
    main() 