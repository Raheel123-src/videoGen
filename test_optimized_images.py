#!/usr/bin/env python3

import os
import json
import subprocess
import sys

def test_optimized_image_generation():
    """Test the optimized image generation script"""
    
    print("🧪 Testing optimized image generation...")
    
    # Check if required files exist
    if not os.path.exists('segments/slides.json'):
        print("❌ Error: segments/slides.json not found")
        print("Please run audio processing first to generate slides.json")
        return False
    
    # Check if .env file exists with API key
    if not os.path.exists('.env'):
        print("❌ Error: .env file not found")
        print("Please create .env file with your IDEOGRAM_API_KEY")
        return False
    
    # Load slides to see how many images need to be generated
    try:
        with open('segments/slides.json', 'r', encoding='utf-8') as f:
            slides = json.load(f)
        
        slides_with_images = [slide for slide in slides if slide.get('image_prompt')]
        print(f"📊 Found {len(slides_with_images)} slides that need images")
        
        if len(slides_with_images) == 0:
            print("⚠️ No slides with image prompts found")
            return True
        
    except Exception as e:
        print(f"❌ Error reading slides.json: {e}")
        return False
    
    # Test the optimized script
    try:
        print("🚀 Running optimized image generation...")
        result = subprocess.run(
            ['python3', 'generate_images_ideogram_optimized.py'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print("✅ Optimized image generation test passed!")
            print("📁 Check the 'generated_images_ideogram' folder for generated images")
            return True
        else:
            print(f"❌ Optimized image generation failed with return code: {result.returncode}")
            print(f"Error output: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Test timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False

if __name__ == "__main__":
    success = test_optimized_image_generation()
    if success:
        print("\n🎉 All tests passed! Optimized image generation is working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Tests failed! Please check the errors above.")
        sys.exit(1) 