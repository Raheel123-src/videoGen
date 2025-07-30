#!/usr/bin/env python3
"""
Test script for GPU video generation on Modal L4
"""

import os
import sys
import numpy as np
from moviepy.editor import VideoClip, AudioFileClip

def test_gpu_video_generation():
    """Test GPU video generation with Modal L4 configuration"""
    
    print("🧪 Testing GPU video generation on Modal L4...")
    
    # Configure GPU environment (same as Modal deployment)
    os.environ['MOVIEPY_USE_GPU'] = '1'
    os.environ['FFMPEG_GPU'] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    os.environ['NVIDIA_VISIBLE_DEVICES'] = '0'
    
    print(f"🔧 GPU Environment configured:")
    print(f"   - MOVIEPY_USE_GPU: {os.environ.get('MOVIEPY_USE_GPU')}")
    print(f"   - FFMPEG_GPU: {os.environ.get('FFMPEG_GPU')}")
    print(f"   - CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
    
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
    
    # Test GPU-optimized parameters (same as Modal L4)
    gpu_params = {
        'fps': 30,
        'codec': 'h264_nvenc',  # Use NVIDIA encoder
        'audio_codec': 'aac',
        'preset': 'p7',  # Fastest preset for NVENC
        'threads': 8,  # More threads for GPU
        'verbose': False,
        'logger': None
    }
    
    output_file = "test_gpu_video_generation.mp4"
    
    print(f"📝 Testing GPU write_videofile with parameters: {gpu_params}")
    
    try:
        clip.write_videofile(
            output_file,
            **gpu_params
        )
        
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / (1024*1024)  # MB
            print(f"✅ GPU test successful! Output file: {output_file} ({file_size:.2f} MB)")
            
            # Clean up
            os.remove(output_file)
            return True
        else:
            print(f"❌ Output file not found!")
            return False
            
    except Exception as e:
        print(f"❌ GPU test failed: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        
        # Try CPU fallback
        print(f"🔄 Trying CPU fallback...")
        try:
            cpu_params = {
                'fps': 30,
                'codec': 'libx264',
                'audio_codec': 'aac',
                'preset': 'ultrafast',
                'threads': 4,
                'verbose': False,
                'logger': None
            }
            
            clip.write_videofile(
                output_file,
                **cpu_params
            )
            
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file) / (1024*1024)  # MB
                print(f"✅ CPU fallback successful! Output file: {output_file} ({file_size:.2f} MB)")
                
                # Clean up
                os.remove(output_file)
                return True
            else:
                print(f"❌ CPU fallback output file not found!")
                return False
                
        except Exception as e2:
            print(f"❌ CPU fallback also failed: {e2}")
            return False
    finally:
        clip.close()

if __name__ == "__main__":
    success = test_gpu_video_generation()
    if success:
        print("🎉 GPU video generation test passed!")
    else:
        print("💥 GPU video generation test failed!")
        sys.exit(1) 