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
        # CPU-only deployment; no NVIDIA packages required
    )
    .env({
        "PYTHONUNBUFFERED": "1",
        # Force CPU mode
        "MOVIEPY_USE_GPU": "0",
        "FFMPEG_GPU": "0"
    })
    # Core application files (only those actually used by mainModel.py)
    .add_local_file("mainModel.py", "/root/mainModel.py", copy=True)
    .add_local_file("video_generator.py", "/root/video_generator.py", copy=True)
    .add_local_file("video_generator_portrait.py", "/root/video_generator_portrait.py", copy=True)
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
app = modal.App("videogen3-cpu-fastapi", image=image)

# Expose the FastAPI app as a web endpoint (CPU only)
@app.function(
    secrets=[
        modal.Secret.from_name("VideoGenSecret"),
    ],
    timeout=1200,  # 20 min timeout
    scaledown_window=10,  # quick scale down after idle
    cpu=16,  # CPU cores
    memory=32768,  # 32GB RAM
    max_containers=100,  # Allow up to 25 containers
)
@modal.concurrent(max_inputs=4)  # Each container handles only one request at a time
@modal.asgi_app()
def fastapi_app():
    import sys
    import os
    
    # Force CPU mode inside the container
    os.environ['MOVIEPY_USE_GPU'] = '0'
    os.environ['FFMPEG_GPU'] = '0'
    # Avoid any OpenCV CUDA auto-detection logs in container
    os.environ['OPENCV_VIDEOIO_PRIORITY_MSMF'] = '0'
    os.environ['OPENCV_LOG_LEVEL'] = 'SILENT'
    
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
    if "/root" not in sys.path:
        sys.path.append("/root")
    
    # Import and return the FastAPI app
    from mainModel import app
    return app
