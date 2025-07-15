#!/usr/bin/env python3

import os
import json
import openai
import base64
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

def get_openai_client():
    """Get OpenAI client with proper configuration"""
    return openai

def generate_image(prompt, size, slide_number):
    """Generate image using GPT Image 1"""
    client = get_openai_client()
    
    print(f"Generating image for slide {slide_number}...")
    print(f"Prompt: {prompt}")
    print(f"Size: {size}")
    
    try:
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            n=1
        )
        
        # Get the base64 image data
        image_base64 = response.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)
        
        print(f"Image generated successfully for slide {slide_number}")
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
    # Load slides.json
    with open('segments/slides.json', 'r', encoding='utf-8') as f:
        slides = json.load(f)
    
    # Create images directory if it doesn't exist
    os.makedirs('generated_images', exist_ok=True)
    
    # Process each slide
    for slide in slides:
        slide_number = slide['slide_number']
        format_type = slide['format']
        image_prompt = slide.get('image_prompt')
        
        # Skip slides without image prompts (format 1 and 5)
        if not image_prompt:
            print(f"Skipping slide {slide_number} (format {format_type}) - no image prompt")
            continue
        
        # Determine image size based on format
        if format_type in [2, 3]:
            size = "1024x1024"  # Square for formats 2 and 3
        elif format_type == 4:
            size = "1792x1024"  # Landscape for format 4 (closest to 1920x1080 that DALL-E supports)
        else:
            print(f"Skipping slide {slide_number} (format {format_type}) - no image needed")
            continue
        
        # Generate filename
        filename = f"generated_images/slide_{slide_number}_format_{format_type}.png"
        
        # Generate image
        image_bytes = generate_image(image_prompt, size, slide_number)
        
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
    print("Check the 'generated_images' folder for all generated images.")

if __name__ == "__main__":
    main() 