#!/usr/bin/env python3
"""
Test script for video generation functionality
"""

import os
import json
from video_generator import VideoGenerator

def test_video_generation():
    """Test the video generation with sample data"""
    
    # Check if required folders exist
    segments_folder = "segments"
    transcripts_folder = "transcripts"
    font_folder = "circular-std-font-family"
    
    if not os.path.exists(segments_folder):
        print(f"❌ Segments folder not found: {segments_folder}")
        return False
    
    if not os.path.exists(transcripts_folder):
        print(f"❌ Transcripts folder not found: {transcripts_folder}")
        return False
    
    if not os.path.exists(font_folder):
        print(f"❌ Font folder not found: {font_folder}")
        return False
    
    # Check for font file
    font_file = os.path.join(font_folder, "CircularStd-Book.ttf")
    if not os.path.exists(font_file):
        print(f"❌ Font file not found: {font_file}")
        return False
    
    print("✅ All required folders and files found")
    
    # Initialize video generator
    try:
        video_gen = VideoGenerator(segments_folder, transcripts_folder, font_folder)
        print("✅ Video generator initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing video generator: {e}")
        return False
    
    # List available files
    print("\n📁 Available files:")
    
    segments_files = [f for f in os.listdir(segments_folder) if f.endswith('_segments.json')]
    if segments_files:
        print(f"  Segments files: {segments_files}")
    else:
        print("  No segments files found")
    
    word_srt_files = [f for f in os.listdir(transcripts_folder) if f.endswith('_words.srt')]
    if word_srt_files:
        print(f"  Word SRT files: {word_srt_files}")
    else:
        print("  No word SRT files found")
    
    markdown_files = [f for f in os.listdir(segments_folder) if f.endswith('.md')]
    if markdown_files:
        print(f"  Markdown files: {len(markdown_files)} found")
    else:
        print("  No markdown files found")
    
    print("\n🎬 Video generation is ready!")
    print("   - Upload an audio file through the web interface")
    print("   - Process it to generate segments and markdown files")
    print("   - Click 'Generate Video' to create the final video")
    
    return True

if __name__ == "__main__":
    test_video_generation() 