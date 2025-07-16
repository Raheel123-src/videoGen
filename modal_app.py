import modal

# Define the Modal image with all dependencies and requirements
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .env({"PYTHONUNBUFFERED": "1"})
)

# Define the Modal App
app = modal.App("videogen2-fastapi", image=image)

# Mount all necessary directories for persistent and asset storage
mounts = [
    modal.Mount.from_local_dir("background", remote_path="/root/background"),
    modal.Mount.from_local_dir("circular-std-font-family", remote_path="/root/circular-std-font-family"),
    modal.Mount.from_local_dir("uploads", remote_path="/root/uploads"),
    modal.Mount.from_local_dir("transcripts", remote_path="/root/transcripts"),
    modal.Mount.from_local_dir("segments", remote_path="/root/segments"),
    modal.Mount.from_local_dir("generated_images_ideogram", remote_path="/root/generated_images_ideogram"),
    modal.Mount.from_local_dir("generated_images", remote_path="/root/generated_images"),
    modal.Mount.from_local_dir("doodle_visuals", remote_path="/root/doodle_visuals"),
    modal.Mount.from_local_dir("bulk_csv", remote_path="/root/bulk_csv"),
]

# Expose the FastAPI app as a web endpoint
@app.function(
    mounts=mounts,
    secrets=[modal.Secret.from_dotenv()],
    timeout=600,
    container_idle_timeout=300,
)
@modal.asgi_app()
def fastapi_app():
    import sys
    sys.path.append("/root")
    from mainModel import app
    return app