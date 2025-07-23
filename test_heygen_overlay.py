import os
import json
from moviepy.editor import VideoFileClip, CompositeVideoClip

# File paths
base_video_path = 'uploads/FinalTest_ed979e99/FinalTest.mp4'
heygen_video_path = 'uploads/FinalTest_ed979e99/heygen_videos/slide_1_heygen_noaudio.mp4'
heygen_empty_spaces_path = 'segments/FinalTest_ed979e99/heygen_empty_spaces.json'
output_path = 'uploads/FinalTest_ed979e99/FinalTest_with_heygen_overlay.mp4'

# Load base video
base_clip = VideoFileClip(base_video_path)

# Load heygen empty space info
with open(heygen_empty_spaces_path, 'r', encoding='utf-8') as f:
    empty_spaces = json.load(f)

# Load heygen video (no audio)
heygen_clip_orig = VideoFileClip(heygen_video_path).without_audio()

# Prepare overlay clips
overlay_clips = []
for space in empty_spaces:
    area = space['empty_space']
    slide_number = space.get('slide_number', 1)
    start_time = space.get('start_time', 0)
    end_time = space.get('end_time', base_clip.duration)
    duration = end_time - start_time
    empty_w, empty_h = int(area['width']), int(area['height'])
    max_side = min(empty_w, empty_h)
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
    heygen_clip = heygen_clip.subclip(0, min(duration, heygen_clip.duration))
    heygen_clip = heygen_clip.set_position((x, y)).set_start(start_time).set_duration(duration)

    print(f"[DEBUG] Overlaying slide {slide_number}: x={x}, y={y}, size={max_side}, start={start_time}, end={end_time}, base=({base_clip.w},{base_clip.h})")
    overlay_clips.append(heygen_clip)

# Composite overlays onto base video
final = CompositeVideoClip([base_clip] + overlay_clips)
final.write_videofile(output_path, codec='libx264', audio_codec='aac')
print(f"[DONE] Overlay video saved to: {output_path}") 