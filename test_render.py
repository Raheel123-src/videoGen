#!/usr/bin/env python3

from video_generator import VideoGenerator
from PIL import Image, ImageDraw, ImageFont
import json
import os

# Initialize video generator
vg = VideoGenerator('segments', 'transcripts', 'circular-std-font-family')

# Load segments and presentation
with open('segments/audio_79577704ee634451909ba6dea0ec78e2_segments.json', 'r') as f:
    segments_data = json.load(f)

with open('segments/presentation.md', 'r') as f:
    all_sections = f.read().split('\n---\n')

# Test rendering for each segment
for idx, segment in enumerate(segments_data['segments'][:3]):  # Test first 3 segments
    section_index = segment['visual_content'].get('section_index', idx)
    markdown_content = all_sections[section_index]
    elements = vg.parse_markdown_content(markdown_content)
    
    print(f"\n=== Testing Segment {idx} (Section {section_index}) ===")
    title = next((el['text'] for el in elements if el['type'] == 'title'), "NO TITLE")
    print(f"Title: {title}")
    
    # Test rendering at different times
    for t in [0.1, 1.0, 2.0]:
        img = vg.create_slide_image(elements, segment['start_time'] + t, segment['start_time'])
        print(f"  Time {t}s: Image size {img.size}, mode {img.mode}")
        
        # Save test image
        img.save(f'test_segment_{idx}_time_{t}.png')
        print(f"  Saved: test_segment_{idx}_time_{t}.png")

print("\nTest complete! Check the generated PNG files to see what content is being rendered.") 

background_dir = 'background'
output_dir = 'background_test_outputs'
os.makedirs(output_dir, exist_ok=True)

font_path = 'circular-std-font-family/CircularStd-Bold.ttf'
try:
    font = ImageFont.truetype(font_path, 80)
except:
    font = ImageFont.load_default()

for fname in os.listdir(background_dir):
    if fname.lower().endswith(('.jpg', '.png')):
        path = os.path.join(background_dir, fname)
        img = Image.open(path)
        print(f'[TEST_BG] {fname}: mode={img.mode}, size={img.size}')
        if img.mode != 'RGB':
            print(f'[TEST_BG][WARN] {fname} is mode {img.mode}, converting to RGB.')
            img = img.convert('RGB')
        img = img.resize((1920, 1080))
        draw = ImageDraw.Draw(img)
        draw.text((100, 100), 'TEST', fill=(255,0,0), font=font)
        out_path = os.path.join(output_dir, f'test_{fname}.png')
        img.save(out_path)
        print(f'[TEST_BG] Saved test image: {out_path}') 