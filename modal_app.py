import modal

# Define the Modal image with all necessary dependencies
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
    )
    .env({
        "PYTHONUNBUFFERED": "1",
        "MOVIEPY_USE_GPU": "1",
        "FFMPEG_GPU": "1"
    })
    # Core application files
    .copy_local_file("mainModel.py", "/app/mainModel.py")
    .copy_local_file("video_generator.py", "/app/video_generator.py")
    .copy_local_file("video_generator_portrait.py", "/app/video_generator_portrait.py")
    .copy_local_file("bgm_processor.py", "/app/bgm_processor.py")
    .copy_local_file("transition_manager.py", "/app/transition_manager.py")
    .copy_local_file("requirements.txt", "/app/requirements.txt")
    
    # Static assets and resources
    .copy_local_file("templates/", "/app/templates/")
    .copy_local_file("background/", "/app/background/")
    .copy_local_file("BGM/", "/app/BGM/")
    .copy_local_file("circular-std-font-family/", "/app/circular-std-font-family/")
)

# Create the Modal app
app = modal.App("video-generator-app", image=image)

@app.function(
    gpu=modal.gpu.L4(),
    timeout=3600,
    memory=8192,
    cpu=4
)
def run_fastapi_app():
    """
    Run the FastAPI application with GPU acceleration
    """
    import uvicorn
    import os
    import sys
    
    # Set working directory
    os.chdir("/app")
    
    # Set environment variables for GPU acceleration
    os.environ["MOVIEPY_USE_GPU"] = "1"
    os.environ["FFMPEG_GPU"] = "1"
    
    print("🚀 Starting Video Generator App on Modal with GPU L4...")
    print("📡 Server will be available at: http://0.0.0.0:8000")
    print("📚 API Documentation: http://0.0.0.0:8000/docs")
    print("⚡ GPU Acceleration: Enabled (L4)")
    print("💾 Memory: 8GB")
    print("🖥️ CPU: 4 cores")
    
    # Run the FastAPI app
    uvicorn.run(
        "mainModel:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )

@app.local_entrypoint()
def main():
    """
    Main entry point for local development
    """
    print("🚀 Starting Video Generator App on Modal...")
    print("☁️ Deploying to Modal cloud with GPU L4...")
    print("⚡ GPU-accelerated video processing enabled")
    print("🎬 Supporting both landscape and portrait orientations")
    print("🎵 BGM processing with crossfade support")
    print("🤖 HeyGen avatar overlay support")
    print("🖼️ Ideogram image generation")
    print("📊 OpenAI Whisper transcription")
    print("🎙️ ElevenLabs TTS integration")
    
    # Deploy to Modal cloud
    run_fastapi_app.remote()

# Optional: Add a health check endpoint
@app.function()
def health_check():
    """
    Health check function for monitoring
    """
    return {
        "status": "healthy",
        "gpu_available": True,
        "memory_gb": 8,
        "cpu_cores": 4,
        "timeout_seconds": 3600
    }

if __name__ == "__main__":
    main()
