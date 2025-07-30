#!/usr/bin/env python3
"""
Test BGM Pipeline Integration
Comprehensive test to verify BGM processing is working in mainModel pipeline
"""

import os
import sys
import json
import time
from bgm_processor import BGMProcessor
from mainModel import process_bgm_audio, create_session_directories

def test_bgm_processor_basic():
    """Test basic BGM processor functionality"""
    print("🧪 Testing Basic BGM Processor...")
    print("=" * 50)
    
    try:
        processor = BGMProcessor()
        print("✅ BGM processor initialized")
        
        # Test getting BGM files for each theme
        themes = ["Hook", "What", "Why", "How", "Ending Hook"]
        for theme in themes:
            bgm_file = processor.get_random_bgm_file(theme)
            if bgm_file and os.path.exists(bgm_file):
                file_size = os.path.getsize(bgm_file) / (1024 * 1024)  # MB
                print(f"✅ {theme}: {os.path.basename(bgm_file)} ({file_size:.1f} MB)")
            else:
                print(f"❌ {theme}: No BGM file found")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ BGM processor test failed: {e}")
        return False

def test_bgm_processing_function():
    """Test the process_bgm_audio function from mainModel"""
    print("\n🧪 Testing BGM Processing Function...")
    print("=" * 50)
    
    try:
        # Create test session
        session_id = f"test_bgm_{int(time.time())}"
        session_uploads, session_transcripts, session_segments = create_session_directories(session_id)
        
        print(f"✅ Created test session: {session_id}")
        print(f"   Uploads: {session_uploads}")
        print(f"   Transcripts: {session_transcripts}")
        print(f"   Segments: {session_segments}")
        
        # Check if we have any existing test files
        test_files = []
        
        # Look for existing audio files in uploads
        if os.path.exists("uploads"):
            for root, dirs, files in os.walk("uploads"):
                for file in files:
                    if file.endswith('.mp3'):
                        test_files.append(os.path.join(root, file))
                        break
                if test_files:
                    break
        
        if not test_files:
            print("❌ No test audio files found in uploads directory")
            print("💡 Please run a video generation first to create test files")
            return False
        
        test_audio = test_files[0]
        print(f"✅ Using test audio: {test_audio}")
        
        # Look for corresponding transcript and segments files
        audio_name = os.path.splitext(os.path.basename(test_audio))[0]
        
        # Find transcript file
        transcript_file = None
        if os.path.exists("transcripts"):
            for root, dirs, files in os.walk("transcripts"):
                for file in files:
                    if file.startswith(audio_name) and file.endswith('_sentences.srt'):
                        transcript_file = os.path.join(root, file)
                        break
                if transcript_file:
                    break
        
        # Find segments file
        segments_file = None
        if os.path.exists("segments"):
            for root, dirs, files in os.walk("segments"):
                for file in files:
                    if file.startswith(audio_name) and file.endswith('_segments.json'):
                        segments_file = os.path.join(root, file)
                        break
                if segments_file:
                    break
        
        if not transcript_file:
            print("❌ No transcript file found")
            return False
        
        if not segments_file:
            print("❌ No segments file found")
            return False
        
        print(f"✅ Found transcript: {transcript_file}")
        print(f"✅ Found segments: {segments_file}")
        
        # Test BGM processing with different volumes
        test_volumes = [50, 70, 90]
        
        for volume in test_volumes:
            print(f"\n🔊 Testing BGM with volume {volume}...")
            
            try:
                start_time = time.time()
                
                # Process BGM
                processed_audio = process_bgm_audio(
                    original_audio_path=test_audio,
                    transcription_file=transcript_file,
                    segments_file=segments_file,
                    bgm_volume=volume,
                    crossfade_duration=2000
                )
                
                processing_time = time.time() - start_time
                
                if processed_audio and os.path.exists(processed_audio):
                    original_size = os.path.getsize(test_audio) / (1024 * 1024)
                    processed_size = os.path.getsize(processed_audio) / (1024 * 1024)
                    
                    print(f"✅ BGM processing successful!")
                    print(f"   Volume: {volume}")
                    print(f"   Processing time: {processing_time:.2f}s")
                    print(f"   Original size: {original_size:.1f} MB")
                    print(f"   Processed size: {processed_size:.1f} MB")
                    print(f"   Output: {processed_audio}")
                    
                    # Check if the processed file has "_bgm" suffix
                    if "_bgm" in processed_audio:
                        print(f"✅ Correctly named with _bgm suffix")
                    else:
                        print(f"⚠️  Warning: Processed file doesn't have _bgm suffix")
                    
                else:
                    print(f"❌ BGM processing failed for volume {volume}")
                    return False
                    
            except Exception as e:
                print(f"❌ BGM processing error for volume {volume}: {e}")
                return False
        
        print(f"\n🎉 All BGM volume tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ BGM processing function test failed: {e}")
        return False

def test_bgm_in_main_pipeline():
    """Test BGM integration in the main pipeline"""
    print("\n🧪 Testing BGM in Main Pipeline...")
    print("=" * 50)
    
    try:
        # Import mainModel functions
        from mainModel import (
            generate_audio_from_script, transcribe_audio, 
            create_srt_file, create_word_srt_file, segment_transcript_variable_duration,
            create_slides_json_from_segments,
            generate_images_from_slides, add_highlights_to_slides,
            process_bgm_audio, VideoGenerator
        )
        from app import create_segments_file
        
        print("✅ Successfully imported mainModel functions")
        
        # Test the complete pipeline with BGM
        session_id = f"pipeline_test_{int(time.time())}"
        session_uploads, session_transcripts, session_segments = create_session_directories(session_id)
        
        print(f"✅ Created pipeline test session: {session_id}")
        
        # Step 1: Generate test audio from script
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
        
        # Step 5: Create slides
        try:
            slides_json_path = os.path.join(session_segments, 'slides.json')
            create_slides_json_from_segments(audio_segments, slides_json_path)
            print(f"✅ Created slides.json")
        except Exception as e:
            print(f"❌ Slides creation failed: {e}")
            return False
        
        # Step 6: Generate images (optional for BGM test)
        try:
            generate_images_from_slides(slides_json_path)
            print(f"✅ Generated images")
        except Exception as e:
            print(f"⚠️  Image generation failed (continuing): {e}")
        
        # Step 7: Add highlights (optional for BGM test)
        try:
            add_highlights_to_slides(slides_json_path)
            print(f"✅ Added highlights")
        except Exception as e:
            print(f"⚠️  Highlight addition failed (continuing): {e}")
        
        # Step 8: Process BGM (THE MAIN TEST)
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
                
                # Step 9: Generate video with BGM audio
                print(f"\n🎬 Testing video generation with BGM audio...")
                try:
                    video_gen = VideoGenerator(
                        segments_folder=session_segments,
                        transcripts_folder=session_transcripts,
                        font_folder='circular-std-font-family'
                    )
                    
                    output_video = os.path.join(session_uploads, f"test_bgm_video.mp4")
                    
                    video_gen.generate_video(
                        segments_filepath, 
                        word_srt_filepath, 
                        bgm_processed_audio,  # Use BGM processed audio
                        output_video,
                        show_subtitles=True,
                        selected_background='1.jpg'
                    )
                    
                    if os.path.exists(output_video):
                        video_size = os.path.getsize(output_video) / (1024 * 1024)
                        print(f"✅ Video generated with BGM: {output_video} ({video_size:.1f} MB)")
                        print(f"🎉 BGM pipeline test COMPLETED SUCCESSFULLY!")
                        return True
                    else:
                        print(f"❌ Video file not created")
                        return False
                        
                except Exception as e:
                    print(f"❌ Video generation failed: {e}")
                    return False
                
            else:
                print(f"❌ BGM processing failed - no output file created")
                return False
                
        except Exception as e:
            print(f"❌ BGM processing failed: {e}")
            return False
        
    except Exception as e:
        print(f"❌ Pipeline test failed: {e}")
        return False

def check_bgm_logs():
    """Check for BGM-related logs in recent files"""
    print("\n📋 Checking BGM Logs...")
    print("=" * 50)
    
    # Look for recent log files or check console output
    log_patterns = [
        "[BGM]",
        "[COMBINED API] Starting BGM processing",
        "[COMBINED API] BGM processing completed",
        "[COMBINED API] BGM processing failed"
    ]
    
    print("🔍 Look for these log patterns in your console output:")
    for pattern in log_patterns:
        print(f"   {pattern}")
    
    print("\n📝 Expected BGM Log Flow:")
    print("1. [COMBINED API] Starting BGM processing...")
    print("2. [BGM] Starting BGM processing...")
    print("3. [BGM] Loaded X segments from segments.json")
    print("4. [BGM] Loaded X transcription segments")
    print("5. [BGM] Selected BGM for Hook: filename.mp3")
    print("6. [BGM] Starting BGM overlay with volume: 80, crossfade: 2.0s")
    print("7. [BGM] BGM overlay completed: path/to/file_bgm.mp3")
    print("8. [COMBINED API] BGM processing completed, using: path/to/file_bgm.mp3")

def main():
    """Run all BGM tests"""
    print("🚀 BGM Pipeline Test Suite")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 0
    
    # Test 1: Basic BGM processor
    total_tests += 1
    if test_bgm_processor_basic():
        tests_passed += 1
        print("✅ Basic BGM processor test PASSED")
    else:
        print("❌ Basic BGM processor test FAILED")
    
    # Test 2: BGM processing function
    total_tests += 1
    if test_bgm_processing_function():
        tests_passed += 1
        print("✅ BGM processing function test PASSED")
    else:
        print("❌ BGM processing function test FAILED")
    
    # Test 3: Full pipeline test
    total_tests += 1
    if test_bgm_in_main_pipeline():
        tests_passed += 1
        print("✅ Full pipeline test PASSED")
    else:
        print("❌ Full pipeline test FAILED")
    
    # Show log information
    check_bgm_logs()
    
    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"   Tests Passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("\n🎉 ALL BGM TESTS PASSED!")
        print("✅ BGM is working correctly in the mainModel pipeline")
        print("💡 If you're not hearing BGM, try increasing the volume to 80-90")
    else:
        print("\n❌ Some BGM tests failed")
        print("🔧 Check the error messages above to fix the issues")
    
    return tests_passed == total_tests

if __name__ == "__main__":
    main() 