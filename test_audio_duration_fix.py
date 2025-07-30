#!/usr/bin/env python3
"""
Test script to verify that the audio duration fix is working correctly.
This script tests that slide durations now match the actual audio duration
instead of the SRT file duration.
"""

import os
import sys
import json
import tempfile
import shutil
from mainModel import (
    transcribe_audio, 
    segment_transcript_variable_duration,
    create_srt_file,
    create_word_srt_file
)

def test_audio_duration_fix():
    """Test that audio duration is used instead of SRT duration for slide generation"""
    print("🧪 TESTING AUDIO DURATION FIX")
    print("=" * 50)
    
    # Create a temporary test directory
    test_dir = tempfile.mkdtemp()
    session_uploads = os.path.join(test_dir, "uploads")
    session_transcripts = os.path.join(test_dir, "transcripts")
    session_segments = os.path.join(test_dir, "segments")
    
    os.makedirs(session_uploads, exist_ok=True)
    os.makedirs(session_transcripts, exist_ok=True)
    os.makedirs(session_segments, exist_ok=True)
    
    try:
        # Step 1: Create a test audio file (or use existing one)
        test_audio_path = "test_audio.mp3"
        if not os.path.exists(test_audio_path):
            print("❌ Test audio file not found. Please create a test_audio.mp3 file first.")
            return False
        
        print(f"✅ Using test audio: {test_audio_path}")
        
        # Step 2: Transcribe audio and get actual duration
        print("\n📝 Transcribing audio...")
        sentence_segments, word_segments, audio_duration = transcribe_audio(test_audio_path)
        print(f"✅ Audio duration from words: {audio_duration:.2f}s")
        print(f"✅ Sentence segments: {len(sentence_segments)}")
        print(f"✅ Word segments: {len(word_segments)}")
        
        # Step 3: Create SRT files
        base_filename = "test_audio"
        srt_filename = f"{base_filename}_sentences.srt"
        srt_filepath = os.path.join(session_transcripts, srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        
        word_srt_filename = f"{base_filename}_words.srt"
        word_srt_filepath = os.path.join(session_transcripts, word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        
        print(f"✅ Created SRT files")
        
        # Step 4: Create segments using audio duration
        print("\n🎯 Creating segments with audio duration...")
        audio_segments = segment_transcript_variable_duration(sentence_segments, srt_filepath, audio_duration)
        
        print(f"✅ Created {len(audio_segments)} segments")
        
        # Step 5: Verify that segment durations match audio duration
        total_segment_duration = 0
        for i, segment in enumerate(audio_segments):
            duration = segment['end'] - segment['start']
            total_segment_duration += duration
            print(f"  Segment {i+1}: {segment['start']:.2f}s - {segment['end']:.2f}s (duration: {duration:.2f}s)")
        
        print(f"\n📊 Duration Analysis:")
        print(f"  Audio duration: {audio_duration:.2f}s")
        print(f"  Total segment duration: {total_segment_duration:.2f}s")
        print(f"  Difference: {abs(total_segment_duration - audio_duration):.2f}s")
        
        # Check if durations match (allow small tolerance for floating point)
        tolerance = 0.1  # 100ms tolerance
        if abs(total_segment_duration - audio_duration) <= tolerance:
            print("✅ SUCCESS: Segment durations match audio duration!")
            return True
        else:
            print("❌ FAILURE: Segment durations don't match audio duration!")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False
    finally:
        # Clean up
        shutil.rmtree(test_dir)
        print(f"\n🧹 Cleaned up test directory: {test_dir}")

if __name__ == "__main__":
    success = test_audio_duration_fix()
    if success:
        print("\n🎉 AUDIO DURATION FIX TEST PASSED!")
        print("The slide duration now correctly matches the audio duration.")
    else:
        print("\n❌ AUDIO DURATION FIX TEST FAILED!")
        print("Please check the implementation.")
    
    sys.exit(0 if success else 1) 