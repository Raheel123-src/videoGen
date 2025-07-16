#!/usr/bin/env python3

import os
import json
import requests
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()
IDEOGRAM_API_KEY = os.getenv('IDEOGRAM_API_KEY')

def generate_image_ideogram(prompt, aspect_ratio, slide_number):
    """Generate image using Ideogram 3.0"""
    
    print(f"Generating image for slide {slide_number}...")
    print(f"Prompt: {prompt}")
    print(f"Aspect ratio: {aspect_ratio}")
    
    try:
        response = requests.post(
            "https://api.ideogram.ai/v1/ideogram-v3/generate",
            headers={
                "Api-Key": IDEOGRAM_API_KEY
            },
            json={
                "prompt": prompt,
                "rendering_speed": "TURBO",
                "aspect_ratio": aspect_ratio
            }
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Get the image URL from the response
        image_url = result['data'][0]['url']
        print(f"Image generated successfully for slide {slide_number}")
        
        # Download the image
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        image_bytes = image_response.content
        
        return image_bytes
        
    except Exception as e:
        print(f"Error generating image for slide {slide_number}: {e}")
        return None

def save_image(image_bytes, filename):
    """Save image bytes to file"""
    try:
        with open(filename, 'wb') as f:
            f.write(image_bytes)
        
        print(f"Image saved: {filename}")
        return True
        
    except Exception as e:
        print(f"Error saving image {filename}: {e}")
        return False

def main():
    # Check if API key is available
    if not IDEOGRAM_API_KEY:
        print("Error: IDEOGRAM_API_KEY not found in .env file")
        print("Please add your Ideogram API key to the .env file:")
        print("IDEOGRAM_API_KEY=your_api_key_here")
        return
    
    # Load slides.json
    with open('segments/slides.json', 'r', encoding='utf-8') as f:
        slides = json.load(f)
    
    # Create images directory if it doesn't exist
    os.makedirs('generated_images_ideogram', exist_ok=True)
    
    # Process each slide
    for slide in slides:
        slide_number = slide['slide_number']
        format_type = slide['format']
        image_prompt = slide.get('image_prompt')
        
        # Skip slides without image prompts (format 1 and 5)
        if not image_prompt:
            print(f"Skipping slide {slide_number} (format {format_type}) - no image prompt")
            continue
        
        # Determine aspect ratio based on format
        if format_type in [2, 3]:
            aspect_ratio = "1x1"  # Square for formats 2 and 3
        elif format_type == 4:
            aspect_ratio = "16x9"  # Landscape for format 4 (closest to 1920x1080)
        else:
            print(f"Skipping slide {slide_number} (format {format_type}) - no image needed")
            continue
        
        # Generate filename
        filename = f"generated_images_ideogram/slide_{slide_number}_format_{format_type}.png"
        
        # Generate image
        image_bytes = generate_image_ideogram(image_prompt, aspect_ratio, slide_number)
        
        if image_bytes:
            # Save image directly
            success = save_image(image_bytes, filename)
            if success:
                print(f"✓ Slide {slide_number} image completed")
            else:
                print(f"✗ Slide {slide_number} image failed")
        
        # Add delay to avoid rate limiting
        time.sleep(2)
    
    print("\nImage generation complete!")
    print("Check the 'generated_images_ideogram' folder for all generated images.")

if __name__ == "__main__":
    main() 