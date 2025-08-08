import os
import json
import shutil
from PIL import Image, ImageDraw, ImageFont
import re
import math
from datetime import timedelta
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, TextClip, concatenate_videoclips, VideoClip
from moviepy.video.fx.all import resize
import numpy as np
import random
from glob import glob
import sys
import time
import json
import psutil
import subprocess
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip, ImageClip
from moviepy.video.fx import resize
import numpy as np
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# GPU-accelerated image processing
try:
    import cv2
    import cv2.cuda as cuda
    GPU_IMAGE_PROCESSING = True
    print("[GPU] OpenCV CUDA support detected - enabling GPU image processing")
except ImportError:
    GPU_IMAGE_PROCESSING = False
    print("[GPU] OpenCV CUDA not available - using CPU image processing")

# Fix PIL ANTIALIAS compatibility issue
try:
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS
except:
    pass

def detect_available_encoders():
    """Detect available GPU and CPU encoders"""
    try:
        # Get all available encoders
        result = subprocess.run(['ffmpeg', '-encoders'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            encoders = result.stdout
            
            # Check for GPU encoders in order of preference
            gpu_encoders = []
            if 'h264_nvenc' in encoders:
                gpu_encoders.append(('h264_nvenc', 'NVIDIA GPU'))
            if 'h264_qsv' in encoders:
                gpu_encoders.append(('h264_qsv', 'Intel GPU'))
            if 'h264_amf' in encoders:
                gpu_encoders.append(('h264_amf', 'AMD GPU'))
            
            # Check for CPU encoders
            cpu_encoders = []
            if 'libx264' in encoders:
                cpu_encoders.append(('libx264', 'CPU'))
            if 'libx265' in encoders:
                cpu_encoders.append(('libx265', 'CPU HEVC'))
            
            return gpu_encoders, cpu_encoders
        else:
            print_flush(f"[ENCODER DETECT] FFmpeg error: {result.stderr}")
            return [], []
            
    except Exception as e:
        print_flush(f"[ENCODER DETECT] Error detecting encoders: {e}")
        return [], []

def check_gpu_performance():
    """Check GPU performance and memory usage"""
    try:
        import subprocess
        import os
        
        # Check NVIDIA GPU stats
        if os.environ.get('CUDA_VISIBLE_DEVICES') is not None:
            try:
                result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu', '--format=csv,noheader,nounits'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    gpu_stats = result.stdout.strip().split(', ')
                    if len(gpu_stats) >= 3:
                        memory_used = int(gpu_stats[0])
                        memory_total = int(gpu_stats[1])
                        gpu_utilization = int(gpu_stats[2])
                        memory_percent = (memory_used / memory_total) * 100
                        
                        print_flush(f"[GPU MONITOR] GPU Memory: {memory_used}MB/{memory_total}MB ({memory_percent:.1f}%)")
                        print_flush(f"[GPU MONITOR] GPU Utilization: {gpu_utilization}%")
                        
                        return {
                            'memory_used_mb': memory_used,
                            'memory_total_mb': memory_total,
                            'memory_percent': memory_percent,
                            'gpu_utilization': gpu_utilization
                        }
            except:
                pass
        
        return None
    except Exception as e:
        print_flush(f"[GPU MONITOR] Error checking GPU: {e}")
        return None

def try_ffmpeg_gpu_fix():
    """Try to fix GPU encoder issues in Modal environment"""
    try:
        import subprocess
        import os
        
        # Check if we're in Modal environment
        is_modal = os.environ.get('MODAL_ENVIRONMENT') or os.environ.get('MODAL_APP_NAME')
        if not is_modal:
            return False
            
        print_flush("[GPU FIX] Attempting to fix GPU encoder issues...")
        
        # Try to install NVIDIA codecs
        try:
            subprocess.run(['apt-get', 'update'], capture_output=True, timeout=10)
            subprocess.run(['apt-get', 'install', '-y', 'nvidia-cuda-toolkit'], capture_output=True, timeout=30)
            print_flush("[GPU FIX] NVIDIA CUDA toolkit installed")
        except:
            pass
            
        # Try to install Intel QSV support
        try:
            subprocess.run(['apt-get', 'install', '-y', 'intel-media-va-driver-non-free'], capture_output=True, timeout=30)
            print_flush("[GPU FIX] Intel QSV drivers installed")
        except:
            pass
            
        # Set environment variables for GPU encoding
        os.environ['CUDA_VISIBLE_DEVICES'] = '0'
        os.environ['NVIDIA_VISIBLE_DEVICES'] = '0'
        os.environ['FFMPEG_GPU'] = '1'
        
        return True
    except Exception as e:
        print_flush(f"[GPU FIX] Error during GPU fix attempt: {e}")
        return False

def test_moviepy_ffmpeg():
    """Test which FFmpeg MoviePy is actually using"""
    try:
        from moviepy.config import get_setting
        moviepy_ffmpeg = get_setting("FFMPEG_BINARY")
        print_flush(f"[FFMPEG TEST] MoviePy FFmpeg path: {moviepy_ffmpeg}")
        
        # Test if this FFmpeg has GPU encoders
        import subprocess
        result = subprocess.run([moviepy_ffmpeg, '-encoders'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            encoders = result.stdout
            if 'h264_nvenc' in encoders:
                print_flush("[FFMPEG TEST] ✅ MoviePy FFmpeg has h264_nvenc")
            else:
                print_flush("[FFMPEG TEST] ❌ MoviePy FFmpeg missing h264_nvenc")
            
            if 'h264_qsv' in encoders:
                print_flush("[FFMPEG TEST] ✅ MoviePy FFmpeg has h264_qsv")
            else:
                print_flush("[FFMPEG TEST] ❌ MoviePy FFmpeg missing h264_qsv")
        else:
            print_flush(f"[FFMPEG TEST] ❌ MoviePy FFmpeg error: {result.stderr}")
            
        return moviepy_ffmpeg
    except Exception as e:
        print_flush(f"[FFMPEG TEST] Error testing MoviePy FFmpeg: {e}")
        return None

def get_best_encoder():
    """Get the best available encoder with MAXIMUM performance while maintaining quality"""
    import os
    gpu_encoders, cpu_encoders = detect_available_encoders()
    
    print_flush(f"[ENCODER DETECT] Available GPU encoders: {gpu_encoders}")
    print_flush(f"[ENCODER DETECT] Available CPU encoders: {cpu_encoders}")
    
    # For Modal environment, be more conservative and default to CPU unless GPU is proven to work
    # This avoids the issue where GPU encoders appear available but don't work with MoviePy
    
    # Check if we're in a Modal environment (has GPU but might have restrictions)
    import os
    is_modal_environment = os.environ.get('MODAL_ENVIRONMENT') or os.environ.get('MODAL_APP_NAME')
    
    if is_modal_environment:
        print_flush("[ENCODER DETECT] Modal environment detected - attempting GPU fixes")
        # Try to fix GPU encoder issues
        try_ffmpeg_gpu_fix()
        
        # Test which FFmpeg MoviePy is actually using
        moviepy_ffmpeg_path = test_moviepy_ffmpeg()
    
    # Test GPU encoders to see which ones actually work
    working_gpu_encoders = []
    
    # Prioritize NVIDIA NVENC for maximum performance
    prioritized_encoders = []
    for encoder_name, description in gpu_encoders:
        if 'nvenc' in encoder_name:
            prioritized_encoders.insert(0, (encoder_name, description))
        else:
            prioritized_encoders.append((encoder_name, description))
    
    for encoder_name, description in prioritized_encoders:
        try:
            # Test if the encoder actually works by trying a simple FFmpeg command
            import subprocess
            
            # Use fastest preset for each encoder
            if 'nvenc' in encoder_name:
                presets_to_try = ['p1']  # Only try fastest preset
            elif 'qsv' in encoder_name:
                presets_to_try = ['veryfast']  # Only try fastest preset
            elif 'amf' in encoder_name:
                presets_to_try = ['speed']  # Only try fastest preset
            else:
                presets_to_try = ['ultrafast']  # Only try fastest preset
            
            encoder_works = False
            working_preset = None
            
            # Use the same FFmpeg that MoviePy uses if available
            ffmpeg_binary = 'ffmpeg'
            if is_modal_environment and moviepy_ffmpeg_path:
                ffmpeg_binary = moviepy_ffmpeg_path
                print_flush(f"[ENCODER TEST] Using MoviePy FFmpeg: {ffmpeg_binary}")
            
            for preset in presets_to_try:
                # Use Windows-compatible temporary path
                import tempfile
                temp_dir = tempfile.gettempdir()
                test_output = os.path.join(temp_dir, 'test_output.mp4')
                
                test_cmd = [ffmpeg_binary, '-f', 'lavfi', '-i', 'testsrc=duration=1:size=320x240:rate=1', 
                           '-c:v', encoder_name, '-preset', preset, '-y', test_output]
                
                result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)  # Reduced timeout
                if result.returncode == 0:
                    # Quick test: try to encode with MoviePy-like parameters
                    moviepy_test_output = os.path.join(temp_dir, 'moviepy_test.mp4')
                    moviepy_test_cmd = [ffmpeg_binary, '-f', 'lavfi', '-i', 'testsrc=duration=1:size=320x240:rate=1', 
                                       '-c:v', encoder_name, '-preset', preset, '-f', 'mp4', '-y', moviepy_test_output]
                    
                    moviepy_result = subprocess.run(moviepy_test_cmd, capture_output=True, text=True, timeout=5)  # Reduced timeout
                    if moviepy_result.returncode == 0:
                        encoder_works = True
                        working_preset = preset
                        print_flush(f"[ENCODER TEST] ✅ {encoder_name} works with preset '{preset}' (MoviePy compatible)!")
                        break
                    else:
                        print_flush(f"[ENCODER TEST] ⚠️ {encoder_name} works with preset '{preset}' but MoviePy test failed")
                else:
                    print_flush(f"[ENCODER TEST] ❌ {encoder_name} failed with preset '{preset}'")
            
            if encoder_works:
                working_gpu_encoders.append((encoder_name, description, working_preset))
                # If we found a working encoder, we can stop testing
                break
                
        except Exception as e:
            print_flush(f"[ENCODER TEST] ❌ {encoder_name} error: {e}")
    
    if not working_gpu_encoders:
        print_flush("[ENCODER TEST] No working GPU encoders found, will use CPU fallback")
    
    # Use working GPU encoders first (only if they pass MoviePy compatibility test)
    if working_gpu_encoders:
        # Double-check that we have at least one encoder that passed the MoviePy test
        moviepy_compatible_encoders = [enc for enc in working_gpu_encoders if len(enc) == 3]
        if not moviepy_compatible_encoders:
            print_flush("[ENCODER TEST] No MoviePy-compatible GPU encoders found, trying alternative approaches")
            
            # Try alternative FFmpeg configurations for GPU encoders
            for encoder_name, description in gpu_encoders:
                try:
                    # Use the same FFmpeg that MoviePy uses if available
                    ffmpeg_binary = 'ffmpeg'
                    if is_modal_environment and moviepy_ffmpeg_path:
                        ffmpeg_binary = moviepy_ffmpeg_path
                    
                    # Try with different FFmpeg configurations
                    alt_configs = [
                        [ffmpeg_binary, '-f', 'lavfi', '-i', 'testsrc=duration=1:size=320x240:rate=1', 
                         '-c:v', encoder_name, '-preset', 'fast', '-y', os.path.join(temp_dir, 'alt1.mp4')],
                        [ffmpeg_binary, '-f', 'lavfi', '-i', 'testsrc=duration=1:size=320x240:rate=1', 
                         '-c:v', encoder_name, '-y', os.path.join(temp_dir, 'alt2.mp4')],
                        [ffmpeg_binary, '-f', 'lavfi', '-i', 'testsrc=duration=1:size=320x240:rate=1', 
                         '-c:v', encoder_name, '-preset', 'ultrafast', '-y', os.path.join(temp_dir, 'alt3.mp4')]
                    ]
                    
                    for i, config in enumerate(alt_configs):
                        result = subprocess.run(config, capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            working_gpu_encoders.append((encoder_name, description, 'fast'))
                            print_flush(f"[ENCODER TEST] ✅ {encoder_name} works with alternative config {i+1}!")
                            break
                except:
                    pass
    
    # For Modal environments, try aggressive GPU fixes instead of defaulting to CPU
    if is_modal_environment and not working_gpu_encoders:
        print_flush("[ENCODER DETECT] Modal environment detected - trying aggressive GPU fixes")
        
        # Try to force enable GPU encoders
        try:
            import subprocess
            # Force install GPU support
            subprocess.run(['apt-get', 'update'], capture_output=True, timeout=10)
            subprocess.run(['apt-get', 'install', '-y', 'nvidia-cuda-toolkit', 'nvidia-cuda-dev'], capture_output=True, timeout=30)
            
            # Try to re-detect encoders after installation
            gpu_encoders_after_install, _ = detect_available_encoders()
            if gpu_encoders_after_install:
                print_flush(f"[ENCODER DETECT] Found encoders after installation: {gpu_encoders_after_install}")
                # Add them to working encoders with basic preset
                for encoder_name, description in gpu_encoders_after_install:
                    working_gpu_encoders.append((encoder_name, description, 'fast'))
        except:
            pass
    
    # In Modal environment, try to fix GPU encoder issues instead of skipping
    if is_modal_environment:
        print_flush("[ENCODER DETECT] Modal environment detected - attempting GPU encoder fixes")
        
        # Try to install/enable GPU encoders if they're missing
        try:
            import subprocess
            # Check if we need to install additional GPU support
            nvidia_check = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=5)
            if nvidia_check.returncode == 0:
                print_flush("[ENCODER DETECT] NVIDIA GPU detected, attempting to enable encoders")
                # Try to install NVIDIA codecs if needed
                try:
                    subprocess.run(['apt-get', 'update'], capture_output=True, timeout=10)
                    subprocess.run(['apt-get', 'install', '-y', 'nvidia-cuda-toolkit'], capture_output=True, timeout=30)
                except:
                    pass
        except:
            pass
    
    if working_gpu_encoders:
        best_gpu = working_gpu_encoders[0]
        encoder_name, description, working_preset = best_gpu
        print_flush(f"[ENCODER DETECT] Using WORKING GPU encoder: {encoder_name} ({description}) with preset '{working_preset}'")
        
        # MAXIMUM PERFORMANCE WITH QUALITY MAINTAINED
        if 'nvenc' in encoder_name:
            # NVIDIA NVENC - Maximum performance with quality maintained
            return {
                'gpu_detected': True,  # Add this key for proper detection
                'fps': 24,  # Reduced for speed
                'codec': encoder_name,
                'audio_codec': 'aac',
                'preset': working_preset,  # Use the tested working preset
                'threads': 64,  # MAXIMUM threads for L4 GPU
                'verbose': False,
                'logger': None,
                # FFmpeg parameters for MAXIMUM SPEED (NVENC-specific)
                'ffmpeg_params': [
                    '-pix_fmt', 'yuv420p',  # Standard pixel format
                    '-colorspace', 'bt709',  # Standard color space
                    '-color_primaries', 'bt709',  # Standard color primaries
                    '-color_trc', 'bt709',  # Standard color transfer characteristics
                    '-color_range', 'tv',  # Standard color range
                    '-profile:v', 'baseline',  # Baseline profile for maximum speed
                    # NVENC doesn't support -level parameter, so we omit it
                    '-rc', 'vbr',  # Variable bitrate for better quality
                    '-cq', '18',  # Lower CQ for better quality while maintaining speed
                    '-b:v', '3M',  # Balanced bitrate for quality and speed
                    '-maxrate', '6M',  # Higher maxrate for better quality
                    '-bufsize', '6M',  # Higher buffer for better quality
                    '-g', '15',  # Smaller GOP for speed (was 30)
                    '-bf', '0',  # No B-frames for speed (was 1)
                    '-refs', '1',  # Fewer refs for speed (was 3)
                    '-movflags', '+faststart',  # Optimize for web streaming
                    '-tag:v', 'avc1'  # Proper codec tag
                ]
            }
        elif 'qsv' in encoder_name:
            # Intel QSV - Maximum performance with quality maintained
            return {
                'gpu_detected': True,  # Add this key for proper detection
                'fps': 30,
                'codec': encoder_name,
                'audio_codec': 'aac',
                'preset': working_preset,  # Use the tested working preset
                'threads': 16,
                'verbose': False,
                'logger': None,
                # FFmpeg parameters for color accuracy and performance (QSV-specific)
                'ffmpeg_params': [
                    '-pix_fmt', 'yuv420p',
                    '-colorspace', 'bt709',
                    '-color_primaries', 'bt709',
                    '-color_trc', 'bt709',
                    '-color_range', 'tv',
                    '-profile:v', 'main',
                    # QSV may not support -level parameter, so we omit it
                    '-rc', 'vbr',
                    '-cq', '18',
                    '-b:v', '5M',
                    '-maxrate', '10M',
                    '-bufsize', '10M',
                    '-g', '60',
                    '-bf', '3',
                    '-refs', '6',
                    '-movflags', '+faststart',
                    '-tag:v', 'avc1'
                ]
            }
        elif 'amf' in encoder_name:
            # AMD AMF - Maximum performance with quality maintained
            return {
                'gpu_detected': True,  # Add this key for proper detection
                'fps': 30,
                'codec': encoder_name,
                'audio_codec': 'aac',
                'preset': working_preset,  # Use the tested working preset
                'threads': 16,
                'verbose': False,
                'logger': None,
                # FFmpeg parameters for color accuracy and performance (AMF-specific)
                'ffmpeg_params': [
                    '-pix_fmt', 'yuv420p',
                    '-colorspace', 'bt709',
                    '-color_primaries', 'bt709',
                    '-color_trc', 'bt709',
                    '-color_range', 'tv',
                    '-profile:v', 'main',
                    # AMF may not support -level parameter, so we omit it
                    '-rc', 'vbr',
                    '-cq', '18',
                    '-b:v', '5M',
                    '-maxrate', '10M',
                    '-bufsize', '10M',
                    '-g', '60',
                    '-bf', '3',
                    '-refs', '6',
                    '-movflags', '+faststart',
                    '-tag:v', 'avc1'
                ]
            }
        else:
            # Generic GPU encoder
            return {
                'gpu_detected': True,  # Add this key for proper detection
                'fps': 30,
                'codec': encoder_name,
                'audio_codec': 'aac',
                'preset': working_preset,  # Use the tested working preset
                'threads': 16,
                'verbose': False,
                'logger': None,
                # FFmpeg parameters for color accuracy and performance (GPU-specific)
                'ffmpeg_params': [
                    '-pix_fmt', 'yuv420p',
                    '-colorspace', 'bt709',
                    '-color_primaries', 'bt709',
                    '-color_trc', 'bt709',
                    '-color_range', 'tv',
                    '-profile:v', 'main',
                    # GPU encoders may not support -level parameter, so we omit it
                    '-rc', 'vbr',
                    '-cq', '18',
                    '-b:v', '5M',
                    '-maxrate', '10M',
                    '-bufsize', '10M',
                    '-g', '60',
                    '-bf', '3',
                    '-refs', '6',
                    '-movflags', '+faststart',
                    '-tag:v', 'avc1'
                ]
            }
    
    # Fallback to CPU encoder (optimized for speed with quality)
    elif cpu_encoders:
        best_cpu = cpu_encoders[0]
        encoder_name, description = best_cpu
        print_flush(f"[ENCODER DETECT] Using CPU encoder: {encoder_name} ({description})")
        
        return {
            'gpu_detected': False,  # Add this key for proper detection
            'fps': 30,
            'codec': encoder_name,
            'audio_codec': 'aac',
            'preset': 'ultrafast',
            'threads': 16,  # Use maximum CPU threads for speed
            'verbose': False,
            'logger': None
        }
    
    else:
        print_flush("[ENCODER DETECT] No suitable encoders found, using default")
        return {
            'gpu_detected': False,  # Add this key for proper detection
            'fps': 30,
            'codec': 'libx264',
            'audio_codec': 'aac',
            'preset': 'ultrafast',
            'threads': 16,
            'verbose': False,
            'logger': None
        }

# Utility: always flush stdout after print

def print_flush(*args, **kwargs):
    """Print with immediate flush to ensure output is visible"""
    print(*args, **kwargs, flush=True)

# Global variable to track video generation progress
video_generation_progress = {
    'current_step': 'Not started',
    'start_time': None,
    'last_update': None,
    'memory_usage': 0,
    'is_running': False
}

def update_progress(step, memory_usage=None):
    """Update the global progress tracking"""
    global video_generation_progress
    import time
    import psutil
    
    video_generation_progress['current_step'] = step
    video_generation_progress['last_update'] = time.time()
    if memory_usage is None:
        video_generation_progress['memory_usage'] = psutil.virtual_memory().percent
    else:
        video_generation_progress['memory_usage'] = memory_usage

def get_video_generation_status():
    """Get the current status of video generation"""
    global video_generation_progress
    import time
    
    if not video_generation_progress['is_running']:
        return {
            'status': 'not_running',
            'current_step': 'Not started',
            'elapsed_time': 0,
            'memory_usage': 0
        }
    
    elapsed = time.time() - video_generation_progress['start_time']
    return {
        'status': 'running',
        'current_step': video_generation_progress['current_step'],
        'elapsed_time': elapsed,
        'memory_usage': video_generation_progress['memory_usage'],
        'last_update': video_generation_progress['last_update']
    }

class VideoGeneratorPortrait:
    def __init__(self, segments_folder, transcripts_folder, font_folder, session_id=None):
        """Initialize VideoGeneratorPortrait with GPU acceleration support - EXACT SAME LOGIC AS LANDSCAPE"""
        self.segments_folder = segments_folder
        self.transcripts_folder = transcripts_folder
        self.font_folder = font_folder
        self.session_id = session_id
        
        # Debug mode for logging
        self.debug_mode = False  # Disable debug logging for better performance
        
        # Portrait dimensions
        self.width = 1080
        self.height = 1920
        self.fps = 24      # Reduced from 30 for 25% speed improvement
        
        # Colors
        self.text_color = (0, 0, 0)  # Black for better visibility
        self.subtitle_color = (255, 255, 255)  # White
        self.subtitle_bg_color = (0, 0, 0, 128)  # Semi-transparent black
        
        # Font loading with GPU acceleration
        self._load_fonts()
        
        # GPU image processing setup
        self.gpu_image_processing = GPU_IMAGE_PROCESSING
        if self.gpu_image_processing:
            print(f"[GPU] Initializing GPU image processing for session: {session_id}")
            # Initialize CUDA memory pool for better performance
            try:
                cuda.setDevice(0)
                print(f"[GPU] CUDA device 0 selected for image processing")
            except Exception as e:
                print(f"[GPU] Warning: Could not set CUDA device: {e}")
                self.gpu_image_processing = False
        
        # Load word segments for subtitle generation
        self.word_segments = []

    def _detect_hindi_script(self, text):
        """Detect if text contains Hindi characters"""
        hindi_chars = set('अआइईउऊएऐओऔकखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहक्षत्रज्ञड़ढ़')
        return any(char in hindi_chars for char in text)

    def _get_font_for_language(self, text, font_size=48):
        """Detect language and return appropriate font with similar style"""
        # Hindi character detection
        hindi_chars = set('अआइईउऊएऐओऔकखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहक्षत्रज्ञड़ढ़')
        
        # Check if text contains Hindi characters
        if any(char in hindi_chars for char in text):
            # Use system fonts that support Hindi Devanagari script
            system_fonts = [
                'C:/Windows/Fonts/arial.ttf',  # Windows Arial (supports Hindi)
                'C:/Windows/Fonts/calibri.ttf',  # Windows Calibri (supports Hindi)
                'C:/Windows/Fonts/segoeui.ttf',  # Windows Segoe UI (supports Hindi)
                '/System/Library/Fonts/Arial Unicode MS.ttf',  # macOS
                '/System/Library/Fonts/Helvetica.ttc',  # macOS fallback
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # Linux
            ]
            
            for font_path in system_fonts:
                try:
                    return ImageFont.truetype(font_path, font_size)
                except:
                    continue
            
            # Final fallback to CircularStd if no Hindi fonts found
            print_flush(f"[FONT] Warning: No Hindi fonts found, using CircularStd (may not display Hindi properly)")
            return ImageFont.truetype(os.path.join(self.font_folder, 'CircularStd-Book.ttf'), font_size)
        else:
            # Use existing CircularStd for Latin scripts
            return ImageFont.truetype(os.path.join(self.font_folder, 'CircularStd-Book.ttf'), font_size)

    def _load_fonts(self):
        # Load fonts with Hindi support
        self.title_font = self._get_font_for_language("", 72)
        self.body_font = self._get_font_for_language("", 36)
        self.subtitle_font = self._get_font_for_language("", 48)
        self.subtitle_overlay_font = self._get_font_for_language("", 42)
        
        if self.debug_mode:
            print_flush(f"[FONT DEBUG] Loaded fonts - Title: {self.title_font}, Body: {self.body_font}")

    def load_segments_data(self, segments_file):
        """Load segments data from JSON file"""
        with open(segments_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_word_segments(self, word_srt_file):
        """Load word-level segments from SRT file"""
        word_segments = []
        with open(word_srt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse SRT format
        blocks = content.strip().split('\n\n')
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                timing = lines[1]
                text = ' '.join(lines[2:])
                
                # Parse timing
                start_time, end_time = self.parse_srt_time(timing)
                
                word_segments.append({
                    'start': start_time,
                    'end': end_time,
                    'text': text.strip()
                })
        
        return word_segments

    def parse_srt_time(self, timing_str):
        """Parse SRT timing format (HH:MM:SS,mmm)"""
        def time_to_seconds(time_str):
            hours, minutes, seconds = time_str.split(':')
            seconds, milliseconds = seconds.split(',')
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000
        
        start_str, end_str = timing_str.split(' --> ')
        return time_to_seconds(start_str), time_to_seconds(end_str)

    def _draw_subtitle(self, img, subtitle_text):
        """Draw subtitle text on the image"""
        if not subtitle_text:
            return
        
        draw = ImageDraw.Draw(img, 'RGBA')
        margin = 60
        max_width = self.width - 2 * margin
        
        # Get appropriate font for the text (supports Hindi)
        font = self._get_font_for_language(subtitle_text, 42)
        
        # Wrap subtitle if needed
        words = subtitle_text.split()
        lines = []
        current_line = ''
        for word in words:
            test_line = current_line + (' ' if current_line else '') + word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        # Draw background rectangle
        total_height = len(lines) * (font.size + 8) - 8
        y = self.height - margin - total_height
        max_line_width = max(draw.textbbox((0,0), line, font=font)[2] - draw.textbbox((0,0), line, font=font)[0] for line in lines)
        x = (self.width - max_line_width) // 2 - 20
        rect_w = max_line_width + 40
        rect_h = total_height + 20
        rect_y = y - 10
        draw.rounded_rectangle([x, rect_y, x+rect_w, rect_y+rect_h], radius=18, fill=(255,255,255,180))
        
        # Draw lines on top
        y_line = y
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x_line = (self.width - w) // 2
            draw.text((x_line, y_line), line, fill=(0,0,0), font=font)
            y_line += font.size + 8

    def _wrap_text(self, text, font, max_width, draw):
        """Wrap text to fit within max_width"""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
            
            if text_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Single word is too long, force it
                    lines.append(word)
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines

    def _center_crop_cover(self, img, target_width, target_height):
        """Scale and crop image to fill target size"""
        if isinstance(img, np.ndarray):
            img = Image.fromarray(img)
        
        # Calculate aspect ratios
        img_aspect = img.width / img.height
        target_aspect = target_width / target_height
        
        if img_aspect > target_aspect:
            # Image is wider, crop width
            new_width = int(img.height * target_aspect)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            # Image is taller, crop height
            new_height = int(img.width / target_aspect)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))
        
        # Resize to target size
        img = img.resize((target_width, target_height), Image.LANCZOS)
        return img 

    def create_slide_image(self, slide_dict, current_time, segment_start_time, slide_bullet_offset=0, background_img=None, subtitle_text=None, reveal_state=None, segment_duration=None, cached_ideogram_img=None):
        """Render slide from slide_dict (JSON) according to format, with typewriter and highlight animation - EXACT SAME LOGIC AS LANDSCAPE"""
        format_type = slide_dict.get('format', 1)
        title = slide_dict.get('title', None)
        bullets = slide_dict.get('bullets', [])
        image_prompt = slide_dict.get('image_prompt', None)
        highlight_info = slide_dict.get('highlight_info', None)  # Optionally pass highlight info
        if background_img is None:
            raise ValueError("[BG][ERROR] No background image provided to create_slide_image! This should never happen.")
        img = background_img.copy()
        # Load generated Ideogram image for image slots (for formats 2, 3, 4)
        slide_number = slide_dict.get('slide_number', 1)
        format_type = slide_dict.get('format', 1)
        
        # Use cached Ideogram image if provided (performance optimization)
        sample_img = None
        if cached_ideogram_img is not None:
            # Use pre-processed cached image
            sample_img = Image.fromarray(cached_ideogram_img)
            if self.debug_mode and current_time < 0.1:  # Only log first few frames
                print_flush(f"[IMAGE] Using cached pre-processed Ideogram image for slide {slide_number}")
        else:
            # Fallback to loading from file (original method)
            ideogram_img_path = None
            if self.session_id:
                # Try session-specific folder first
                session_img_path = os.path.join('generated_images_ideogram', self.session_id, f'slide_{slide_number}_format_{format_type}.png')
                if os.path.exists(session_img_path):
                    ideogram_img_path = session_img_path
                    if self.debug_mode:
                        print_flush(f"[IMAGE] Using session-specific Ideogram image: {ideogram_img_path}")
            
            # Fallback to global folder if session-specific image not found
            if ideogram_img_path is None:
                ideogram_img_path = os.path.join('generated_images_ideogram', f'slide_{slide_number}_format_{format_type}.png')
            if os.path.exists(ideogram_img_path):
                if self.debug_mode:
                    print_flush(f"[IMAGE] Using global Ideogram image: {ideogram_img_path}")
            
            if ideogram_img_path and os.path.exists(ideogram_img_path):
                sample_img = Image.open(ideogram_img_path)
                # Apply GPU-accelerated color correction to fix Ideogram tinting issues
                if self.gpu_image_processing:
                    sample_img = self._gpu_color_correction(sample_img)
                    if self.debug_mode:
                        print_flush(f"[GPU] Applied GPU color correction to Ideogram image")
                else:
                    sample_img = self._correct_ideogram_colors(sample_img)
            else:
                # Fallback to sample image if Ideogram image doesn't exist
                sample_img_path = os.path.join('uploads', 'sample_image.jpg')
                if os.path.exists(sample_img_path):
                    sample_img = Image.open(sample_img_path)
                    if self.debug_mode:
                        print_flush(f"[IMAGE] Using fallback sample image: {sample_img_path}")
                else:
                    if self.debug_mode:
                        print_flush(f"[IMAGE] No image found for slide {slide_number}, format {format_type}")
        
        # Format 1: Heading + Bullets (text-only) - ADAPTED FOR PORTRAIT
        if format_type == 1:
            draw = ImageDraw.Draw(img)
            x0 = 80
            y0 = 120
            max_text_width = self.width - 2*x0
            if title:
                # Get appropriate font for title (supports Hindi)
                title_font = self._get_font_for_language(title, 72)
                lines = self._wrap_text(title, title_font, max_text_width, draw)
                for line in lines:
                    if self.debug_mode and current_time < 0.1:  # Only log first few frames
                        print_flush(f"[TITLE DEBUG] Format 1 - Drawing title line: '{line}' at position ({x0}, {y0}) with color {self.text_color}")
                    draw.text((x0, y0), line, fill=self.text_color, font=title_font)
                    y0 += title_font.size + 8
            y0 += 80  # Reduced spacing between title and bullets for smaller fonts
            fade_in_duration = 0.5
            for i, bullet in enumerate(bullets):
                alpha = int(255 * min(1.0, max(0, (current_time - segment_start_time - i*fade_in_duration)/fade_in_duration)))
                bullet_text = '\u2022 ' + bullet
                # Parse <highlight> tags in bullet
                import re
                m = re.search(r'<highlight>(.+?)</highlight>', bullet_text)
                if m:
                    highlight_word = m.group(1)
                    clean_bullet = re.sub(r'<highlight>(.+?)</highlight>', highlight_word, bullet_text)
                else:
                    highlight_word = None
                    clean_bullet = bullet_text
                # Get appropriate font for bullet text (supports Hindi)
                bullet_font = self._get_font_for_language(clean_bullet, 36)
                bullet_lines = self._wrap_text(clean_bullet, bullet_font, max_text_width, draw)
                for line in bullet_lines:
                    if highlight_word and highlight_word in line:
                        pre, word, post = line.partition(highlight_word)
                        w_pre = draw.textbbox((0,0), pre, font=bullet_font)[2]
                        w_word = draw.textbbox((0,0), word, font=bullet_font)[2]
                        h_word = bullet_font.size + 8
                        rect_x = x0 + w_pre
                        rect_y = y0 - 4
                        draw.rounded_rectangle([rect_x, rect_y, rect_x + w_word, rect_y + h_word], radius=8, fill=(255, 215, 0, int(alpha*0.8)))
                        draw.text((x0, y0), pre, fill=(0,0,0,alpha), font=bullet_font)
                        draw.text((x0 + w_pre, y0), word, fill=(0,0,0,alpha), font=bullet_font)
                        draw.text((x0 + w_pre + w_word, y0), post, fill=(0,0,0,alpha), font=bullet_font)
                    else:
                        draw.text((x0, y0), line, fill=(0,0,0,alpha), font=bullet_font)
                    y0 += bullet_font.size + 10
            self._draw_subtitle(img, subtitle_text)
            return img
        
        # Format 6: Top half image, bottom half text (PORTRAIT ADAPTATION)
        elif format_type == 6:
            if sample_img is not None:
                import math, random
                # Use the true segment duration for Ken Burns
                duration = segment_duration if segment_duration is not None else 8
                t = current_time - segment_start_time
                t = max(0, min(t, duration))
                random.seed(slide_dict.get('slide_number', 0))
                # Randomly pick effect type and direction
                effect_types = [
                    'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down',
                    'diag_tl_br', 'diag_tr_bl', 'diag_bl_tr', 'diag_br_tl'
                ]
                effect = random.choice(effect_types)
                progress = t / max(duration, 0.01)
                base_w, base_h = self.width, self.height // 2  # Top half only
                # Always start with a larger crop for movement, guarantee full coverage
                crop_scale_start = 1.18
                crop_scale_end = 1.0
                # For zoom in/out, interpolate scale
                if effect == 'zoom_in':
                    scale = crop_scale_start - (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                elif effect == 'zoom_out':
                    scale = crop_scale_end + (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                else:
                    # For pan/tilt/diagonal, always use crop_scale_start for full coverage
                    crop_w = int(base_w * crop_scale_start)
                    crop_h = int(base_h * crop_scale_start)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    # Pan/tilt/diagonal logic
                    max_dx = crop_w - base_w
                    max_dy = crop_h - base_h
                    if effect == 'pan_left':
                        dx = int(max_dx * progress)
                        dy = 0
                    elif effect == 'pan_right':
                        dx = int(max_dx * (1 - progress))
                        dy = 0
                    elif effect == 'pan_up':
                        dx = 0
                        dy = int(max_dy * progress)
                    elif effect == 'pan_down':
                        dx = 0
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_tl_br':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * progress)
                    elif effect == 'diag_tr_bl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * progress)
                    elif effect == 'diag_bl_tr':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_br_tl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * (1 - progress))
                    else:
                        dx = max_dx // 2
                        dy = max_dy // 2
                    sample_img_cropped = img_crop.crop((dx, dy, dx + base_w, dy + base_h))
                img.paste(sample_img_cropped, (0, 0))  # Paste in top half
            draw = ImageDraw.Draw(img, 'RGBA')
            x0 = 90  # Move title and bullets slightly more left for format 6
            y0 = self.height // 2 + 120  # Start text in bottom half
            max_text_width = self.width - 2*x0
            # --- Animation timing logic ---
            title_reveal_duration = 2.0
            bullet_fade_duration = 1.0
            bullet_pause = 1.0
            highlight_anim_duration = 0.7
            # Title typewriter effect (0-2s)
            if title:
                lines = self._wrap_text(title, self.title_font, max_text_width, draw)
                total_title_chars = sum(len(line) for line in lines)
                chars_to_show = int(min(1.0, max(0, (current_time - segment_start_time) / title_reveal_duration)) * total_title_chars)
                chars_drawn = 0
                for line in lines:
                    line_to_draw = line[:max(0, min(len(line), chars_to_show - chars_drawn))]
                    if self.debug_mode and current_time < 0.1:  # Only log first few frames
                        print_flush(f"[TITLE DEBUG] Drawing title line: '{line_to_draw}' at position ({x0}, {y0}) with color {self.text_color}")
                    draw.text((x0, y0), line_to_draw, fill=self.text_color, font=self.title_font)
                    chars_drawn += len(line)
                    y0 += self.title_font.size + 10
                y0 += 120  # Original spacing between title and bullets
            # Bullets fade in one by one, each over 0.7s, with 1s pause between
            bullets_start_time = segment_start_time + title_reveal_duration
            bullet_times = []
            for i in range(len(bullets)):
                bullet_times.append(bullets_start_time + i * (bullet_fade_duration + bullet_pause))
            all_bullets_revealed_time = bullets_start_time + len(bullets) * (bullet_fade_duration + bullet_pause) - bullet_pause
            for i, bullet in enumerate(bullets):
                bullet_appear = bullet_times[i]
                t = current_time - bullet_appear
                alpha = int(255 * min(1.0, max(0, t / bullet_fade_duration))) if t > 0 else 0
                if alpha == 0:
                    y0 += self.body_font.size + 32  # Still increment y0 to keep spacing
                    continue  # Skip drawing this bullet until its fade-in starts
                bullet_text = bullet
                # Parse <highlight> tags in bullet
                import re
                m = re.search(r'<highlight>(.+?)</highlight>', bullet_text)
                if m:
                    highlight_word = m.group(1)
                    clean_bullet = re.sub(r'<highlight>(.+?)</highlight>', highlight_word, bullet_text)
                else:
                    highlight_word = None
                    clean_bullet = bullet_text
                bullet_lines = self._wrap_text(clean_bullet, self.body_font, max_text_width, draw)
                for line_idx, line in enumerate(bullet_lines):
                    # Draw bullet dot only for the first line of each bullet point
                    if alpha > 0 and line_idx == 0:
                        dot_radius = 7
                        dot_y = y0 + self.body_font.size//2
                        draw.ellipse([x0 - 30, dot_y - dot_radius, x0 - 16, dot_y + dot_radius], fill=(0,0,0,alpha))
                    # Highlight animation logic
                    highlight_box_alpha = alpha
                    highlight_box_width = None
                    if highlight_word and highlight_word in line:
                        pre, word, post = line.partition(highlight_word)
                        w_pre = draw.textbbox((0,0), pre, font=self.body_font)[2]
                        w_word = draw.textbbox((0,0), word, font=self.body_font)[2]
                        h_word = self.body_font.size + 8
                        rect_x = x0 + w_pre
                        rect_y = y0 - 4
                        # Animate highlight box only after all bullets are revealed
                        highlight_anim_start = all_bullets_revealed_time
                        highlight_anim_t = current_time - highlight_anim_start
                        if highlight_anim_t > 0:
                            highlight_progress = min(1.0, highlight_anim_t / highlight_anim_duration)
                            highlight_box_width = int(w_word * highlight_progress)
                            draw.rounded_rectangle([rect_x, rect_y, rect_x + highlight_box_width, rect_y + h_word], radius=8, fill=(255, 215, 0, int(200*highlight_progress)))
                        draw.text((x0, y0), pre, fill=(0,0,0,alpha), font=self.body_font)
                        draw.text((x0 + w_pre, y0), word, fill=(0,0,0,alpha), font=self.body_font)
                        draw.text((x0 + w_pre + w_word, y0), post, fill=(0,0,0,alpha), font=self.body_font)
                    else:
                        draw.text((x0, y0), line, fill=(0,0,0,alpha), font=self.body_font)
                    y0 += self.body_font.size + 32  # Original spacing between bullet lines
            self._draw_subtitle(img, subtitle_text)
            return img
        
        # Format 7: Full image only (PORTRAIT ADAPTATION)
        elif format_type == 7:
            if sample_img is not None:
                import math, random
                # Use the true segment duration for Ken Burns
                duration = segment_duration if segment_duration is not None else 8
                t = current_time - segment_start_time
                t = max(0, min(t, duration))
                random.seed(slide_dict.get('slide_number', 0))
                # Randomly pick effect type and direction
                effect_types = [
                    'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down',
                    'diag_tl_br', 'diag_tr_bl', 'diag_bl_tr', 'diag_br_tl'
                ]
                effect = random.choice(effect_types)
                progress = t / max(duration, 0.01)
                base_w, base_h = self.width, self.height
                # Always start with a larger crop for movement, guarantee full coverage
                crop_scale_start = 1.18
                crop_scale_end = 1.0
                if effect == 'zoom_in':
                    scale = crop_scale_start - (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                elif effect == 'zoom_out':
                    scale = crop_scale_end + (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                else:
                    crop_w = int(base_w * crop_scale_start)
                    crop_h = int(base_h * crop_scale_start)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    max_dx = crop_w - base_w
                    max_dy = crop_h - base_h
                    if effect == 'pan_left':
                        dx = int(max_dx * progress)
                        dy = 0
                    elif effect == 'pan_right':
                        dx = int(max_dx * (1 - progress))
                        dy = 0
                    elif effect == 'pan_up':
                        dx = 0
                        dy = int(max_dy * progress)
                    elif effect == 'pan_down':
                        dx = 0
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_tl_br':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * progress)
                    elif effect == 'diag_tr_bl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * progress)
                    elif effect == 'diag_bl_tr':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_br_tl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * (1 - progress))
                    else:
                        dx = max_dx // 2
                        dy = max_dy // 2
                    sample_img_cropped = img_crop.crop((dx, dy, dx + base_w, dy + base_h))
                img.paste(sample_img_cropped, (0, 0))
            self._draw_subtitle(img, subtitle_text)
            return img
        
        # Format 5: Heading only, centered (PORTRAIT ADAPTATION)
        elif format_type == 5:
            draw = ImageDraw.Draw(img)
            if title:
                bbox = draw.textbbox((0,0), title, font=self.title_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (self.width - text_width)//2
                y = (self.height - text_height)//2
                draw.text((x, y), title, fill=self.text_color, font=self.title_font)
            self._draw_subtitle(img, subtitle_text)
            return img
        
        # Default fallback
        else:
            draw = ImageDraw.Draw(img)
            draw.text((100, 100), f"Slide format {format_type}", fill=self.text_color, font=self.title_font)
            self._draw_subtitle(img, subtitle_text)
            return img

    def create_subtitle_text(self, word_segments, current_time):
        """Create subtitle text for current time, showing at most 7 words per segment, refreshing only when a new 7-word segment is reached."""
        if self.debug_mode:
            print_flush(f"[DEBUG] create_subtitle_text called with {len(word_segments)} word segments, current_time={current_time}")
            if word_segments:
                print_flush(f"[DEBUG] First word segment: {word_segments[0]}")
        # Flatten all words up to current_time
        revealed_words = []
        for word in word_segments:
            if word['end'] <= current_time:
                revealed_words.append(word['text'])
            else:
                break
        # Show the most recent 7-word segment
        n = len(revealed_words)
        if n == 0:
            return ""
        # Find which 7-word segment we are in
        segment_size = 7
        segment_idx = (n - 1) // segment_size
        start_idx = segment_idx * segment_size
        end_idx = min(start_idx + segment_size, n)
        current_segment_words = revealed_words[start_idx:end_idx]
        current_sentence_text = " ".join(current_segment_words)
        return current_sentence_text

    def generate_video(self, segments_file, word_srt_file, audio_file, output_file, show_subtitles=True, selected_background=None):
        """Generate video from segments, SRT, and audio files - EXACT SAME LOGIC AS LANDSCAPE"""
        try:
            # Check for Hindi script and auto-disable subtitles
            segments_data = self.load_segments_data(segments_file)
            all_text = ' '.join([seg.get('text', '') for seg in segments_data['segments']])
            if self._detect_hindi_script(all_text):
                print_flush("[SUBTITLE] Hindi script detected - automatically disabling subtitles")
                show_subtitles = False
            
            # Force GPU mode if NVIDIA encoder is detected
            gpu_encoders, cpu_encoders = detect_available_encoders()
            if any('nvenc' in encoder[0] for encoder in gpu_encoders):
                print_flush("[VIDEO GEN START] GPU encoder detected: True")
                print_flush("[VIDEO GEN START] Forcing GPU mode - NVIDIA encoder detected!")
                os.environ['MOVIEPY_USE_GPU'] = '1'
                os.environ['FFMPEG_GPU'] = '1'
                os.environ['CUDA_VISIBLE_DEVICES'] = '0'
                os.environ['NVIDIA_VISIBLE_DEVICES'] = '0'
            
            print_flush(f"[VIDEO GEN START] Starting video generation at {datetime.now().strftime('%H:%M:%S')}")
            print_flush(f"[VIDEO GEN START] Input files: segments={segments_file}, srt={word_srt_file}, audio={audio_file}")
            print_flush(f"[VIDEO GEN START] Output file: {output_file}")
            print_flush(f"[VIDEO GEN START] Memory usage: {psutil.virtual_memory().percent}%")
            print_flush(f"[VIDEO GEN START] MoviePy version: {VideoFileClip.__module__}")
            
            # Check GPU performance
            gpu_stats = check_gpu_performance()
            
            # Detect best encoder
            encoder_info = get_best_encoder()
            print_flush(f"[VIDEO GEN START] GPU encoder detected: {encoder_info.get('gpu_detected', False)}")
            
            update_progress("Cleaning up previous run files")
            print_flush("[STEP 1] Cleaning up previous run files...")
            
            update_progress("Loading segments data")
            print_flush("[STEP 2] Loading segments data...")
            segments_data = self.load_segments_data(segments_file)
            print_flush(f"[STEP 2] Loaded {len(segments_data['segments'])} segments")
            
            update_progress("Loading word segments")
            print_flush("[STEP 3] Loading word segments...")
            word_segments = self.load_word_segments(word_srt_file)
            print_flush(f"[STEP 3] Loaded {len(word_segments)} word segments")
            
            update_progress("Loading slides.json")
            print_flush("[STEP 4] Loading slides.json...")
            slides_file = os.path.join(os.path.dirname(segments_file), 'slides.json')
            with open(slides_file, 'r', encoding='utf-8') as f:
                slides = json.load(f)
            print_flush(f"[STEP 4] Loaded {len(slides)} slides from slides.json")
            
            update_progress("Creating video clips")
            print_flush("[STEP 5] Creating video clips...")
            video_clips = []
            
            update_progress("Loading background image")
            print_flush("[STEP 6] Loading background image...")
            if selected_background:
                background_path = os.path.join('background', selected_background)
                print_flush(f"[STEP 6] Using user-selected background image: {background_path}")
            else:
                background_path = os.path.join('background', '1.jpg')
                print_flush(f"[STEP 6] Using default background image: {background_path}")
            
            background_img = Image.open(background_path)
            print_flush(f"[STEP 6] Loaded image mode: {background_img.mode}, size: {background_img.size}")
            
            if background_img.mode == 'RGBA':
                print_flush(f"[STEP 6][WARN] Image mode is RGBA, converting to RGB.")
                background_img = background_img.convert('RGB')
            
            # Pre-cache background image for performance
            background_img = background_img.resize((self.width, self.height), Image.LANCZOS)
            print_flush(f"[STEP 6] Resized background to {self.width}x{self.height}")
            
            # Pre-cache Ideogram images and color-corrected versions for performance
            print_flush("[STEP 6.5] Pre-caching Ideogram images...")
            ideogram_cache = {}
            
            # Use session-specific directory if available, otherwise fallback to global
            if self.session_id:
                session_ideogram_dir = os.path.join('generated_images_ideogram', self.session_id)
                if os.path.exists(session_ideogram_dir):
                    ideogram_dir = session_ideogram_dir
                    print_flush(f"[STEP 6.5] Using session-specific images: {session_ideogram_dir}")
                else:
                    ideogram_dir = 'generated_images_ideogram'
                    print_flush(f"[STEP 6.5] Session directory not found, using global: {ideogram_dir}")
            else:
                ideogram_dir = 'generated_images_ideogram'
                print_flush(f"[STEP 6.5] No session ID, using global: {ideogram_dir}")
            
            if os.path.exists(ideogram_dir):
                for filename in os.listdir(ideogram_dir):
                    if filename.endswith('.png') and 'slide_' in filename:
                        filepath = os.path.join(ideogram_dir, filename)
                        try:
                            img = Image.open(filepath)
                            if img.mode == 'RGBA':
                                img = img.convert('RGB')
                            
                            # Apply color correction once and cache as numpy array
                            img_array = np.array(img)
                            corrected_img = self._correct_ideogram_colors(img_array)
                            ideogram_cache[filename] = corrected_img
                            if self.debug_mode:
                                print_flush(f"[STEP 6.5] Cached color-corrected image: {filename}")
                        except Exception as e:
                            print_flush(f"[STEP 6.5] Error caching {filename}: {e}")

            def create_slide_image_with_bg(slide_dict, current_time, segment_start_time, subtitle_text=None, reveal_state=None, segment_duration=None):
                # Use cached background and pre-processed images for maximum performance
                if self.debug_mode and current_time < 0.1:  # Only log first few frames
                    print_flush(f'[BG] Using cached background image for slide at time {current_time}')
                
                # Get Ideogram image from cache for this specific segment
                ideogram_filename = None
                cached_ideogram_img = None
                if 'segment_id' in slide_dict and 'segment_format' in slide_dict:
                    # Use segment_id and segment_format for proper image lookup
                    segment_id = slide_dict['segment_id']
                    format_type = slide_dict['segment_format']
                    
                    # Get the specific format image - no fallback
                    ideogram_filename = f"slide_{segment_id}_format_{format_type}.png"
                    cached_ideogram_img = ideogram_cache.get(ideogram_filename)
                    
                    if self.debug_mode and current_time < 0.1:  # Only log first few frames
                        print_flush(f'[BG] Looking for image: {ideogram_filename}')
                        print_flush(f'[BG] Cached image found: {cached_ideogram_img is not None}')
                        print_flush(f'[BG] Available cached images: {list(ideogram_cache.keys())}')
                
                # Create slide image with optimized rendering
                return self.create_slide_image(slide_dict, current_time, segment_start_time, background_img=background_img, subtitle_text=subtitle_text, reveal_state=reveal_state, segment_duration=segment_duration, cached_ideogram_img=cached_ideogram_img)

            update_progress(f"Creating {len(segments_data['segments'])} video clips")
            print_flush(f"[STEP 7] Creating {len(segments_data['segments'])} video clips...")
            clip_creation_start = time.time()
            
            for idx, segment in enumerate(segments_data['segments']):
                segment_start = time.time()
                update_progress(f"Creating clip {idx+1}/{len(segments_data['segments'])}")
                if self.debug_mode:
                    print_flush(f"[STEP 7] Processing segment {idx+1}/{len(segments_data['segments'])}: {segment}")
                print_flush(f"[STEP 7] Memory usage: {psutil.virtual_memory().percent}%")
                
                if idx < len(slides):
                    slide_dict = slides[idx]
                    # Add segment information to slide_dict for proper image lookup
                    slide_dict['segment_id'] = segment['segment_id']
                    slide_dict['segment_format'] = segment['format']
                    
                    if self.debug_mode:
                        print_flush(f"[STEP 7] Using slide_dict for segment {idx}: title='{slide_dict.get('title', '')}', segment_id={segment['segment_id']}, format={segment['format']}")
                    duration = segment['end_time'] - segment['start_time']
                    if self.debug_mode:
                        print_flush(f"[STEP 7] Segment duration: {duration}s")
                    
                    def create_make_frame(slide_dict, segment_start_time, segment_idx, segment_duration):
                        def make_frame(t):
                            current_time = segment_start_time + t
                            # Only generate subtitle text if subtitles are enabled
                            subtitle_text = self.create_subtitle_text(word_segments, current_time) if show_subtitles else None
                            
                            # Create slide image with background (no reveal state for performance)
                            slide_img = create_slide_image_with_bg(slide_dict, current_time, segment_start_time, subtitle_text, None, segment_duration)
                            
                            # Convert to numpy array for MoviePy
                            return np.array(slide_img)
                        return make_frame
                    
                    make_frame = create_make_frame(slide_dict, segment['start_time'], idx, duration)
                    if self.debug_mode:
                        print_flush(f"[STEP 7] Creating VideoClip for segment {idx}...")
                    clip = VideoClip(make_frame, duration=duration)
                    if self.debug_mode:
                        print_flush(f"[STEP 7] Created clip for segment {idx} with duration {duration}s")
                    video_clips.append(clip)
                    if self.debug_mode:
                        print_flush(f"[STEP 7] Total clips so far: {len(video_clips)}")
                    
                    segment_time = time.time() - segment_start
                    if self.debug_mode:
                        print_flush(f"[STEP 7] Segment {idx+1} completed in {segment_time:.2f}s")
                else:
                    if self.debug_mode:
                        print_flush(f"[STEP 7][ERROR] No slide JSON for segment {idx}")
            
            clip_creation_time = time.time() - clip_creation_start
            print_flush(f"[STEP 7] All clips created in {clip_creation_time:.2f}s")
            print_flush(f"[STEP 7] Memory usage: {psutil.virtual_memory().percent}%")
            
            update_progress("Processing video clips")
            print_flush("[STEP 8] Processing video clips...")
            print_flush(f"[STEP 8] Processing {len(video_clips)} video clips")
            for i, clip in enumerate(video_clips):
                print_flush(f"[STEP 8] Clip {i}: duration={clip.duration}s")
            
            # Ensure the last slide stays until the end
            update_progress("Checking duration consistency")
            print_flush("[STEP 9] Checking duration consistency...")
            total_duration = segments_data['segments'][-1]['end_time']
            current_duration = sum([clip.duration for clip in video_clips])
            print_flush(f"[STEP 9] Total expected duration: {total_duration}s")
            print_flush(f"[STEP 9] Current clips duration: {current_duration}s")
            
            if current_duration < total_duration:
                print_flush(f"[STEP 9] Adding still frame for last slide to fill {total_duration - current_duration:.2f}s gap at end.")
                last_slide = slides[-1]
                last_segment = segments_data['segments'][-1]
                def make_last_frame(t):
                    reveal_time = last_segment['start_time'] + last_segment['duration'] + 5
                    return np.array(create_slide_image_with_bg(
                        last_slide,
                        reveal_time,
                        last_segment['start_time'],
                        subtitle_text=None if not show_subtitles else self.create_subtitle_text(word_segments, reveal_time),
                        segment_duration=last_segment['duration']
                    ))
                gap_duration = total_duration - current_duration
                if gap_duration > 0.01:
                    last_clip = VideoClip(make_last_frame, duration=gap_duration)
                    video_clips.append(last_clip)
                    print_flush(f"[STEP 9] Added gap-filling clip with duration {gap_duration}s")
            
            # Concatenate video clips
            update_progress("Concatenating video clips")
            print_flush("[STEP 10] Concatenating video clips...")
            final_video = concatenate_videoclips(video_clips)
            print_flush("[STEP 10] Video clips concatenated successfully")
            
            print_flush(f"[STEP 10] Final video duration: {final_video.duration}s")
            print_flush(f"[STEP 10] Memory usage: {psutil.virtual_memory().percent}%")
            
            update_progress("Loading audio file")
            print_flush("[STEP 11] Loading audio file...")
            audio_start = time.time()
            audio_clip = AudioFileClip(audio_file)
            audio_load_time = time.time() - audio_start
            print_flush(f"[STEP 11] Audio loaded in {audio_load_time:.2f}s, duration: {audio_clip.duration}s")
            
            update_progress("Compositing audio")
            print_flush("[STEP 12] Compositing final video with audio...")
            composite_start = time.time()
            final_video = final_video.set_audio(audio_clip)
            composite_time = time.time() - composite_start
            print_flush(f"[STEP 12] Audio composited in {composite_time:.2f}s")
            
            update_progress("Writing video file")
            print_flush(f"[STEP 13] Writing video file to {output_file}...")
            print_flush(f"[STEP 13] Video settings: fps={self.fps}, codec=libx264, preset=ultrafast, threads=8")
            print_flush(f"[STEP 13] Memory usage before write: {psutil.virtual_memory().percent}%")
            
            # Check environment variables for GPU acceleration
            gpu_env_vars = {k: v for k, v in os.environ.items() if any(x in k.upper() for x in ['GPU', 'CUDA', 'NVIDIA'])}
            print_flush(f"[STEP 13] Found MoviePy/FFmpeg/GPU environment variables: {gpu_env_vars}")
                
                # Check GPU performance before encoding
            gpu_stats = check_gpu_performance()
            print_flush(f"[STEP 13] GPU Status before encoding: {gpu_stats}")
            
            # Detect best available encoder for MAXIMUM performance
            print_flush("[STEP 13] Detecting best available encoder for MAXIMUM performance...")
            encoder_info = get_best_encoder()
            
            # Use the best encoder found
            if encoder_info.get('gpu_detected', False):
                print_flush("[STEP 13] Using MAXIMUM PERFORMANCE parameters:")
                print_flush(f"[STEP 13] {encoder_info}")
                
                # Write video with GPU acceleration
                write_start = time.time()
                final_video.write_videofile(
                    output_file,
                    fps=self.fps,
                    codec=encoder_info['codec'],
                    audio_codec='aac',
                    preset=encoder_info['preset'],
                    threads=encoder_info['threads'],
                    verbose=False,
                    logger=None,
                    ffmpeg_params=encoder_info['ffmpeg_params']
                )
                write_time = time.time() - write_start
                print_flush(f"[STEP 13] Video written with GPU acceleration in {write_time:.2f}s")
            else:
                # Fallback to CPU encoding
                print_flush("[STEP 13] Using CPU fallback encoding...")
                write_start = time.time()
                final_video.write_videofile(
                    output_file,
                    fps=self.fps,
                    codec='libx264',
                    audio_codec='aac',
                    preset='ultrafast',
                    threads=8,
                    verbose=False,
                    logger=None
                )
                write_time = time.time() - write_start
                print_flush(f"[STEP 13] Video written with CPU encoding in {write_time:.2f}s")
            
            # Check GPU performance after encoding
            gpu_stats_after = check_gpu_performance()
            print_flush(f"[STEP 13] GPU Status after encoding: {gpu_stats_after}")
            
            print_flush(f"[STEP 13] Memory usage after write: {psutil.virtual_memory().percent}%")
            print_flush(f"[STEP 13] Video generation completed successfully!")
            
            # Clean up
            final_video.close()
            audio_clip.close()
            for clip in video_clips:
                clip.close()
            
            return True
            
        except Exception as e:
            print_flush(f"[ERROR] Video generation failed: {e}")
            import traceback
            traceback.print_exc()
            return False 

    def _correct_ideogram_colors(self, img):
        """Apply color correction to Ideogram images to fix tinting issues"""
        # Handle both PIL Image and numpy array inputs
        if hasattr(img, 'mode'):
            # PIL Image
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img_array = np.array(img)
        else:
            # Numpy array
            img_array = img
        
        # Apply color correction (increase R/G, reduce B to fix blue tint)
        corrected = img_array.copy()
        corrected[:, :, 0] = np.clip(corrected[:, :, 0] * 1.1, 0, 255)  # Increase red
        corrected[:, :, 1] = np.clip(corrected[:, :, 1] * 1.1, 0, 255)  # Increase green
        corrected[:, :, 2] = np.clip(corrected[:, :, 2] * 0.9, 0, 255)  # Decrease blue
        
        # Only log color correction details in debug mode
        if self.debug_mode:
            avg_before = np.mean(img_array, axis=(0, 1))
            avg_after = np.mean(corrected, axis=(0, 1))
            print_flush(f"[COLOR CORRECTION] Before - R:{avg_before[0]:.1f} G:{avg_before[1]:.1f} B:{avg_before[2]:.1f}")
            print_flush(f"[COLOR CORRECTION] After - R:{avg_after[0]:.1f} G:{avg_after[1]:.1f} B:{avg_after[2]:.1f}")
        
        return corrected

    def _center_crop_cover(self, img, target_width, target_height):
        # Scale and crop the image to fill the target size (center crop, no squeeze)
        # Handle both PIL Image and numpy array inputs
        if hasattr(img, 'width'):
            # PIL Image
            img_ratio = img.width / img.height
        else:
            # Numpy array
            img_ratio = img.shape[1] / img.shape[0]
            # Convert to PIL Image for processing
            img = Image.fromarray(img)
        
        target_ratio = target_width / target_height
        
        if img_ratio > target_ratio:
            # Image is wider than target, crop width
            new_width = int(img.height * target_ratio)
            new_height = img.height
            left = (img.width - new_width) // 2
            top = 0
            right = left + new_width
            bottom = new_height
        else:
            # Image is taller than target, crop height
            new_width = img.width
            new_height = int(img.width / target_ratio)
            left = 0
            top = (img.height - new_height) // 2
            right = new_width
            bottom = top + new_height
        
        cropped = img.crop((left, top, right, bottom))
        return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

    def _gpu_resize_image(self, img, target_size):
        """GPU-accelerated image resizing"""
        if not self.gpu_image_processing:
            return img.resize(target_size, Image.LANCZOS)
        
        try:
            # Convert PIL to OpenCV format
            if img.mode == 'RGBA':
                img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGR)
            else:
                img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            
            # Upload to GPU
            gpu_img = cuda.GpuMat()
            gpu_img.upload(img_cv)
            
            # GPU resize
            gpu_resized = cuda.resize(gpu_img, target_size)
            
            # Download from GPU
            resized_cv = gpu_resized.download()
            
            # Convert back to PIL
            if img.mode == 'RGBA':
                resized_pil = Image.fromarray(cv2.cvtColor(resized_cv, cv2.COLOR_BGR2RGBA))
            else:
                resized_pil = Image.fromarray(cv2.cvtColor(resized_cv, cv2.COLOR_BGR2RGB))
            
            return resized_pil
            
        except Exception as e:
            if self.debug_mode:
                print(f"[GPU] GPU resize failed, falling back to CPU: {e}")
            return img.resize(target_size, Image.LANCZOS)
    
    def _gpu_color_correction(self, img):
        """GPU-accelerated color correction"""
        if not self.gpu_image_processing:
            return self._correct_ideogram_colors(img)
        
        try:
            # Convert PIL to OpenCV format
            if img.mode == 'RGBA':
                img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGR)
            else:
                img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            
            # Upload to GPU
            gpu_img = cuda.GpuMat()
            gpu_img.upload(img_cv)
            
            # GPU color correction (increase red/green, reduce blue)
            # Create color correction matrix
            correction_matrix = np.array([
                [1.1, 0, 0],    # Increase red by 10%
                [0, 1.1, 0],    # Increase green by 10%
                [0, 0, 0.9]     # Reduce blue by 10%
            ], dtype=np.float32)
            
            # Apply color correction on GPU
            gpu_corrected = cuda.transform(gpu_img, correction_matrix)
            
            # Download from GPU
            corrected_cv = gpu_corrected.download()
            
            # Convert back to PIL
            if img.mode == 'RGBA':
                corrected_pil = Image.fromarray(cv2.cvtColor(corrected_cv, cv2.COLOR_BGR2RGBA))
            else:
                corrected_pil = Image.fromarray(cv2.cvtColor(corrected_cv, cv2.COLOR_BGR2RGB))
            
            return corrected_pil
            
        except Exception as e:
            if self.debug_mode:
                print(f"[GPU] GPU color correction failed, falling back to CPU: {e}")
            return self._correct_ideogram_colors(img)
    
    def _gpu_blend_images(self, background, overlay, alpha=0.8):
        """GPU-accelerated image blending"""
        if not self.gpu_image_processing:
            # Fallback to PIL blending
            if background.mode != overlay.mode:
                overlay = overlay.convert(background.mode)
            return Image.blend(background, overlay, alpha)
        
        try:
            # Convert both images to OpenCV format
            if background.mode == 'RGBA':
                bg_cv = cv2.cvtColor(np.array(background), cv2.COLOR_RGBA2BGR)
            else:
                bg_cv = cv2.cvtColor(np.array(background), cv2.COLOR_RGB2BGR)
            
            if overlay.mode == 'RGBA':
                ov_cv = cv2.cvtColor(np.array(overlay), cv2.COLOR_RGBA2BGR)
            else:
                ov_cv = cv2.cvtColor(np.array(overlay), cv2.COLOR_RGB2BGR)
            
            # Upload to GPU
            gpu_bg = cuda.GpuMat()
            gpu_ov = cuda.GpuMat()
            gpu_bg.upload(bg_cv)
            gpu_ov.upload(ov_cv)
            
            # GPU blending
            gpu_blended = cuda.addWeighted(gpu_bg, 1-alpha, gpu_ov, alpha, 0)
            
            # Download from GPU
            blended_cv = gpu_blended.download()
            
            # Convert back to PIL
            if background.mode == 'RGBA':
                blended_pil = Image.fromarray(cv2.cvtColor(blended_cv, cv2.COLOR_BGR2RGBA))
            else:
                blended_pil = Image.fromarray(cv2.cvtColor(blended_cv, cv2.COLOR_BGR2RGB))
            
            return blended_pil
            
        except Exception as e:
            if self.debug_mode:
                print(f"[GPU] GPU blending failed, falling back to CPU: {e}")
            # Fallback to PIL blending
            if background.mode != overlay.mode:
                overlay = overlay.convert(background.mode)
            return Image.blend(background, overlay, alpha)

 