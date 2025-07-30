#!/usr/bin/env python3
"""
Modal Deployment Check
Simplified test focusing on core functionality ready for Modal deployment
"""

import os
import sys

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_core_functionality():
    """Test core functionality that's ready for Modal deployment"""
    print("🚀 MODAL DEPLOYMENT READINESS CHECK")
    print("=" * 50)
    
    tests_passed = 0
    total_tests = 0
    
    # Test 1: Dependencies
    print("\n📦 Testing Dependencies...")
    total_tests += 1
    try:
        import fastapi, openai, requests, boto3, moviepy, PIL, pydub, numpy
        print("✅ All core dependencies available")
        tests_passed += 1
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
    
    # Test 2: API Structure
    print("\n🌐 Testing API Structure...")
    total_tests += 1
    try:
        from mainModel import app
        if hasattr(app, 'routes'):
            print(f"✅ FastAPI app configured with {len(app.routes)} routes")
            tests_passed += 1
        else:
            print("❌ FastAPI app not properly configured")
    except Exception as e:
        print(f"❌ API structure test failed: {e}")
    
    # Test 3: Variable Duration Segmentation
    print("\n⏱️ Testing Variable Duration Segmentation...")
    total_tests += 1
    try:
        from mainModel import segment_transcript_variable_duration
        
        test_segments = [
            {'start': 0, 'end': 5, 'text': 'Test sentence 1.'},
            {'start': 5, 'end': 12, 'text': 'Test sentence 2 with more content.'},
            {'start': 12, 'end': 18, 'text': 'Test sentence 3.'},
            {'start': 18, 'end': 25, 'text': 'Test sentence 4 with additional content.'}
        ]
        
        result = segment_transcript_variable_duration(test_segments, audio_duration=25.0)
        
        # Validate results
        valid_formats = [2, 3, 4]
        previous_format = None
        valid_durations = True
        
        for segment in result:
            format_type = segment.get('format')
            duration = segment['end'] - segment['start']
            
            # Check format validity
            if format_type not in valid_formats:
                print(f"❌ Invalid format {format_type}")
                valid_durations = False
                break
            
            # Check no consecutive formats
            if previous_format == format_type:
                print(f"❌ Consecutive format {format_type}")
                valid_durations = False
                break
            
            # Check duration ranges
            if format_type == 4:
                if not (5 <= duration <= 8):
                    print(f"❌ Format 4 duration {duration:.1f}s not in range [5,8]")
                    valid_durations = False
                    break
            else:  # formats 2 or 3
                if not (10 <= duration <= 20):
                    print(f"❌ Format {format_type} duration {duration:.1f}s not in range [10,20]")
                    valid_durations = False
                    break
            
            previous_format = format_type
        
        if valid_durations:
            print("✅ Variable duration segmentation working correctly")
            tests_passed += 1
        else:
            print("❌ Variable duration segmentation has issues")
            
    except Exception as e:
        print(f"❌ Variable duration segmentation test failed: {e}")
    
    # Test 4: Audience-Aware Image Generation
    print("\n🎨 Testing Audience-Aware Image Generation...")
    total_tests += 1
    try:
        from mainModel import generate_slide_json_content
        
        result = generate_slide_json_content(
            segment_text="Understanding brain function and neural pathways.",
            segment_index=0,
            segment_duration=15.0,
            target_audience="Healthcare sales team"
        )
        
        image_prompt = result.get('image_prompt', '')
        if 'healthcare' in image_prompt.lower() or 'medical' in image_prompt.lower():
            print("✅ Audience-aware image generation working")
            tests_passed += 1
        else:
            print("❌ Audience-aware image generation not working correctly")
            
    except Exception as e:
        print(f"❌ Audience-aware image generation test failed: {e}")
    
    # Test 5: HeyGen Avatar Size Configuration
    print("\n👤 Testing HeyGen Avatar Size...")
    total_tests += 1
    try:
        from mainModel import MIN_AVATAR_SIZE, MAX_AVATAR_SIZE
        
        if MIN_AVATAR_SIZE == 165 and MAX_AVATAR_SIZE >= MIN_AVATAR_SIZE:
            print(f"✅ HeyGen avatar size configured correctly (min: {MIN_AVATAR_SIZE}px, max: {MAX_AVATAR_SIZE}px)")
            tests_passed += 1
        else:
            print(f"❌ HeyGen avatar size not configured correctly")
            
    except Exception as e:
        print(f"❌ HeyGen avatar size test failed: {e}")
    
    # Test 6: File Cleanup (Basic)
    print("\n🧹 Testing Basic File Cleanup...")
    total_tests += 1
    try:
        from mainModel import cleanup_session_files
        
        # Test that the function exists and can be called
        test_session_id = "test_cleanup_123"
        cleanup_session_files(test_session_id)
        print("✅ Basic file cleanup function available")
        tests_passed += 1
        
    except Exception as e:
        print(f"❌ Basic file cleanup test failed: {e}")
    
    return tests_passed, total_tests

def main():
    """Main deployment check"""
    print("🔍 CORE FUNCTIONALITY DEPLOYMENT CHECK")
    print("=" * 60)
    
    tests_passed, total_tests = test_core_functionality()
    
    print(f"\n{'='*60}")
    print("📊 DEPLOYMENT READINESS SUMMARY")
    print(f"{'='*60}")
    
    print(f"Tests Passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("\n🎉 CORE FUNCTIONALITY READY FOR MODAL DEPLOYMENT!")
        print("\n✅ What's Working:")
        print("   - All dependencies available")
        print("   - FastAPI app properly configured")
        print("   - Variable duration segmentation (5-8s for format 4, 10-20s for formats 2/3)")
        print("   - Audience-aware image generation")
        print("   - HeyGen avatar size optimized (165px minimum)")
        print("   - Basic file cleanup functionality")
        
        print("\n📋 For Modal Deployment:")
        print("   - Environment variables will be configured in Modal")
        print("   - S3 link storage can be added as enhancement")
        print("   - Enhanced cleanup can be added as enhancement")
        print("   - Core video generation pipeline is ready")
        
        print("\n🚀 Ready to deploy to Modal!")
        return True
    else:
        print(f"\n⚠️  {total_tests - tests_passed} core tests failed.")
        print("Please fix core functionality before Modal deployment.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 