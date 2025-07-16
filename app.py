from flask import Flask, render_template, request, flash, send_file, redirect, jsonify
import os
import re
import requests
from urllib.parse import urlparse
import whisper
from pydub import AudioSegment
import json
from datetime import timedelta
from dotenv import load_dotenv
from openai import OpenAI
from video_generator import VideoGenerator
import glob
import random

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Required for flash messages

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
TRANSCRIPTS_FOLDER = 'transcripts'
SEGMENTS_FOLDER = 'segments'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'aac', 'ogg'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(TRANSCRIPTS_FOLDER):
    os.makedirs(TRANSCRIPTS_FOLDER)
if not os.path.exists(SEGMENTS_FOLDER):
    os.makedirs(SEGMENTS_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TRANSCRIPTS_FOLDER'] = TRANSCRIPTS_FOLDER
app.config['SEGMENTS_FOLDER'] = SEGMENTS_FOLDER

# Initialize Whisper model (load once for better performance)
whisper_model = None

def get_whisper_model():
    """Get or initialize Whisper model"""
    global whisper_model
    if whisper_model is None:
        whisper_model = whisper.load_model("base")  # You can use "tiny", "base", "small", "medium", "large"
    return whisper_model

def get_openai_client():
    """Get OpenAI client"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or api_key == 'your_openai_api_key_here':
        raise Exception("OpenAI API key not found. Please set OPENAI_API_KEY in .env file")
    return OpenAI(api_key=api_key)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_valid_audio_url(url):
    """Check if the URL is a valid audio file URL"""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        
        # Check if URL ends with an audio extension
        path = parsed.path.lower()
        return any(path.endswith(f'.{ext}') for ext in ALLOWED_EXTENSIONS)
    except:
        return False

def download_audio_file(url):
    """Download audio file from URL"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Extract filename from URL
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        # If no filename or no extension, generate one
        if not filename or '.' not in filename:
            filename = f"audio_{hash(url) % 10000}.mp3"
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Download the file
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return filename, filepath
    except requests.RequestException as e:
        raise Exception(f"Failed to download file: {str(e)}")
    except Exception as e:
        raise Exception(f"Error processing URL: {str(e)}")

def convert_to_mp3(audio_path):
    """Convert audio file to MP3 format for Whisper"""
    try:
        audio = AudioSegment.from_file(audio_path)
        mp3_path = audio_path.rsplit('.', 1)[0] + '.mp3'
        audio.export(mp3_path, format='mp3')
        return mp3_path
    except Exception as e:
        raise Exception(f"Error converting audio: {str(e)}")

def transcribe_audio(audio_path):
    """Transcribe audio file using Whisper and return both sentence and word segments"""
    try:
        # Convert to MP3 if needed (Whisper works best with MP3)
        if not audio_path.lower().endswith('.mp3'):
            audio_path = convert_to_mp3(audio_path)
        
        # Load Whisper model
        model = get_whisper_model()
        
        # Transcribe with word-level timestamps
        result = model.transcribe(audio_path, word_timestamps=True)
        
        if result and 'segments' in result:
            # Extract sentence segments (original functionality)
            sentence_segments = []
            for segment in result['segments']:
                sentence_segments.append({
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'].strip()
                })
            
            # Extract word-level segments
            word_segments = []
            for segment in result['segments']:
                if 'words' in segment:
                    for word in segment['words']:
                        word_segments.append({
                            'start': word['start'],
                            'end': word['end'],
                            'text': word['word'].strip()
                        })
            
            return sentence_segments, word_segments
        else:
            raise Exception("No transcript found")
                
    except Exception as e:
        raise Exception(f"Error transcribing audio: {str(e)}")

def create_audio_segments(sentence_segments, segment_duration=15):
    """Create audio segments of specified duration"""
    if not sentence_segments:
        return []
    
    # Get total duration
    total_duration = sentence_segments[-1]['end']
    
    # Create fixed time-based segments
    segments = []
    segment_start = 0
    
    while segment_start < total_duration:
        segment_end = min(segment_start + segment_duration, total_duration)
        
        # Find all sentences that fall within this time window
        segment_text = ""
        for sentence in sentence_segments:
            # Check if sentence overlaps with current segment
            sentence_start = sentence['start']
            sentence_end = sentence['end']
            
            # If sentence overlaps with segment, include it
            if (sentence_start < segment_end and sentence_end > segment_start):
                if segment_text:
                    segment_text += " " + sentence['text']
                else:
                    segment_text = sentence['text']
        
        # Only create segment if there's text
        if segment_text.strip():
            segments.append({
                'start': segment_start,
                'end': segment_end,
                'text': segment_text.strip(),
                'sentences': [s for s in sentence_segments if s['start'] < segment_end and s['end'] > segment_start]
            })
        
        segment_start = segment_end
    
    return segments

def clean_json_block(raw):
    # Remove triple backticks and optional 'json' after them
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.lstrip('`')
        if raw.lower().startswith('json'):
            raw = raw[4:]
        raw = raw.lstrip('\n')
    if raw.endswith('```'):
        raw = raw.rstrip('`')
    return raw.strip()

def generate_slide_json_content(segment_text, segment_index, segment_duration, segment_title=None, previous_format=None):
    """Generate slide JSON for a segment using GPT-4o. Strict JSON output, with fix logic if needed."""
    client = get_openai_client()
    prompt = f'''
You are a presentation expert specializing in Indian corporate environments.

Given the following transcript segment and its duration, output a single JSON object for the slide with these fields:
- slide_number (integer)
- format (integer, 2-4)
- title (string)
- bullets (array of strings, each may contain <highlight> tags, or empty array if not needed)
- image_prompt (string, required for all formats 2, 3, or 4; do NOT include the word 'ideogram')

**CRITICAL FORMAT RULE:**
- You MUST randomly select a format number between 2-4 for each slide
- NEVER use the same format as the previous slide (previous_format={previous_format})
- If previous_format is {previous_format}, choose ANY format except {previous_format}
- Use random selection to ensure variety: formats 2, 3, 4 should all be used throughout the presentation
- Do NOT use format 1 or format 5. Do NOT favor any particular format - truly randomize your choice

**INDIAN OFFICE IMAGE REQUIREMENTS:**
For image_prompt, generate highly detailed prompts that produce **realistic Indian human characters** in **modern Indian corporate office environments**. The image should directly relate to the slide content and transcript segment:

📌 **Context Integration:**
- **Analyze the transcript segment** and extract key themes, emotions, or concepts
- **Match the image to the slide content** - if the slide talks about stress management, show stressed professionals; if it's about teamwork, show collaborative scenes
- **Incorporate specific elements** mentioned in the transcript (e.g., if "deadlines" are mentioned, show time pressure scenarios)
- **Reflect the tone and mood** of the content (calm, energetic, focused, collaborative, etc.)

📌 **Character Requirements:**
- Use **Indian ethnicity, attire, and context** (e.g., kurta with ID badge, formal shirt, women in saree/blazer, men in formal shirts, Indian facial features)
- Include diverse Indian professionals (different ages, genders, ethnicities within India)
- Pose and expression should match the **emotion or theme of the slide** (empathy, stress, teamwork, productivity, growth, leadership)
- **Facial expressions and body language** should reflect the content's emotional tone

📌 **Office Environment Requirements:**
- **Indian office settings** (open-plan workspace, glass partitions, laptops, Indian-style furniture, indoor plants, name boards in Hindi/English, HR posters in background)
- **Modern Indian corporate atmosphere** (clean desks, Indian corporate culture elements)
- **Natural or soft corporate lighting** (fluorescent or LED lighting common in Indian offices)
- Include subtle Indian cultural elements (calendar with Indian festivals, tea cups, etc.)
- **Scene composition** should support the slide's message (e.g., focused individual work, team meetings, training sessions)

📌 **Quality Requirements:**
- **Photorealistic, professional Indian** visuals only
- Avoid cartoon or generic western-style visuals
- Vary people and angles slightly across slides while maintaining realism
- No logos or copyrighted branding
- **Ensure the image directly supports** the slide's educational or professional development message

**Example image_prompt format:**
"A diverse group of Indian professionals in a modern Bangalore office, men in formal shirts and women in sarees/blazers, gathered around a glass conference table, natural lighting from large windows, laptops and notebooks visible, indoor plants in background, professional corporate atmosphere, photorealistic, 1024x1024"

Transcript:
"""
{segment_text}
"""
Duration: {segment_duration:.2f} seconds
Title: {segment_title or f"Slide {segment_index+1}"}
'''
    def try_parse_json(raw):
        try:
            cleaned = clean_json_block(raw)
            return json.loads(cleaned)
        except Exception:
            return None
    # First attempt
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a presentation content expert. Output only the JSON object, no commentary."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=700,
        temperature=0.4
    )
    raw_json = response.choices[0].message.content.strip()
    slide_json = try_parse_json(raw_json)
    # If parsing fails, ask GPT-4o to fix the JSON
    if slide_json is None:
        fix_prompt = f"Fix this JSON and return only the corrected JSON object, no commentary:\n{raw_json}"
        fix_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a JSON fixer. Output only the corrected JSON object, no commentary."},
                {"role": "user", "content": fix_prompt}
            ],
            max_tokens=700,
            temperature=0.2
        )
        fixed_json = fix_response.choices[0].message.content.strip()
        slide_json = try_parse_json(fixed_json)
        if slide_json is None:
            raise Exception(f"Failed to parse/fix JSON for segment {segment_index}. Raw: {raw_json}")
    return slide_json

import re

def extract_script_bullets(segment_text, max_bullets=5, max_words=6):
    # Split into sentences (simple split on . ! ?)
    sentences = re.split(r'[.!?]', segment_text)
    bullets = []
    seen = set()
    for sentence in sentences:
        phrase = ' '.join(sentence.strip().split()[:max_words])
        if phrase and phrase.lower() not in seen:
            bullets.append(phrase)
            seen.add(phrase.lower())
        if len(bullets) >= max_bullets:
            break
    return bullets

def create_segments_file(segments, output_path):
    """Create both slides.json and segments.json files"""
    try:
        # Create slides.json
        slides = []
        total_segments = len(segments)
        previous_format = None
        for i, segment in enumerate(segments):
            percent = int((i+1)/total_segments*100)
            print(f"Generating slide JSON for segment {i+1}/{total_segments} ({percent}%)", flush=True)
            slide_json = generate_slide_json_content(segment['text'], i, segment['end'] - segment['start'], previous_format=previous_format)
            previous_format = slide_json.get('format', previous_format)
            slides.append(slide_json)
        
        # Save the slides.json file
        slides_json_path = os.path.join(app.config['SEGMENTS_FOLDER'], 'slides.json')
        with open(slides_json_path, 'w', encoding='utf-8') as f:
            json.dump(slides, f, indent=2, ensure_ascii=False)
        print(f"Slides JSON saved: {slides_json_path}")
        
        # Create segments.json with proper timing keys
        segments_data = {
            "segments": []
        }
        for i, segment in enumerate(segments):
            segment_data = {
                "segment_id": i + 1,
                "start_time": segment['start'],
                "end_time": segment['end'],
                "duration": segment['end'] - segment['start'],
                "text": segment['text']
            }
            segments_data["segments"].append(segment_data)
        
        # Save the segments.json file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(segments_data, f, indent=2, ensure_ascii=False)
        print(f"Segments JSON saved: {output_path}")
        
        return True
    except Exception as e:
        raise Exception(f"Error creating segments files: {str(e)}")

def format_time(seconds):
    """Convert seconds to SRT time format (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    milliseconds = int((secs % 1) * 1000)
    secs = int(secs)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def create_srt_file(segments, output_path):
    """Create SRT file from transcription segments"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                start_time = format_time(segment['start'])
                end_time = format_time(segment['end'])
                
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{segment['text']}\n\n")
        
        return True
    except Exception as e:
        raise Exception(f"Error creating SRT file: {str(e)}")

def create_word_srt_file(word_segments, output_path):
    """Create word-by-word SRT file"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, word in enumerate(word_segments, 1):
                start_time = format_time(word['start'])
                end_time = format_time(word['end'])
                
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{word['text']}\n\n")
        
        return True
    except Exception as e:
        raise Exception(f"Error creating word SRT file: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def index():
    message = ''
    srt_file_path = None
    word_srt_file_path = None
    segments_file_path = None
    # List available backgrounds
    background_images = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
    selected_background = None
    if request.method == 'POST':
        selected_background = request.form.get('selected_background')
        # Check if a file was uploaded
        if 'audio_file' in request.files:
            file = request.files['audio_file']
            if file.filename == '':
                # Check if URL was provided instead
                audio_url = request.form.get('audio_url', '').strip()
                if audio_url:
                    if is_valid_audio_url(audio_url):
                        try:
                            filename, filepath = download_audio_file(audio_url)
                            # Transcribe the downloaded file
                            sentence_segments, word_segments = transcribe_audio(filepath)
                            
                            # Create sentence-based SRT file
                            srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
                            srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], srt_filename)
                            create_srt_file(sentence_segments, srt_filepath)
                            
                            # Create word-based SRT file
                            word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
                            word_srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], word_srt_filename)
                            create_word_srt_file(word_segments, word_srt_filepath)
                            
                            # Create audio segments with visual content
                            audio_segments = create_audio_segments(sentence_segments, 15)
                            segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
                            segments_filepath = os.path.join(app.config['SEGMENTS_FOLDER'], segments_filename)
                            create_segments_file(audio_segments, segments_filepath)
                            
                            message = f'Processing complete! Files: {srt_filename}, {word_srt_filename}, {segments_filename}'
                            srt_file_path = srt_filepath
                            word_srt_file_path = word_srt_filepath
                            segments_file_path = segments_filepath
                        except Exception as e:
                            flash(f'Error processing audio: {str(e)}')
                    else:
                        flash('Invalid audio URL. Please provide a URL ending with an audio file extension (mp3, wav, m4a, aac, ogg)')
                else:
                    flash('Please either upload a file or provide an audio URL')
            elif file and allowed_file(file.filename):
                # Save the uploaded file
                filename = file.filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Transcribe the uploaded file
                try:
                    sentence_segments, word_segments = transcribe_audio(filepath)
                    
                    # Create sentence-based SRT file
                    srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
                    srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], srt_filename)
                    create_srt_file(sentence_segments, srt_filepath)
                    
                    # Create word-based SRT file
                    word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
                    word_srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], word_srt_filename)
                    create_word_srt_file(word_segments, word_srt_filepath)
                    
                    # Create audio segments with visual content
                    audio_segments = create_audio_segments(sentence_segments, 15)
                    segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
                    segments_filepath = os.path.join(app.config['SEGMENTS_FOLDER'], segments_filename)
                    create_segments_file(audio_segments, segments_filepath)
                    
                    message = f'Processing complete! Files: {srt_filename}, {word_srt_filename}, {segments_filename}'
                    srt_file_path = srt_filepath
                    word_srt_file_path = word_srt_filepath
                    segments_file_path = segments_filepath
                except Exception as e:
                    flash(f'Error transcribing audio: {str(e)}')
            else:
                flash('Invalid file type. Please upload an audio file (mp3, wav, m4a, aac, ogg)')
        else:
            # Check for audio URL
            audio_url = request.form.get('audio_url', '').strip()
            if audio_url:
                if is_valid_audio_url(audio_url):
                    try:
                        filename, filepath = download_audio_file(audio_url)
                        # Transcribe the downloaded file
                        sentence_segments, word_segments = transcribe_audio(filepath)
                        
                        # Create sentence-based SRT file
                        srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
                        srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], srt_filename)
                        create_srt_file(sentence_segments, srt_filepath)
                        
                        # Create word-based SRT file
                        word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
                        word_srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], word_srt_filename)
                        create_word_srt_file(word_segments, word_srt_filepath)
                        
                        # Create audio segments with visual content
                        audio_segments = create_audio_segments(sentence_segments, 15)
                        segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
                        segments_filepath = os.path.join(app.config['SEGMENTS_FOLDER'], segments_filename)
                        create_segments_file(audio_segments, segments_filepath)
                        
                        message = f'Processing complete! Files: {srt_filename}, {word_srt_filename}, {segments_filename}'
                        srt_file_path = srt_filepath
                        word_srt_file_path = word_srt_filepath
                        segments_file_path = segments_filepath
                    except Exception as e:
                        flash(f'Error processing audio: {str(e)}')
                else:
                    flash('Invalid audio URL. Please provide a URL ending with an audio file extension (mp3, wav, m4a, aac, ogg)')
            else:
                flash('Please either upload a file or provide an audio URL')
    
    return render_template('index.html', message=message, srt_file_path=srt_file_path, word_srt_file_path=word_srt_file_path, segments_file_path=segments_file_path, background_images=background_images, selected_background=selected_background)

@app.route('/api/transcribe', methods=['POST'])
def api_transcribe():
    """API endpoint for transcription"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        audio_url = data.get('audio_url', '').strip()
        if not audio_url:
            return jsonify({'error': 'audio_url is required'}), 400
        
        if not is_valid_audio_url(audio_url):
            return jsonify({'error': 'Invalid audio URL format'}), 400
        
        # Download and transcribe
        filename, filepath = download_audio_file(audio_url)
        sentence_segments, word_segments = transcribe_audio(filepath)
        
        # Create sentence-based SRT file
        srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
        srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        
        # Create word-based SRT file
        word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
        word_srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        
        # Create audio segments with visual content
        audio_segments = create_audio_segments(sentence_segments, 15)
        segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
        segments_filepath = os.path.join(app.config['SEGMENTS_FOLDER'], segments_filename)
        create_segments_file(audio_segments, segments_filepath)
        
        return jsonify({
            'success': True,
            'sentence_file': srt_filename,
            'word_file': word_srt_filename,
            'segments_file': segments_filename,
            'sentence_segments': sentence_segments,
            'word_segments': word_segments,
            'audio_segments': audio_segments,
            'sentence_download_url': f'/download/{srt_filename}',
            'word_download_url': f'/download/{word_srt_filename}',
            'segments_download_url': f'/download/{segments_filename}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model': 'whisper-base',
        'supported_formats': list(ALLOWED_EXTENSIONS),
        'output_types': ['sentences', 'words', 'segments'],
        'openai_configured': os.getenv('OPENAI_API_KEY') is not None and os.getenv('OPENAI_API_KEY') != 'your_openai_api_key_here'
    })

@app.route('/download/<filename>')
def download_srt(filename):
    """Download SRT or markdown files"""
    try:
        # Check if it's a markdown file
        if filename.endswith('.md'):
            file_path = os.path.join(app.config['SEGMENTS_FOLDER'], filename)
        else:
            file_path = os.path.join(app.config['TRANSCRIPTS_FOLDER'], filename)
        
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            flash('File not found')
            return redirect('/')
    except Exception as e:
        flash(f'Error downloading file: {str(e)}')
        return redirect('/')

@app.route('/download_markdown/<filename>')
def download_markdown(filename):
    """Download markdown files specifically"""
    try:
        file_path = os.path.join(app.config['SEGMENTS_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, mimetype='text/markdown')
        else:
            flash('Markdown file not found')
            return redirect('/')
    except Exception as e:
        flash(f'Error downloading markdown file: {str(e)}')
        return redirect('/')

@app.route('/generate_video/<filename>')
def generate_video(filename):
    """Generate video from processed audio files"""
    try:
        from flask import request
        show_subtitles = request.args.get('show_subtitles', '1') == '1'
        selected_background = request.args.get('background')
        # Extract base filename without extension
        base_name = filename.rsplit('_segments.json', 1)[0]
        # Construct file paths
        segments_file = os.path.join(app.config['SEGMENTS_FOLDER'], filename)
        word_srt_file = os.path.join(app.config['TRANSCRIPTS_FOLDER'], f"{base_name}_words.srt")
        audio_file = None
        # Find the original audio file
        for ext in ['mp3', 'wav', 'm4a', 'aac', 'ogg']:
            potential_audio = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}.{ext}")
            if os.path.exists(potential_audio):
                audio_file = potential_audio
                break
        if not audio_file:
            flash('Original audio file not found')
            return redirect('/')
        if not os.path.exists(segments_file):
            flash('Segments file not found')
            return redirect('/')
        if not os.path.exists(word_srt_file):
            flash('Word-level SRT file not found')
            return redirect('/')
        
        # Run Ideogram image generation first
        print("Running Ideogram image generation...")
        try:
            import subprocess
            result = subprocess.run(['venv/bin/python', 'generate_images_ideogram.py'], 
                                 capture_output=True, text=True, check=True)
            print("Ideogram image generation completed successfully")
            print(f"Script output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Ideogram image generation failed: {e}")
            print(f"Script stderr: {e.stderr}")
            # Continue without generated images if script fails
        except Exception as e:
            print(f"Warning: Could not run Ideogram image generation: {e}")
            # Continue without generated images if script fails
        
        # Run highlight script to add highlight tags to presentation.md
        print("Running highlight script to add highlight tags...")
        try:
            import subprocess
            result = subprocess.run(['python3', 'gpt_highlight_bullets.py'], 
                                 capture_output=True, text=True, check=True)
            print("Highlight script completed successfully")
            print(f"Script output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Highlight script failed: {e}")
            print(f"Script stderr: {e.stderr}")
            # Continue without highlights if script fails
        except Exception as e:
            print(f"Warning: Could not run highlight script: {e}")
            # Continue without highlights if script fails
        
        # Initialize video generator
        video_gen = VideoGenerator(
            segments_folder=app.config['SEGMENTS_FOLDER'],
            transcripts_folder=app.config['TRANSCRIPTS_FOLDER'],
            font_folder='circular-std-font-family'
        )
        # Generate video
        output_video = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_video.mp4")
        print(f"Starting video generation for {filename}...")
        video_gen.generate_video(segments_file, word_srt_file, audio_file, output_video, show_subtitles=show_subtitles, selected_background=selected_background)
        flash(f'Video generated successfully: {os.path.basename(output_video)}')
        return redirect('/')
    except Exception as e:
        flash(f'Error generating video: {str(e)}')
        return redirect('/')

@app.route('/process_and_generate_video', methods=['POST'])
def process_and_generate_video():
    """Process audio and generate video in one step"""
    try:
        # Get form data
        audio_file = request.files.get('audio_file')
        audio_url = request.form.get('audio_url', '').strip()
        video_name = request.form.get('video_name', '').strip()
        show_subtitles = request.form.get('show_subtitles', 'true').lower() == 'true'
        selected_background = request.form.get('selected_background', '')
        
        # Validate inputs
        if not audio_file and not audio_url:
            return jsonify({'error': 'Please provide either an audio file or audio URL'}), 400
        
        if not video_name:
            return jsonify({'error': 'Video name is required'}), 400
        
        # Sanitize video name
        import re
        video_name = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
        if not video_name:
            return jsonify({'error': 'Invalid video name'}), 400
        
        print(f"[COMBINED API] Starting combined process for video: {video_name}")
        
        # Step 1: Process audio (transcribe and create segments)
        if audio_file:
            # Save uploaded file
            filename = audio_file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            audio_file.save(filepath)
            print(f"[COMBINED API] Saved uploaded file: {filepath}")
        else:
            # Download from URL
            filename, filepath = download_audio_file(audio_url)
            print(f"[COMBINED API] Downloaded file: {filepath}")
        
        # Transcribe audio
        print(f"[COMBINED API] Transcribing audio...")
        sentence_segments, word_segments = transcribe_audio(filepath)
        
        # Create SRT files
        srt_filename = f"{filename.rsplit('.', 1)[0]}_sentences.srt"
        srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], srt_filename)
        create_srt_file(sentence_segments, srt_filepath)
        
        word_srt_filename = f"{filename.rsplit('.', 1)[0]}_words.srt"
        word_srt_filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], word_srt_filename)
        create_word_srt_file(word_segments, word_srt_filepath)
        
        # Create segments file
        audio_segments = create_audio_segments(sentence_segments, 15)
        segments_filename = f"{filename.rsplit('.', 1)[0]}_segments.json"
        segments_filepath = os.path.join(app.config['SEGMENTS_FOLDER'], segments_filename)
        create_segments_file(audio_segments, segments_filepath)
        
        print(f"[COMBINED API] Audio processing completed")
        
        # Step 2: Generate images
        print(f"[COMBINED API] Generating images with optimized parallel processing...")
        try:
            import subprocess
            result = subprocess.run(['venv/bin/python', 'generate_images_ideogram_optimized.py'], 
                                 capture_output=True, text=True, check=True)
            print(f"[COMBINED API] Image generation completed with optimization")
        except Exception as e:
            print(f"[COMBINED API] Image generation failed: {e}")
            # Continue without images
        
        # Step 3: Add highlights
        print(f"[COMBINED API] Adding highlights...")
        try:
            import subprocess
            result = subprocess.run(['python3', 'gpt_highlight_bullets.py'], 
                                 capture_output=True, text=True, check=True)
            print(f"[COMBINED API] Highlights added")
        except Exception as e:
            print(f"[COMBINED API] Highlight script failed: {e}")
            # Continue without highlights
        
        # Step 4: Generate video
        print(f"[COMBINED API] Generating video...")
        
        # Select background
        if not selected_background:
            bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
            selected_bg = random.choice(bg_files) if bg_files else None
        else:
            selected_bg = selected_background
            if not os.path.exists(os.path.join('background', selected_bg)):
                bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
                selected_bg = random.choice(bg_files) if bg_files else None
        
        # Initialize video generator
        video_gen = VideoGenerator(
            segments_folder=app.config['SEGMENTS_FOLDER'],
            transcripts_folder=app.config['TRANSCRIPTS_FOLDER'],
            font_folder='circular-std-font-family'
        )
        
        # Generate video with custom name
        output_video = os.path.join(app.config['UPLOAD_FOLDER'], f"{video_name}.mp4")
        video_gen.generate_video(segments_filepath, word_srt_filepath, filepath, output_video, 
                               show_subtitles=show_subtitles, selected_background=selected_bg)
        
        print(f"[COMBINED API] Video generated successfully: {output_video}")
        
        return jsonify({
            'success': True,
            'video_filename': os.path.basename(output_video),
            'message': 'Complete video generated successfully'
        })
        
    except Exception as e:
        print(f"[COMBINED API ERROR] Process failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate_video_api', methods=['POST'])
def generate_video_api():
    """Generate video using the last processed audio file and its presentation.md"""
    try:
        data = request.get_json()
        video_name = data.get('video_name', '').strip()
        show_subtitles = data.get('show_subtitles', True)
        selected_background = data.get('selected_background', '')
        
        # Validate video name
        if not video_name:
            return jsonify({'error': 'Video name is required'}), 400
        
        # Sanitize video name (remove special characters, allow only alphanumeric and underscores)
        import re
        video_name = re.sub(r'[^a-zA-Z0-9_]', '_', video_name)
        if not video_name:
            return jsonify({'error': 'Invalid video name'}), 400
        
        # Find the most recent segments file
        segments_files = glob.glob(os.path.join(app.config['SEGMENTS_FOLDER'], '*_segments.json'))
        if not segments_files:
            return jsonify({'error': 'No processed audio files found. Please process an audio file first.'}), 400
        
        # Get the most recent segments file
        segments_file = max(segments_files, key=os.path.getctime)
        base_name = os.path.basename(segments_file).replace('_segments.json', '')
        
        print(f"[API DEBUG] Using segments file: {segments_file}")
        print(f"[API DEBUG] Base name: {base_name}")
        
        # Find corresponding files
        word_srt_file = os.path.join(app.config['TRANSCRIPTS_FOLDER'], f"{base_name}_words.srt")
        slides_file = os.path.join(app.config['SEGMENTS_FOLDER'], 'slides.json')
        
        # Check if required files exist
        if not os.path.exists(word_srt_file):
            return jsonify({'error': f'Word SRT file not found: {word_srt_file}'}), 400
        if not os.path.exists(slides_file):
            return jsonify({'error': f'Slides file not found: {slides_file}'}), 400
        
        # Find the original audio file
        audio_file = None
        for ext in ['mp3', 'wav', 'm4a', 'aac', 'ogg']:
            potential_audio = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}.{ext}")
            if os.path.exists(potential_audio):
                audio_file = potential_audio
                break
        
        if not audio_file:
            return jsonify({'error': f'Original audio file not found for: {base_name}'}), 400
        
        print(f"[API DEBUG] Using audio file: {audio_file}")
        
        # Select background
        if not selected_background:
            bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
            selected_bg = random.choice(bg_files) if bg_files else None
        else:
            selected_bg = selected_background
            if not os.path.exists(os.path.join('background', selected_bg)):
                print(f"[API WARN] Background {selected_bg} not found, using random.")
                bg_files = [f for f in os.listdir('background') if f.lower().endswith(('.jpg', '.png'))]
                selected_bg = random.choice(bg_files) if bg_files else None
        
        print(f"[API DEBUG] Using background: {selected_bg}")
        
        # Run Ideogram image generation first
        print("[API DEBUG] Running optimized Ideogram image generation...")
        try:
            import subprocess
            result = subprocess.run(['venv/bin/python', 'generate_images_ideogram_optimized.py'], 
                                 capture_output=True, text=True, check=True)
            print("[API DEBUG] Optimized Ideogram image generation completed successfully")
            print(f"[API DEBUG] Script output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            print(f"[API WARN] Optimized Ideogram image generation failed: {e}")
            print(f"[API WARN] Script stderr: {e.stderr}")
            # Continue without generated images if script fails
        except Exception as e:
            print(f"[API WARN] Could not run optimized Ideogram image generation: {e}")
            # Continue without generated images if script fails
        
        # Run highlight script to add highlight tags to presentation.md
        print("[API DEBUG] Running highlight script to add highlight tags...")
        try:
            import subprocess
            result = subprocess.run(['python3', 'gpt_highlight_bullets.py'], 
                                 capture_output=True, text=True, check=True)
            print("[API DEBUG] Highlight script completed successfully")
            print(f"[API DEBUG] Script output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            print(f"[API WARN] Highlight script failed: {e}")
            print(f"[API WARN] Script stderr: {e.stderr}")
            # Continue without highlights if script fails
        except Exception as e:
            print(f"[API WARN] Could not run highlight script: {e}")
            # Continue without highlights if script fails
        
        # Generate video
        video_gen = VideoGenerator(
            segments_folder=app.config['SEGMENTS_FOLDER'],
            transcripts_folder=app.config['TRANSCRIPTS_FOLDER'],
            font_folder='circular-std-font-family'
        )
        
        output_video = os.path.join(app.config['UPLOAD_FOLDER'], f"{video_name}.mp4")
        print(f"[API DEBUG] Generating video with custom name: {video_name}")
        video_gen.generate_video(segments_file, word_srt_file, audio_file, output_video, show_subtitles=show_subtitles, selected_background=selected_bg)
        print(f"[API DEBUG] Video generated: {output_video}")
        
        return jsonify({
            'success': True,
            'video_filename': os.path.basename(output_video),
            'message': 'Video generated successfully'
        })
        
    except Exception as e:
        print(f"[API ERROR] Video generation failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/download_video/<filename>')
def download_video(filename):
    """Download generated video file"""
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, mimetype='video/mp4')
        else:
            flash('Video file not found')
            return redirect('/')
    except Exception as e:
        flash(f'Error downloading video: {str(e)}')
        return redirect('/')

if __name__ == '__main__':
    # app.run(debug=True) 
    app.run(host="0.0.0.0", port=5001) 