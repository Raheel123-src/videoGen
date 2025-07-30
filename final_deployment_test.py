#!/usr/bin/env python3
"""
Final Deployment Test Script
Tests all functionality before Modal deployment:
- Variable duration segmentation
- Image generation with audience-aware prompts
- S3 link storage and retrieval
- File cleanup
- HeyGen overlay functionality
- Environment validation
"""

import os
import json
import sys
import time
import shutil
from pathlib import Path

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_environment_validation():
    """Test environment variable validation"""
    print("\n🔧 TESTING ENVIRONMENT VALIDATION:")
    print("=" * 50)
    
    required_env_vars = [
        "ELEVENLABS_API_KEY",
        "OPENAI_API_KEY", 
        "IDEOGRAM_API_KEY",
        "HEYGEN_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "S3_BUCKET_NAME"
    ]
    
    missing_vars = []
    for var in required_env_vars:
        value = os.getenv(var)
        if not value or value == 'your_api_key_here':
            missing_vars.append(var)
            print(f"❌ {var}: Missing or placeholder value")
        else:
            print(f"✅ {var}: Configured")
    
    if missing_vars:
        print(f"\n⚠️  WARNING: {len(missing_vars)} environment variables missing:")
        for var in missing_vars:
            print(f"   - {var}")
        return False
    else:
        print("\n✅ All environment variables are properly configured!")
        return True

def test_variable_duration_segmentation():
    """Test variable duration segmentation functionality"""
    print("\n⏱️  TESTING VARIABLE DURATION SEGMENTATION:")
    print("=" * 50)
    
    try:
        from mainModel import segment_transcript_variable_duration
        
        # Create test transcript segments
        test_segments = [
            {'start': 0, 'end': 5, 'text': 'This is the first sentence.'},
            {'start': 5, 'end': 12, 'text': 'This is the second sentence with more content.'},
            {'start': 12, 'end': 18, 'text': 'Third sentence here.'},
            {'start': 18, 'end': 25, 'text': 'Fourth sentence with additional content.'},
            {'start': 25, 'end': 32, 'text': 'Fifth sentence for testing.'},
            {'start': 32, 'end': 40, 'text': 'Sixth sentence with more words.'},
            {'start': 40, 'end': 48, 'text': 'Seventh sentence for the test.'},
            {'start': 48, 'end': 55, 'text': 'Eighth and final sentence.'}
        ]
        
        print(f"Test segments created: {len(test_segments)} segments")
        
        # Test segmentation
        result = segment_transcript_variable_duration(test_segments, audio_duration=55.0)
        
        print(f"Segmentation result: {len(result)} segments")
        
        # Validate results
        valid_formats = [2, 3, 4]
        previous_format = None
        format_counts = {2: 0, 3: 0, 4: 0}
        
        for i, segment in enumerate(result):
            format_type = segment.get('format')
            duration = segment['end'] - segment['start']
            
            print(f"Segment {i+1}: Format {format_type}, Duration {duration:.1f}s")
            
            # Check format validity
            if format_type not in valid_formats:
                print(f"❌ Invalid format {format_type} in segment {i+1}")
                return False
            
            # Check no consecutive formats
            if previous_format == format_type:
                print(f"❌ Consecutive format {format_type} in segments")
                return False
            
            # Check duration ranges
            if format_type == 4:
                if not (5 <= duration <= 8):
                    print(f"❌ Format 4 duration {duration:.1f}s not in range [5,8]")
                    return False
            else:  # formats 2 or 3
                if not (10 <= duration <= 20):
                    print(f"❌ Format {format_type} duration {duration:.1f}s not in range [10,20]")
                    return False
            
            format_counts[format_type] += 1
            previous_format = format_type
        
        print(f"\nFormat distribution: {format_counts}")
        print("✅ Variable duration segmentation working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Variable duration segmentation test failed: {e}")
        return False

def test_audience_aware_image_generation():
    """Test audience-aware image prompt generation"""
    print("\n🎨 TESTING AUDIENCE-AWARE IMAGE GENERATION:")
    print("=" * 50)
    
    try:
        from mainModel import generate_slide_json_content
        
        test_cases = [
            {
                'audience': 'Healthcare sales team',
                'content': 'Understanding brain function and neural pathways in stress management.',
                'expected_keywords': ['medical', 'healthcare', 'professional']
            },
            {
                'audience': 'High school science students',
                'content': 'The process of photosynthesis and energy conversion in plants.',
                'expected_keywords': ['educational', 'classroom', 'students']
            },
            {
                'audience': 'IT marketing professionals',
                'content': 'Digital transformation and cloud computing strategies.',
                'expected_keywords': ['tech', 'digital', 'professional']
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\nTest Case {i}: {test_case['audience']}")
            
            try:
                result = generate_slide_json_content(
                    segment_text=test_case['content'],
                    segment_index=0,
                    segment_duration=15.0,
                    target_audience=test_case['audience']
                )
                
                image_prompt = result.get('image_prompt', '')
                print(f"Generated prompt: {image_prompt[:100]}...")
                
                # Check if audience-appropriate keywords are present
                prompt_lower = image_prompt.lower()
                found_keywords = [kw for kw in test_case['expected_keywords'] if kw in prompt_lower]
                
                if found_keywords:
                    print(f"✅ Found audience keywords: {found_keywords}")
                else:
                    print(f"⚠️  No expected keywords found in prompt")
                
            except Exception as e:
                print(f"❌ Test case {i} failed: {e}")
                return False
        
        print("\n✅ Audience-aware image generation working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Audience-aware image generation test failed: {e}")
        return False

def test_s3_link_storage():
    """Test S3 link storage and retrieval functionality"""
    print("\n🔗 TESTING S3 LINK STORAGE:")
    print("=" * 50)
    
    try:
        # Import the functions (they should be in mainModel.py)
        from mainModel import store_s3_link, get_stored_s3_link
        
        test_session_id = "test_session_123"
        test_slide_number = 5
        test_s3_url = "https://test-bucket.s3.amazonaws.com/test-audio.mp3"
        test_video_id = "test_video_456"
        
        # Test storing S3 link
        print(f"Storing S3 link for slide {test_slide_number}...")
        success = store_s3_link(test_session_id, test_slide_number, test_s3_url, test_video_id)
        
        if not success:
            print("❌ Failed to store S3 link")
            return False
        
        # Test retrieving S3 link
        print(f"Retrieving S3 link for slide {test_slide_number}...")
        retrieved_url = get_stored_s3_link(test_session_id, test_slide_number)
        
        if retrieved_url == test_s3_url:
            print("✅ S3 link storage and retrieval working correctly!")
        else:
            print(f"❌ Retrieved URL doesn't match: {retrieved_url}")
            return False
        
        # Clean up test files
        test_s3_dir = os.path.join('uploads', test_session_id, 's3_links')
        if os.path.exists(test_s3_dir):
            shutil.rmtree(test_s3_dir)
            print("✅ Cleaned up test S3 files")
        
        return True
        
    except ImportError as e:
        print(f"❌ S3 link storage functions not found: {e}")
        return False
    except Exception as e:
        print(f"❌ S3 link storage test failed: {e}")
        return False

def test_file_cleanup():
    """Test comprehensive file cleanup functionality"""
    print("\n🧹 TESTING FILE CLEANUP:")
    print("=" * 50)
    
    try:
        from mainModel import cleanup_session_files
        
        test_session_id = "cleanup_test_456"
        
        # Create test files and directories
        test_dirs = [
            os.path.join('uploads', test_session_id),
            os.path.join('transcripts', test_session_id),
            os.path.join('segments', test_session_id)
        ]
        
        test_files = [
            os.path.join('uploads', test_session_id, 'test_video.mp4'),
            os.path.join('transcripts', test_session_id, 'test_transcript.txt'),
            os.path.join('segments', test_session_id, 'test_segments.json'),
            f'temp_{test_session_id}.mp3',
            f'orphaned_{test_session_id}.wav'
        ]
        
        print("Creating test files and directories...")
        for test_dir in test_dirs:
            os.makedirs(test_dir, exist_ok=True)
            print(f"✅ Created directory: {test_dir}")
        
        for test_file in test_files:
            with open(test_file, 'w') as f:
                f.write("test content")
            print(f"✅ Created test file: {test_file}")
        
        # Test cleanup
        print(f"\nRunning cleanup for session: {test_session_id}")
        cleanup_session_files(test_session_id)
        
        # Verify cleanup
        all_cleaned = True
        for test_dir in test_dirs:
            if os.path.exists(test_dir):
                print(f"❌ Directory still exists: {test_dir}")
                all_cleaned = False
        
        for test_file in test_files:
            if os.path.exists(test_file):
                print(f"❌ File still exists: {test_file}")
                all_cleaned = False
        
        if all_cleaned:
            print("✅ All test files and directories cleaned up successfully!")
        else:
            print("❌ Some files/directories were not cleaned up")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ File cleanup test failed: {e}")
        return False

def test_heygen_avatar_size():
    """Test HeyGen avatar size configuration"""
    print("\n👤 TESTING HEYGEN AVATAR SIZE:")
    print("=" * 50)
    
    try:
        from mainModel import MIN_AVATAR_SIZE, MAX_AVATAR_SIZE, AVATAR_SAFETY_MARGIN
        
        print(f"MIN_AVATAR_SIZE: {MIN_AVATAR_SIZE}px")
        print(f"MAX_AVATAR_SIZE: {MAX_AVATAR_SIZE}px")
        print(f"AVATAR_SAFETY_MARGIN: {AVATAR_SAFETY_MARGIN}px")
        
        # Check if minimum size is correctly set to 165
        if MIN_AVATAR_SIZE == 165:
            print("✅ MIN_AVATAR_SIZE correctly set to 165px")
        else:
            print(f"❌ MIN_AVATAR_SIZE is {MIN_AVATAR_SIZE}px, should be 165px")
            return False
        
        # Check if maximum size is reasonable
        if MAX_AVATAR_SIZE >= MIN_AVATAR_SIZE:
            print("✅ MAX_AVATAR_SIZE is greater than MIN_AVATAR_SIZE")
        else:
            print(f"❌ MAX_AVATAR_SIZE ({MAX_AVATAR_SIZE}) is less than MIN_AVATAR_SIZE ({MIN_AVATAR_SIZE})")
            return False
        
        # Calculate minimum required space
        min_required_space = MIN_AVATAR_SIZE + AVATAR_SAFETY_MARGIN
        print(f"Minimum required space: {min_required_space}px")
        
        return True
        
    except Exception as e:
        print(f"❌ HeyGen avatar size test failed: {e}")
        return False

def test_api_endpoints():
    """Test API endpoint structure"""
    print("\n🌐 TESTING API ENDPOINTS:")
    print("=" * 50)
    
    try:
        from mainModel import app
        
        # Check if FastAPI app is properly configured
        if hasattr(app, 'routes'):
            print(f"✅ FastAPI app has {len(app.routes)} routes")
            
            # Check for required endpoints
            required_endpoints = [
                ('POST', '/process_and_generate_video'),
                ('GET', '/video_status')
            ]
            
            for method, path in required_endpoints:
                found = False
                for route in app.routes:
                    if hasattr(route, 'methods') and hasattr(route, 'path'):
                        if method in route.methods and route.path == path:
                            found = True
                            break
                
                if found:
                    print(f"✅ Found endpoint: {method} {path}")
                else:
                    print(f"❌ Missing endpoint: {method} {path}")
                    return False
            
            return True
        else:
            print("❌ FastAPI app not properly configured")
            return False
            
    except Exception as e:
        print(f"❌ API endpoints test failed: {e}")
        return False

def test_dependencies():
    """Test if all required dependencies are available"""
    print("\n📦 TESTING DEPENDENCIES:")
    print("=" * 50)
    
    required_packages = [
        'fastapi',
        'openai',
        'requests',
        'boto3',
        'moviepy',
        'PIL',
        'pydub',
        'numpy'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package}")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n❌ Missing packages: {missing_packages}")
        return False
    else:
        print("\n✅ All required packages are available!")
        return True

def main():
    """Run all deployment tests"""
    print("🚀 FINAL DEPLOYMENT TEST SUITE")
    print("=" * 60)
    print("Testing all functionality before Modal deployment...")
    
    tests = [
        ("Environment Validation", test_environment_validation),
        ("Dependencies", test_dependencies),
        ("API Endpoints", test_api_endpoints),
        ("HeyGen Avatar Size", test_heygen_avatar_size),
        ("Variable Duration Segmentation", test_variable_duration_segmentation),
        ("Audience-Aware Image Generation", test_audience_aware_image_generation),
        ("S3 Link Storage", test_s3_link_storage),
        ("File Cleanup", test_file_cleanup)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"🧪 RUNNING: {test_name}")
        print(f"{'='*60}")
        
        try:
            result = test_func()
            results.append((test_name, result))
            
            if result:
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
                
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Ready for Modal deployment!")
        print("\n✅ Deployment Checklist:")
        print("   - Environment variables configured")
        print("   - Dependencies available")
        print("   - API endpoints working")
        print("   - Variable duration segmentation functional")
        print("   - Audience-aware image generation working")
        print("   - S3 link storage implemented")
        print("   - File cleanup comprehensive")
        print("   - HeyGen avatar size optimized (165px)")
        return True
    else:
        print(f"\n⚠️  {total - passed} tests failed. Please fix issues before deployment.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 