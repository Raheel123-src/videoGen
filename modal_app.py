import modal

# Define the Modal image with all dependencies and requirements
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .pip_install("python-multipart>=0.0.5", "moviepy==1.0.3")
    .apt_install(
        "ffmpeg", 
        "libgl1-mesa-glx", 
        "libglib2.0-0", 
        "libsm6", 
        "libxext6", 
        "libxrender-dev"
        # Removed NVIDIA packages as they're handled by Modal's GPU environment
    )
    .env({
        "PYTHONUNBUFFERED": "1",
        "MOVIEPY_USE_GPU": "1",  # Enable GPU acceleration
        "FFMPEG_GPU": "1",  # Enable FFmpeg GPU support
        "CUDA_VISIBLE_DEVICES": "0",  # Set CUDA device
        "NVIDIA_VISIBLE_DEVICES": "0"  # Set NVIDIA device
    })
    # Core application files (only those actually used by mainModel.py)
    .add_local_file("mainModel.py", "/root/mainModel.py", copy=True)
    .add_local_file("video_generator.py", "/root/video_generator.py", copy=True)
    .add_local_file("bgm_processor.py", "/root/bgm_processor.py", copy=True)
    .add_local_file("generate_images.py", "/root/generate_images.py", copy=True)
    .add_local_file("generate_images_ideogram.py", "/root/generate_images_ideogram.py", copy=True)
    .add_local_file("generate_images_ideogram_optimized.py", "/root/generate_images_ideogram_optimized.py", copy=True)
    .add_local_file("gpt_highlight_bullets.py", "/root/gpt_highlight_bullets.py", copy=True)
    .add_local_file("heygen_empty_spaces.json", "/root/heygen_empty_spaces.json", copy=True)
    
    # Static assets and directories (all required for video generation)
    .add_local_dir("background", "/root/background", copy=True)
    .add_local_dir("BGM", "/root/BGM", copy=True)
    .add_local_dir("circular-std-font-family", "/root/circular-std-font-family", copy=True)
    .add_local_dir("uploads", "/root/uploads", copy=True)
    .add_local_dir("transcripts", "/root/transcripts", copy=True)
    .add_local_dir("segments", "/root/segments", copy=True)
    .add_local_dir("generated_images_ideogram", "/root/generated_images_ideogram", copy=True)
)

# Define the Modal App
app = modal.App("videogen3-gpu-fastapi", image=image)

# Expose the FastAPI app as a web endpoint with GPU L4
@app.function(
    secrets=[
        modal.Secret.from_name("VideoGenSecret"),
    ],
    timeout=900,  # 15 min timeout for GPU processing
    scaledown_window=600,  # 10 min scaledown window
    cpu=16,  # 16 CPU cores for fast processing
    gpu="L4",  # Use GPU L4 for best performance
    memory=32768,  # 32GB RAM
)
@modal.concurrent(max_inputs=20)  # Enable up to 20 concurrent requests per container
@modal.asgi_app()
def fastapi_app():
    import sys
    import os
    
    # Configure GPU environment for Modal deployment
    os.environ['MOVIEPY_USE_GPU'] = '1'  # Enable GPU for Modal
    os.environ['FFMPEG_GPU'] = '1'  # Enable FFmpeg GPU support
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'  # Set CUDA device
    os.environ['NVIDIA_VISIBLE_DEVICES'] = '0'  # Set NVIDIA device
    
    # Fix PIL ANTIALIAS compatibility issue
    try:
        from PIL import Image
        # Add ANTIALIAS back for compatibility with older MoviePy versions
        if not hasattr(Image, 'ANTIALIAS'):
            Image.ANTIALIAS = Image.LANCZOS
        print("[MODAL DEPLOYMENT] Fixed PIL ANTIALIAS compatibility")
    except Exception as e:
        print(f"[MODAL DEPLOYMENT] Warning: Could not fix PIL compatibility: {e}")
    
    # Add root to Python path
    sys.path.append("/root")
    
    # Import and return the FastAPI app
    from mainModel import app
    return app
