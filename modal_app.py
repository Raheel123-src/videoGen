import modal

# Define the Modal image with all dependencies and requirements
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .pip_install("moviepy>=1.0.0", "numpy>=1.21.0", "Pillow>=9.0.0", "decorator>=4.0.0", "imageio>=2.5", "imageio-ffmpeg>=0.4.0", "proglog>=0.1.9")
    .run_commands("pip3 install moviepy>=1.0.0 numpy>=1.21.0 Pillow>=9.0.0 decorator>=4.0.0 imageio>=2.5 imageio-ffmpeg>=0.4.0 proglog>=0.1.9")
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
app = modal.App("videogen2-fastapi", image=image)

# Expose the FastAPI app as a web endpoint
@app.function(
    secrets=[
        modal.Secret.from_name("openai-api-key"),
        modal.Secret.from_name("elevenlabs-api-key"),
        modal.Secret.from_name("ideogram-api-key"),
        modal.Secret.from_name("aws-credentials"),
    ],
    timeout=600,
    scaledown_window=300,
    cpu=8,  # Use 8 CPU cores for concurrent processing
)
@modal.asgi_app()
def fastapi_app():
    import sys
    sys.path.append("/root")
    from mainModel import app
    return app
