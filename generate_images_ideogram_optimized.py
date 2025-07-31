#!/usr/bin/env python3

import os
import json
import requests
from dotenv import load_dotenv
import time
import concurrent.futures
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()
IDEOGRAM_API_KEY = os.getenv('IDEOGRAM_API_KEY')

# Global counter for progress tracking
completed_images = 0
total_images = 0
lock = threading.Lock()

def generate_image_ideogram_optimized(prompt, aspect_ratio, slide_number):
    """Generate image using Ideogram 3.0 with optimized settings"""
    
    print(f"🎨 Generating image for slide {slide_number}...")
    
    try:
        # Optimized API call with faster settings
        response = requests.post(
            "https://api.ideogram.ai/v1/ideogram-v3/generate",
            headers={
                "Api-Key": IDEOGRAM_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "prompt": prompt,
                "rendering_speed": "TURBO",  # Fastest rendering
                "aspect_ratio": aspect_ratio,
                "quality": "standard"  # Faster than high quality
            },
            timeout=30  # Reduced timeout for faster failure detection
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Get the image URL from the response
        image_url = result['data'][0]['url']
        print(f"✅ Image generated for slide {slide_number}")
        
        # Download the image with optimized settings
        image_response = requests.get(
            image_url, 
            timeout=15,  # Faster timeout
            stream=True  # Stream for better memory management
        )
        image_response.raise_for_status()
        image_bytes = image_response.content
        
        return image_bytes, slide_number
        
    except Exception as e:
        print(f"❌ Error generating image for slide {slide_number}: {e}")
        return None, slide_number

def save_image_optimized(image_data, slide_info, session_id=None):
    """Save image bytes to file with progress tracking"""
    image_bytes, slide_number = image_data
    if image_bytes is None:
        return False, slide_number
    
    try:
        # Get format type from slide info
        format_type = slide_info.get('format', 2)
        
        # Create session-specific folder structure
        if session_id:
            session_images_dir = os.path.join('generated_images_ideogram', session_id)
            os.makedirs(session_images_dir, exist_ok=True)
            filename = os.path.join(session_images_dir, f'slide_{slide_number}_format_{format_type}.png')
        else:
            # Fallback to original behavior for backward compatibility
            filename = f"generated_images_ideogram/slide_{slide_number}_format_{format_type}.png"
        
        with open(filename, 'wb') as f:
            f.write(image_bytes)
        
        # Update progress
        global completed_images
        with lock:
            completed_images += 1
            progress = (completed_images / total_images) * 100
            print(f"💾 Saved: {filename} ({completed_images}/{total_images} - {progress:.1f}%)")
        
        return True, slide_number
        
    except Exception as e:
        print(f"❌ Error saving image for slide {slide_number}: {e}")
        return False, slide_number

def process_slide_parallel(slide, session_id=None):
    """Process a single slide with image generation"""
    slide_number = slide['slide_number']
    format_type = slide['format']
    image_prompt = slide.get('image_prompt')
    
    # Skip slides without image prompts
    if not image_prompt:
        print(f"⏭️ Skipping slide {slide_number} (format {format_type}) - no image prompt")
        return None
    
    # Determine aspect ratio based on format
    if format_type in [2, 3]:
        aspect_ratio = "1x1"  # Square for formats 2 and 3
    elif format_type == 4:
        aspect_ratio = "16x9"  # Landscape for format 4
    else:
        print(f"⏭️ Skipping slide {slide_number} (format {format_type}) - no image needed")
        return None
    
    # Generate image
    image_data = generate_image_ideogram_optimized(image_prompt, aspect_ratio, slide_number)
    
    if image_data[0]:
        # Save image with session_id
        success, _ = save_image_optimized(image_data, slide, session_id)
        if success:
            print(f"✅ Slide {slide_number} completed")
        else:
            print(f"❌ Slide {slide_number} failed")
        return success
    else:
        print(f"❌ Slide {slide_number} failed")
        return False

def main(session_id=None):
    # Check if API key is available
    if not IDEOGRAM_API_KEY:
        print("❌ Error: IDEOGRAM_API_KEY not found in .env file")
        print("Please add your Ideogram API key to the .env file:")
        print("IDEOGRAM_API_KEY=your_api_key_here")
        return
    
    # Load slides.json
    try:
        with open('segments/slides.json', 'r', encoding='utf-8') as f:
            slides = json.load(f)
    except FileNotFoundError:
        print("❌ Error: segments/slides.json not found")
        return
    
    # Create images directory if it doesn't exist
    os.makedirs('generated_images_ideogram', exist_ok=True)
    
    # Filter slides that need images
    slides_with_images = [slide for slide in slides if slide.get('image_prompt')]
    global total_images
    total_images = len(slides_with_images)
    
    print(f"🚀 Starting optimized image generation for {total_images} slides")
    print(f"⚡ Using parallel processing for faster generation")
    if session_id:
        print(f"📁 Session ID: {session_id}")
    print("=" * 60)
    
    # Use ThreadPoolExecutor for parallel processing
    # Limit to 4 concurrent requests to avoid overwhelming the API
    max_workers = min(4, total_images)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks with session_id
        future_to_slide = {
            executor.submit(process_slide_parallel, slide, session_id): slide 
            for slide in slides_with_images
        }
        
        # Process completed tasks
        for future in as_completed(future_to_slide):
            slide = future_to_slide[future]
            try:
                result = future.result()
                if result:
                    print(f"✅ Completed: Slide {slide['slide_number']}")
                else:
                    print(f"❌ Failed: Slide {slide['slide_number']}")
            except Exception as e:
                print(f"❌ Exception for slide {slide['slide_number']}: {e}")
    
    print(f"\n🎉 Image generation complete!")
    if session_id:
        print(f"📁 Check the 'generated_images_ideogram/{session_id}' folder for all generated images.")
    else:
        print(f"📁 Check the 'generated_images_ideogram' folder for all generated images.")

if __name__ == "__main__":
    main() 