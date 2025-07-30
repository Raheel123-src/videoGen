#!/usr/bin/env python3
"""
Test script to verify write_videofile fix
"""

import os
import sys
import numpy as np
from moviepy.editor import VideoClip, AudioFileClip

def test_write_videofile():
    """Test write_videofile with the same parameters used in video generation"""
    
    print("🧪 Testing write_videofile fix...")
    
    # Disable GPU acceleration
    os.environ['MOVIEPY_USE_GPU'] = '0'
    os.environ['FFMPEG_GPU'] = '0'
    
    # Create a simple test video clip
    def make_frame(t):
        # Create a simple colored frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Add some color based on time
        frame[:, :, 0] = int(255 * (t % 2))  # Red channel
        frame[:, :, 1] = int(255 * ((t + 0.5) % 2))  # Green channel
        frame[:, :, 2] = int(255 * ((t + 1) % 2))  # Blue channel
        return frame
    
    # Create a 3-second video clip
    clip = VideoClip(make_frame, duration=3)
    
    # Test the same parameters used in video generation
    write_params = {
        'fps': 30,
        'codec': 'libx264',
        'audio_codec': 'aac',
        'preset': 'ultrafast',
        'threads': 4,
        'verbose': False,
        'logger': None
    }
    
    output_file = "test_write_videofile_fix.mp4"
    
    print(f"📝 Testing write_videofile with parameters: {write_params}")
    
    try:
        clip.write_videofile(
            output_file,
            **write_params
        )
        
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / (1024*1024)  # MB
            print(f"✅ Test successful! Output file: {output_file} ({file_size:.2f} MB)")
            
            # Clean up
            os.remove(output_file)
            return True
        else:
            print(f"❌ Output file not found!")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        return False
    finally:
        clip.close()

if __name__ == "__main__":
    success = test_write_videofile()
    if success:
        print("🎉 write_videofile fix test passed!")
    else:
        print("💥 write_videofile fix test failed!")
        sys.exit(1) 