# FastAPI Video Generation API

## Overview
This API allows you to generate videos from audio files, audio URLs, or plain text scripts. It uses ElevenLabs for TTS (text-to-speech) when a script is provided, and then processes the audio to generate slides, highlights, and a final video.

## Features
- Accepts audio via file upload, URL, or script (with TTS)
- Supports custom voice, speed, stability, and similarity boost for TTS
- Generates subtitles, highlights, and video with background selection
- All processing is local; no cloud storage required

## How to Run
1. **Clone the repository**
2. **Install dependencies:**
   ```sh
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Set up your `.env` file** (see below)
4. **Run the API:**
   ```sh
   uvicorn main:app --reload
   ```
5. **Access the API docs:**
   Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Environment Variables (.env)
You must create a `.env` file in the project root with at least:
```
OPENAI_API_KEY=your_openai_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=ftDdhfYtmfGP0tFlBYA1  # (optional, default used if not set)
```

## API Endpoint
### `POST /process_and_generate_video`
Accepts `multipart/form-data` with the following parameters:

| Parameter         | Type     | Required | Description |
|-------------------|----------|----------|-------------|
| audio_file        | file     | No       | Audio file upload (mp3, wav, etc.) |
| audio_url         | string   | No       | URL to an audio file |
| script            | string   | No       | Plain text script to generate audio |
| speed             | float    | No       | TTS speed (default: 1.0) |
| voice_id          | string   | No       | ElevenLabs voice ID (default provided) |
| stability         | float    | No       | TTS stability (default: 0.35) |
| similarity_boost  | float    | No       | TTS similarity boost (default: 0.40) |
| video_name        | string   | Yes      | Name for the output video |
| show_subtitles    | string   | No       | 'true' or 'false' (default: 'true') |
| selected_background | string | No       | Background image filename |

**Note:** You must provide at least one of `audio_file`, `audio_url`, or `script`.

## Example `curl` Requests

### 1. Using an audio file upload
```sh
curl -X POST "http://127.0.0.1:8000/process_and_generate_video" \
  -F "audio_file=@/path/to/audio.mp3" \
  -F "video_name=my_video"
```

### 2. Using an audio URL
```sh
curl -X POST "http://127.0.0.1:8000/process_and_generate_video" \
  -F "audio_url=https://example.com/audio.mp3" \
  -F "video_name=my_video"
```

### 3. Using a script (TTS)
```sh
curl -X POST "http://127.0.0.1:8000/process_and_generate_video" \
  -F "script=Hello, this is my video script." \
  -F "video_name=my_video"
```

### 4. Using a script with custom TTS params
```sh
curl -X POST "http://127.0.0.1:8000/process_and_generate_video" \
  -F "script=Hello, this is my video script." \
  -F "speed=1.2" \
  -F "voice_id=ftDdhfYtmfGP0tFlBYA1" \
  -F "stability=0.5" \
  -F "similarity_boost=0.6" \
  -F "video_name=my_video"
```

## Dependencies
- fastapi
- uvicorn
- python-dotenv
- requests
- pydub
- openai
- whisper
- Flask (for legacy code reuse)
- Other dependencies as listed in `requirements.txt`

## Notes
- `.env` should **never** be committed to git (see `.gitignore`).
- All generated files (audio, video, subtitles, etc.) are stored locally in the appropriate folders.
- For more details, see the code in `main.py` and the FastAPI docs at `/docs` when running. 