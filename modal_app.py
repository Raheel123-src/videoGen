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
 

)

# Define the Modal App
app = modal.App("videogen2-gpu-fastapi", image=image)

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
@modal.concurrent(max_inputs=10)  # Enable up to 10 concurrent requests per container
@modal.asgi_app()
def fastapi_app():
    import sys
    sys.path.append("/root")
    from mainModel import app
    return app
