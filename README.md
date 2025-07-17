# VideoGEn2: Automated Video Generation Platform

## Overview
VideoGEn2 is an advanced system for generating professional-quality videos from audio files, audio URLs, or text scripts. It supports both single and bulk video generation, leveraging AI for transcription, slide creation, image generation, and highlight extraction. The platform provides both a web interface (Flask) and a REST API (FastAPI), and is optimized for local and cloud deployment.

---

## Features
- **Audio to Video**: Generate videos from uploaded audio, audio URLs, or scripts (with TTS via ElevenLabs).
- **Bulk Generation**: Process CSV files to generate multiple videos in batch mode.
- **AI-Powered**: Uses OpenAI Whisper for transcription, GPT-4o for slide generation, and Ideogram for context-aware images.
- **Subtitles & Highlights**: Automatic subtitle and highlight extraction for enhanced video engagement.
- **Custom Backgrounds**: Supports custom background images for all videos.
- **Optimized Image Generation**: Parallelized image generation for speed.
- **Status Tracking**: CSV status updates and error handling for bulk jobs.
- **Modular Codebase**: Flask app, FastAPI app, and modular scripts for easy extension and refactoring.

---

## Folder Structure
```
VideoGEn2/
├── app.py                  # Flask web app for manual video generation
├── main.py                 # FastAPI app for REST API
├── mainModel.py            # Alternative FastAPI implementation
├── modal_app.py            # Modal cloud deployment entrypoint
├── bulk_video_generator.py # Bulk video generation logic
├── run_bulk_generation.py  # Script to run bulk jobs
├── background/             # Background images (use 1.jpg as default)
├── bulk_csv/               # CSV files for bulk jobs
├── uploads/                # Output videos
├── transcripts/            # Generated transcripts/SRTs
├── segments/               # Audio and slide segments
├── generated_images/       # Images for slides
├── generated_images_ideogram/ # Ideogram-generated images
├── doodle_visuals/         # Doodle images (optional)
├── requirements.txt        # Python dependencies
├── runtime.txt             # Python version (e.g., python-3.12)
├── .env                    # API keys and secrets (not committed)
└── ...
```

---

## Code Flow
### 1. **Single Video Generation (Web or API)**
- **Input**: User uploads audio, provides audio URL, or enters a script.
- **Audio Processing**: Audio is transcribed using Whisper.
- **Slide Generation**: Slides are generated using GPT-4o.
- **Image Generation**: Ideogram creates context-aware images for each slide (parallelized for speed).
- **Highlight Extraction**: Key points are highlighted using GPT.
- **Video Assembly**: Video is generated with synchronized audio, subtitles, and images.
- **Output**: Video is saved to `uploads/`.

### 2. **Bulk Video Generation**
- **Input**: CSV file in `bulk_csv/` with columns: Course, Topic, Raw S3 URL, Status.
- **Processing**: Each row is processed as above, with status tracked in the CSV.
- **Output**: Videos organized by course/topic in `uploads/Course/`.

---

## Build & Run Instructions
### 1. **Clone the Repository**
```sh
git clone https://github.com/Raheel123-src/videoGen.git
cd VideoGEn2
```

### 2. **Set Up Python Environment**
```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. **Configure Environment Variables**
Create a `.env` file in the project root:
```
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=ftDdhfYtmfGP0tFlBYA1  # (optional)
```

### 4. **Prepare Assets**
- Place your background image as `background/1.jpg`.
- For bulk jobs, add your CSV files to `bulk_csv/`.

### 5. **Run the Web App (Flask)**
```sh
python app.py
# Visit http://localhost:5000
```

### 6. **Run the API (FastAPI)**
```sh
uvicorn main:app --reload
# Visit http://127.0.0.1:8000/docs for API docs
```

### 7. **Run Bulk Generation**
```sh
python run_bulk_generation.py
```

---

## Deployment
### **Local**
- Use the instructions above for local development.

### **Cloud (Render, Modal, etc.)**
- Ensure `runtime.txt` specifies a supported Python version (e.g., `python-3.12`).
- Set environment variables in your cloud provider's dashboard.
- For Render, set the start command to:
  - `uvicorn main:app --host 0.0.0.0 --port 10123`
- For Modal, use `modal_app.py` as the entrypoint.

---

## Refactoring Guidance
- **API Logic**: Centralize business logic in reusable modules (e.g., `video_generator.py`).
- **Config**: Use `.env` and environment variables for all secrets and API keys.
- **Testing**: Add tests for each major script (see `test_*.py` files).
- **Bulk vs. Single**: Keep bulk and single video logic modular for easy maintenance.
- **Image Generation**: Use the optimized script for all image generation tasks.
- **Error Handling**: Ensure all scripts update status and handle errors gracefully.

---

## Troubleshooting
- **Python Version**: If the wrong Python version is used in cloud, check `runtime.txt` and clear build cache.
- **Missing Files**: Ensure all required folders and files exist (see above).
- **API Keys**: Double-check `.env` for valid keys.
- **Logs**: Check console and API logs for detailed error messages.

---

## Resources & Docs
- [Bulk Generation Guide](BULK_GENERATION_README.md)
- [API Guide](FASTAPI_README.md)
- [Optimization Summary](OPTIMIZATION_SUMMARY.md)

--- 