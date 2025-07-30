#!/usr/bin/env python3
"""
Test script for video generation with comprehensive debug logging
"""

import os
import sys
import time
import psutil
from video_generator import VideoGenerator

def test_video_generation():
    """Test video generation with debug logging"""
    
    print("🧪 Testing video generation with debug logging...")
    print(f"📊 System memory: {psutil.virtual_memory().total / (1024**3):.1f} GB total")
    print(f"📊 Available memory: {psutil.virtual_memory().available / (1024**3):.1f} GB")
    
    # Check if required files exist
    segments_file = "segments/DeployTest_46b98c1a_segments.json"
    word_srt_file = "transcripts/DeployTest_46b98c1a_words.srt"
    audio_file = "uploads/DeployTest_46b98c1a/audio_0c6b648f778e4441a17e940e0edc7584_bgm.mp3"
    output_file = "test_output_debug.mp4"
    
    print(f"🔍 Checking input files...")
    for file_path in [segments_file, word_srt_file, audio_file]:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path) / (1024*1024)  # MB
            print(f"✅ {file_path}: {size:.2f} MB")
        else:
            print(f"❌ {file_path}: NOT FOUND")
            return False
    
    print(f"🎬 Initializing VideoGenerator...")
    video_gen = VideoGenerator(
        segments_folder="segments",
        transcripts_folder="transcripts", 
        font_folder='circular-std-font-family'
    )
    
    # Configure transitions
    video_gen.enable_transitions(True)
    video_gen.set_transition_duration(0.6)
    
    print(f"🚀 Starting video generation test...")
    start_time = time.time()
    
    try:
        video_gen.generate_video(
            segments_file=segments_file,
            word_srt_file=word_srt_file,
            audio_file=audio_file,
            output_file=output_file,
            show_subtitles=True,
            selected_background='1.jpg'
        )
        
        total_time = time.time() - start_time
        print(f"✅ Video generation completed successfully in {total_time:.2f}s")
        
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / (1024*1024)  # MB
            print(f"📁 Output file: {output_file} ({file_size:.2f} MB)")
            return True
        else:
            print(f"❌ Output file not found!")
            return False
            
    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ Video generation failed after {total_time:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_video_generation()
    if success:
        print("🎉 Test completed successfully!")
    else:
        print("💥 Test failed!")
        sys.exit(1) 