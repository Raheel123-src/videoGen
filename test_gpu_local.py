#!/usr/bin/env python3
"""
Test GPU Video Generation
"""

import os
import time
from moviepy.editor import ColorClip, AudioFileClip

def test_gpu_encoding():
    """Test GPU encoding with a simple video"""
    print("🧪 Testing GPU video encoding...")
    
    # Set GPU environment
    os.environ['MOVIEPY_USE_GPU'] = '1'
    os.environ['FFMPEG_GPU'] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    
    # Create a simple test video
    clip = ColorClip(size=(1920, 1080), color=(255, 0, 0), duration=2)
    
    # GPU parameters
    gpu_params = {
        'fps': 30,
        'codec': 'h264_nvenc',
        'audio_codec': 'aac',
        'preset': 'p7',
        'threads': 8,
        'verbose': False,
        'logger': None
    }
    
    output_file = "gpu_test_output.mp4"
    
    try:
        start_time = time.time()
        clip.write_videofile(output_file, **gpu_params)
        end_time = time.time()
        
        file_size = os.path.getsize(output_file) / (1024 * 1024)  # MB
        
        print(f"✅ GPU test successful!")
        print(f"   Output file: {output_file}")
        print(f"   File size: {file_size:.2f} MB")
        print(f"   Encoding time: {end_time - start_time:.2f}s")
        
        # Clean up
        os.remove(output_file)
        
        return True
        
    except Exception as e:
        print(f"❌ GPU test failed: {e}")
        return False

if __name__ == "__main__":
    test_gpu_encoding()
