#!/usr/bin/env python3
"""
GPU and Encoder Checker
Checks GPU availability and video encoding capabilities
"""

import os
import subprocess
import sys
import platform

def check_gpu_availability():
    """Check if GPU is available and what type"""
    print("🔍 Checking GPU Availability...")
    print("=" * 50)
    
    # Check CUDA environment variables
    cuda_visible = os.environ.get('CUDA_VISIBLE_DEVICES')
    nvidia_visible = os.environ.get('NVIDIA_VISIBLE_DEVICES')
    moviepy_gpu = os.environ.get('MOVIEPY_USE_GPU')
    ffmpeg_gpu = os.environ.get('FFMPEG_GPU')
    
    print(f"CUDA_VISIBLE_DEVICES: {cuda_visible}")
    print(f"NVIDIA_VISIBLE_DEVICES: {nvidia_visible}")
    print(f"MOVIEPY_USE_GPU: {moviepy_gpu}")
    print(f"FFMPEG_GPU: {ffmpeg_gpu}")
    
    # Check if we're in a GPU environment
    gpu_available = cuda_visible is not None or nvidia_visible is not None
    print(f"\nGPU Environment Detected: {gpu_available}")
    
    return gpu_available

def check_ffmpeg_encoders():
    """Check available FFmpeg encoders"""
    print("\n🔍 Checking FFmpeg Encoders...")
    print("=" * 50)
    
    try:
        # Get all available encoders
        result = subprocess.run(['ffmpeg', '-encoders'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            encoders = result.stdout
            
            # Check for GPU encoders
            gpu_encoders = []
            cpu_encoders = []
            
            for line in encoders.split('\n'):
                if 'h264' in line.lower():
                    if 'nvenc' in line.lower() or 'qsv' in line.lower() or 'amf' in line.lower():
                        gpu_encoders.append(line.strip())
                    else:
                        cpu_encoders.append(line.strip())
            
            print("🎯 GPU Video Encoders:")
            if gpu_encoders:
                for encoder in gpu_encoders:
                    print(f"  ✅ {encoder}")
            else:
                print("  ❌ No GPU encoders found")
            
            print("\n💻 CPU Video Encoders:")
            if cpu_encoders:
                for encoder in cpu_encoders[:5]:  # Show first 5
                    print(f"  ✅ {encoder}")
                if len(cpu_encoders) > 5:
                    print(f"  ... and {len(cpu_encoders) - 5} more")
            else:
                print("  ❌ No CPU encoders found")
                
        else:
            print(f"❌ FFmpeg not available or error: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ FFmpeg not found in system PATH")
    except subprocess.TimeoutExpired:
        print("❌ FFmpeg command timed out")
    except Exception as e:
        print(f"❌ Error checking FFmpeg encoders: {e}")

def check_moviepy_gpu():
    """Check MoviePy GPU capabilities"""
    print("\n🔍 Checking MoviePy GPU Support...")
    print("=" * 50)
    
    try:
        import moviepy
        print(f"MoviePy Version: {moviepy.__version__}")
        
        # Check if MoviePy can detect GPU
        from moviepy.config import get_setting
        ffmpeg_binary = get_setting("FFMPEG_BINARY")
        print(f"FFmpeg Binary: {ffmpeg_binary}")
        
        # Try to get MoviePy's GPU detection
        try:
            from moviepy.video.io.ffmpeg_writer import FFMPEG_BINARY
            print(f"MoviePy FFmpeg: {FFMPEG_BINARY}")
        except:
            print("Could not get MoviePy FFmpeg binary")
            
    except ImportError:
        print("❌ MoviePy not installed")
    except Exception as e:
        print(f"❌ Error checking MoviePy: {e}")

def check_system_info():
    """Check system information"""
    print("\n🔍 System Information...")
    print("=" * 50)
    
    print(f"Platform: {platform.platform()}")
    print(f"Python Version: {sys.version}")
    print(f"Architecture: {platform.architecture()}")
    
    # Check for NVIDIA GPU
    try:
        result = subprocess.run(['nvidia-smi'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("\n🎯 NVIDIA GPU Information:")
            print(result.stdout)
        else:
            print("❌ nvidia-smi not available or no NVIDIA GPU")
    except:
        print("❌ nvidia-smi not found")

def test_gpu_encoding():
    """Test GPU encoding capabilities"""
    print("\n🔍 Testing GPU Encoding...")
    print("=" * 50)
    
    # Test different encoder configurations
    encoders_to_test = [
        ('h264_nvenc', 'GPU NVIDIA'),
        ('h264_qsv', 'GPU Intel'),
        ('h264_amf', 'GPU AMD'),
        ('libx264', 'CPU'),
        ('libx265', 'CPU HEVC')
    ]
    
    for encoder, description in encoders_to_test:
        try:
            # Test if encoder is available
            result = subprocess.run([
                'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=320x240:rate=1',
                '-c:v', encoder, '-t', '1', '-f', 'null', '-'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"✅ {description} ({encoder}): Available")
            else:
                print(f"❌ {description} ({encoder}): Not available")
                
        except subprocess.TimeoutExpired:
            print(f"⏰ {description} ({encoder}): Timeout")
        except Exception as e:
            print(f"❌ {description} ({encoder}): Error - {e}")

def check_modal_environment():
    """Check if running in Modal environment"""
    print("\n🔍 Modal Environment Check...")
    print("=" * 50)
    
    modal_vars = {k: v for k, v in os.environ.items() if 'MODAL' in k.upper()}
    if modal_vars:
        print("✅ Running in Modal environment:")
        for k, v in modal_vars.items():
            print(f"  {k}: {v}")
    else:
        print("❌ Not running in Modal environment")
    
    # Check for GPU in Modal
    if os.environ.get('CUDA_VISIBLE_DEVICES') or os.environ.get('GPU'):
        print("✅ GPU detected in Modal environment")
    else:
        print("❌ No GPU detected in Modal environment")

def main():
    """Main function to run all checks"""
    print("🚀 GPU and Encoder Checker")
    print("=" * 60)
    
    # Run all checks
    check_gpu_availability()
    check_ffmpeg_encoders()
    check_moviepy_gpu()
    check_system_info()
    test_gpu_encoding()
    check_modal_environment()
    
    print("\n" + "=" * 60)
    print("✅ GPU and Encoder Check Complete!")
    
    # Summary
    print("\n📊 Summary:")
    gpu_available = check_gpu_availability()
    if gpu_available:
        print("🎯 GPU is available - you can enable GPU encoding")
        print("💡 To enable GPU in your code:")
        print("   1. Remove GPU disable lines in modal_app.py")
        print("   2. Change gpu_available = False to True in video_generator.py")
        print("   3. Use h264_nvenc codec for GPU encoding")
    else:
        print("❌ GPU not available - will use CPU encoding")
        print("💡 CPU encoding is still reliable but slower")

if __name__ == "__main__":
    main() 