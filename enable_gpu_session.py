#!/usr/bin/env python3
"""
Enable GPU for Current Session
Sets environment variables for GPU acceleration
"""

import os

def enable_gpu():
    """Enable GPU environment variables"""
    print("🔧 Enabling GPU environment variables...")
    
    # Set GPU environment variables
    os.environ['MOVIEPY_USE_GPU'] = '1'
    os.environ['FFMPEG_GPU'] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    os.environ['NVIDIA_VISIBLE_DEVICES'] = '0'
    
    print("✅ GPU environment variables set:")
    print(f"   MOVIEPY_USE_GPU: {os.environ.get('MOVIEPY_USE_GPU')}")
    print(f"   FFMPEG_GPU: {os.environ.get('FFMPEG_GPU')}")
    print(f"   CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
    print(f"   NVIDIA_VISIBLE_DEVICES: {os.environ.get('NVIDIA_VISIBLE_DEVICES')}")
    
    print("\n💡 Now you can run your video generation with GPU acceleration!")
    print("   The environment variables are set for this Python session.")

if __name__ == "__main__":
    enable_gpu() 