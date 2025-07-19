import modal

# Define the Modal image with all dependencies and requirements
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .pip_install("python-multipart>=0.0.5", "moviepy==1.0.3")
    .apt_install("ffmpeg", "libgl1-mesa-glx", "libglib2.0-0", "libsm6", "libxext6", "libxrender-dev")
    .env({"PYTHONUNBUFFERED": "1"})
    .add_local_file("mainModel.py", "/root/mainModel.py", copy=True)
    .add_local_file("video_generator.py", "/root/video_generator.py", copy=True)
    .add_local_dir("background", "/root/background", copy=True)
    .add_local_dir("circular-std-font-family", "/root/circular-std-font-family", copy=True)
    .add_local_dir("uploads", "/root/uploads", copy=True)
    .add_local_dir("transcripts", "/root/transcripts", copy=True)
    .add_local_dir("segments", "/root/segments", copy=True)
    .add_local_dir("generated_images_ideogram", "/root/generated_images_ideogram", copy=True)
    .add_local_dir("generated_images", "/root/generated_images", copy=True)
    .add_local_dir("doodle_visuals", "/root/doodle_visuals", copy=True)
    .add_local_dir("bulk_csv", "/root/bulk_csv", copy=True)
)

# Define the Modal App
app = modal.App("videogen2-gpu-fastapi", image=image)

# Expose the FastAPI app as a web endpoint with GPU T4
@app.function(
    secrets=[
        modal.Secret.from_name("VideoGenSecret"),
    ],
    timeout=900,  # Increased timeout for GPU processing
    scaledown_window=600,  # Increased scaledown window
    cpu=16,  # Increased to 16 CPU cores for faster processing
    gpu="T4",  # Use GPU T4 for faster image generation and video processing
    memory=32768,  # 32GB RAM for better performance
    max_containers=10,  # Allow 10 concurrent requests (updated parameter name)
)
@modal.asgi_app()
def fastapi_app():
    import sys
    sys.path.append("/root")
    from mainModel import app
    return app
