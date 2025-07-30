import modal

# Define a minimal Modal image for testing
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .pip_install("python-multipart>=0.0.5", "moviepy==1.0.3")
    .apt_install("ffmpeg")
    .env({
        "PYTHONUNBUFFERED": "1",
        "MOVIEPY_USE_GPU": "1",
        "FFMPEG_GPU": "1",
        "CUDA_VISIBLE_DEVICES": "0",
        "NVIDIA_VISIBLE_DEVICES": "0"
    })
    # Only essential files for testing
    .add_local_file("mainModel.py", "/root/mainModel.py", copy=True)
    .add_local_file("video_generator.py", "/root/video_generator.py", copy=True)
    .add_local_file("bgm_processor.py", "/root/bgm_processor.py", copy=True)
    .add_local_file("heygen_empty_spaces.json", "/root/heygen_empty_spaces.json", copy=True)
)

# Define the Modal App
app = modal.App("videogen3-test", image=image)

# Expose the FastAPI app as a web endpoint
@app.function(
    secrets=[
        modal.Secret.from_name("VideoGenSecret"),
    ],
    timeout=900,
    scaledown_window=600,
    cpu=16,
    gpu="L4",
    memory=32768,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def fastapi_app():
    import sys
    import os
    
    # Configure GPU environment
    os.environ['MOVIEPY_USE_GPU'] = '1'
    os.environ['FFMPEG_GPU'] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    os.environ['NVIDIA_VISIBLE_DEVICES'] = '0'
    
    sys.path.append("/root")
    from mainModel import app
    return app 