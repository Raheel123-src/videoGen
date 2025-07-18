import modal

# Define the Modal image with all dependencies and requirements
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .apt_install("ffmpeg", "libgl1-mesa-glx", "libglib2.0-0", "libsm6", "libxext6", "libxrender-dev")
    .env({"PYTHONUNBUFFERED": "1"})
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
    container_idle_timeout=300,
    cpu=8,  # Use 8 CPU cores for concurrent processing
)
@modal.asgi_app()
def fastapi_app():
    import sys
    sys.path.append("/root")
    from mainModel import app
    return app 