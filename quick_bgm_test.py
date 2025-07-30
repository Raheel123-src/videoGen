#!/usr/bin/env python3
"""
Quick BGM Test
Generate test files and test BGM processing
"""

import os
import time
from mainModel import (
    generate_audio_from_script, transcribe_audio, 
    create_srt_file, create_word_srt_file, segment_transcript_variable_duration,
    process_bgm_audio, create_session_directories
)
from app import create_segments_file

def quick_bgm_test():
    """Quick test of BGM processing"""
    print("🚀 Quick BGM Test")
    print("=" * 50)
    
    # Create test session
    session_id = f"quick_bgm_test_{int(time.time())}"
    session_uploads, session_transcripts, session_segments = create_session_directories(session_id)
    
    print(f"✅ Created test session: {session_id}")
    
    # Step 1: Generate test audio
    test_script = "Hello, this is a test script for BGM processing. We will test if background music is properly added to the video."
    print(f"📝 Test script: {test_script}")
    
    try:
        filename, filepath = generate_audio_from_script(
            test_script, 
            speed=1.0, 
            voice_id="ftDdhfYtmfGP0tFlBYA1",
            stability=0.35,
            similarity_boost=0.40
        )
        print(f"✅ Generated test audio: {filepath}")
    except Exception as e:
        print(f"❌ Audio generation failed: {e}")
        return False
    
    # Step 2: Transcribe audio
    try:
        sentence_segments, word_segments, audio_duration = transcribe_audio(filepath)
        print(f"✅ Transcribed audio: {len(sentence_segments)} sentence segments")
        print(f"✅ Audio duration: {audio_duration:.2f}s")
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        return False
    
    # Step 3: Create SRT files
    try:
        base_filename = filename.rsplit('.', 1)[0]
        srt_filename = f"{base_filename}_sentences.srt"
        srt_filepath = os.path.join(session_transcripts, srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        
        word_srt_filename = f"{base_filename}_words.srt"
        word_srt_filepath = os.path.join(session_transcripts, word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        
        print(f"✅ Created SRT files")
    except Exception as e:
        print(f"❌ SRT file creation failed: {e}")
        return False
    
    # Step 4: Create segments
    try:
        audio_segments = segment_transcript_variable_duration(sentence_segments, audio_duration=audio_duration)
        segments_filename = f"{base_filename}_segments.json"
        segments_filepath = os.path.join(session_segments, segments_filename)
        create_segments_file(audio_segments, segments_filepath)
        
        print(f"✅ Created segments file")
    except Exception as e:
        print(f"❌ Segments creation failed: {e}")
        return False
    
    # Step 5: Test BGM processing
    print(f"\n🎵 TESTING BGM PROCESSING...")
    try:
        start_time = time.time()
        
        bgm_processed_audio = process_bgm_audio(
            original_audio_path=filepath,
            transcription_file=srt_filepath,
            segments_file=segments_filepath,
            bgm_volume=80,  # Higher volume for testing
            crossfade_duration=2000
        )
        
        processing_time = time.time() - start_time
        
        if bgm_processed_audio and os.path.exists(bgm_processed_audio):
            original_size = os.path.getsize(filepath) / (1024 * 1024)
            processed_size = os.path.getsize(bgm_processed_audio) / (1024 * 1024)
            
            print(f"✅ BGM processing successful!")
            print(f"   Processing time: {processing_time:.2f}s")
            print(f"   Original audio: {filepath} ({original_size:.1f} MB)")
            print(f"   BGM processed: {bgm_processed_audio} ({processed_size:.1f} MB)")
            
            # Verify the processed file has BGM
            if "_bgm" in bgm_processed_audio:
                print(f"✅ Correctly named with _bgm suffix")
            else:
                print(f"⚠️  Warning: Processed file doesn't have _bgm suffix")
            
            print(f"\n🎉 BGM TEST COMPLETED SUCCESSFULLY!")
            print(f"📁 Files created:")
            print(f"   - Original audio: {filepath}")
            print(f"   - BGM processed: {bgm_processed_audio}")
            print(f"   - Transcript: {srt_filepath}")
            print(f"   - Segments: {segments_filepath}")
            
            return True
            
        else:
            print(f"❌ BGM processing failed - no output file created")
            return False
            
    except Exception as e:
        print(f"❌ BGM processing failed: {e}")
        return False

if __name__ == "__main__":
    success = quick_bgm_test()
    if success:
        print("\n🎉 BGM is working correctly!")
        print("💡 Check the console logs above for BGM processing messages")
    else:
        print("\n❌ BGM test failed")
        print("🔧 Check the error messages above") 