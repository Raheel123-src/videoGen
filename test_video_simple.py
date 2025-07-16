#!/usr/bin/env python3

from video_generator import VideoGenerator
from moviepy.editor import VideoClip
import numpy as np
import json

# Initialize video generator
vg = VideoGenerator('segments', 'transcripts', 'circular-std-font-family')

# Load segments and presentation
with open('segments/audio_79577704ee634451909ba6dea0ec78e2_segments.json', 'r') as f:
    segments_data = json.load(f)

with open('segments/presentation.md', 'r') as f:
    all_sections = f.read().split('\n---\n')

# Test creating individual video clips
for idx, segment in enumerate(segments_data['segments'][:3]):  # Test first 3 segments
    section_index = segment['visual_content'].get('section_index', idx)
    markdown_content = all_sections[section_index]
    elements = vg.parse_markdown_content(markdown_content)
    
    print(f"\n=== Creating Video Clip for Segment {idx} (Section {section_index}) ===")
    title = next((el['text'] for el in elements if el['type'] == 'title'), "NO TITLE")
    print(f"Title: {title}")
    
    # Create a local copy of elements
    segment_elements = elements.copy()
    
    def make_frame(t):
        current_time = segment['start_time'] + t
        slide_img = vg.create_slide_image(segment_elements, current_time, segment['start_time'])
        return np.array(slide_img)
    
    # Create video clip
    duration = segment['end_time'] - segment['start_time']
    clip = VideoClip(make_frame=make_frame, duration=duration)
    
    # Test a few frames
    for t in [0.1, 1.0, 2.0]:
        frame = clip.get_frame(t)
        print(f"  Frame at {t}s: shape {frame.shape}, dtype {frame.dtype}")
    
    # Save individual clip
    output_file = f'test_clip_segment_{idx}.mp4'
    clip.write_videofile(output_file, fps=24, verbose=False, logger=None)
    clip.close()
    print(f"  Saved: {output_file}")

print("\nTest complete! Check the individual MP4 files to see if they contain the correct content.") 