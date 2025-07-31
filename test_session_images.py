#!/usr/bin/env python3

import os
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from mainModel import generate_images_from_slides, create_session_directories, cleanup_session_files

def create_test_slides():
    """Create test slides for testing"""
    test_slides = [
        {
            "slide_number": 1,
            "format": 2,
            "title": "Test Slide 1",
            "bullets": ["First bullet", "Second bullet"],
            "image_prompt": "A beautiful sunset over mountains"
        },
        {
            "slide_number": 2,
            "format": 3,
            "title": "Test Slide 2", 
            "bullets": ["Another bullet", "More content"],
            "image_prompt": "A modern office workspace"
        }
    ]
    
    # Save to segments folder
    os.makedirs('segments', exist_ok=True)
    with open('segments/slides.json', 'w', encoding='utf-8') as f:
        json.dump(test_slides, f, indent=2)
    
    return test_slides

def test_session_image_generation(session_id):
    """Test image generation for a specific session"""
    print(f"🧪 Testing session: {session_id}")
    
    # Create session directories
    session_uploads, session_transcripts, session_segments, session_images = create_session_directories(session_id)
    
    # Copy slides.json to session-specific location
    session_slides_path = os.path.join(session_segments, 'slides.json')
    if os.path.exists('segments/slides.json'):
        import shutil
        shutil.copy('segments/slides.json', session_slides_path)
    
    try:
        # Generate images for this session
        success = generate_images_from_slides(session_slides_path, session_id)
        
        if success:
            # Check if images were created in session folder
            session_images_dir = os.path.join('generated_images_ideogram', session_id)
            if os.path.exists(session_images_dir):
                images = [f for f in os.listdir(session_images_dir) if f.endswith('.png')]
                print(f"✅ Session {session_id}: Generated {len(images)} images")
                return True, len(images)
            else:
                print(f"❌ Session {session_id}: No session images folder created")
                return False, 0
        else:
            print(f"❌ Session {session_id}: Image generation failed")
            return False, 0
            
    except Exception as e:
        print(f"❌ Session {session_id}: Exception - {e}")
        return False, 0
    finally:
        # Clean up session files
        cleanup_session_files(session_id)

def test_concurrent_sessions():
    """Test multiple concurrent sessions to ensure no conflicts"""
    print("🚀 Testing concurrent session image generation")
    print("=" * 60)
    
    # Create test slides
    create_test_slides()
    
    # Generate multiple session IDs
    session_ids = [str(uuid.uuid4())[:8] for _ in range(3)]
    
    print(f"📋 Testing {len(session_ids)} concurrent sessions:")
    for session_id in session_ids:
        print(f"   - {session_id}")
    
    # Run concurrent image generation
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_session = {
            executor.submit(test_session_image_generation, session_id): session_id 
            for session_id in session_ids
        }
        
        for future in future_to_session:
            session_id = future_to_session[future]
            try:
                success, image_count = future.result()
                results.append((session_id, success, image_count))
            except Exception as e:
                print(f"❌ Session {session_id} failed with exception: {e}")
                results.append((session_id, False, 0))
    
    # Report results
    print("\n📊 Results:")
    print("=" * 60)
    successful_sessions = 0
    total_images = 0
    
    for session_id, success, image_count in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} Session {session_id}: {image_count} images")
        if success:
            successful_sessions += 1
            total_images += image_count
    
    print(f"\n🎯 Summary:")
    print(f"   - Successful sessions: {successful_sessions}/{len(session_ids)}")
    print(f"   - Total images generated: {total_images}")
    
    # Verify no conflicts in global folder
    global_images = []
    if os.path.exists('generated_images_ideogram'):
        global_images = [f for f in os.listdir('generated_images_ideogram') 
                        if f.endswith('.png') and not os.path.isdir(os.path.join('generated_images_ideogram', f))]
    
    print(f"   - Images in global folder: {len(global_images)}")
    
    if len(global_images) == 0:
        print("✅ No conflicts detected - all images properly isolated in session folders")
    else:
        print("⚠️  Warning: Images found in global folder - potential conflicts detected")
    
    return successful_sessions == len(session_ids)

if __name__ == "__main__":
    # Check if API key is available
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv('IDEOGRAM_API_KEY'):
        print("❌ Error: IDEOGRAM_API_KEY not found in .env file")
        print("Please add your Ideogram API key to the .env file:")
        print("IDEOGRAM_API_KEY=your_api_key_here")
        exit(1)
    
    print("🧪 Session-based Image Storage Test")
    print("This test verifies that concurrent requests use separate image folders")
    print("=" * 60)
    
    success = test_concurrent_sessions()
    
    if success:
        print("\n🎉 All tests passed! Session-based image storage is working correctly.")
    else:
        print("\n❌ Some tests failed. Check the output above for details.") 