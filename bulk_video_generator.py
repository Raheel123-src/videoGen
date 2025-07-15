#!/usr/bin/env python3

import csv
import os
import requests
import time
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
import re
import platform

class BulkVideoGenerator:
    def __init__(self, csv_file_path, background_image="1.jpg"):
        self.csv_file_path = csv_file_path
        self.background_image = background_image
        self.base_upload_dir = "uploads"
        self.course_dir = os.path.join(self.base_upload_dir, "Course")
        
        # Create necessary directories
        os.makedirs(self.course_dir, exist_ok=True)
        os.makedirs("segments", exist_ok=True)
        os.makedirs("transcripts", exist_ok=True)
        
        # Import app functions
        sys.path.append('.')
        from app import (
            download_audio_file, transcribe_audio, create_srt_file, 
            create_word_srt_file, create_audio_segments, create_segments_file,
            VideoGenerator
        )
        
        self.download_audio_file = download_audio_file
        self.transcribe_audio = transcribe_audio
        self.create_srt_file = create_srt_file
        self.create_word_srt_file = create_word_srt_file
        self.create_audio_segments = create_audio_segments
        self.create_segments_file = create_segments_file
        self.VideoGenerator = VideoGenerator
    
    def play_beep(self):
        """Play a beep sound to indicate video completion"""
        try:
            system = platform.system()
            if system == "Darwin":  # macOS
                os.system('afplay /System/Library/Sounds/Glass.aiff')
            elif system == "Linux":
                os.system('paplay /usr/share/sounds/freedesktop/stereo/complete.oga')
            elif system == "Windows":
                os.system('powershell.exe [console]::beep(800,500)')
            else:
                # Fallback: print bell character
                print('\a')
        except Exception as e:
            # Silent fallback if beep fails
            pass
    
    def sanitize_filename(self, filename):
        """Sanitize filename for safe file system usage"""
        # Remove or replace invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip('. ')
        # Limit length
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        return sanitized
    
    def download_and_process_audio(self, audio_url, course_name, topic_name):
        """Download audio file and process it"""
        try:
            print(f"📥 Downloading audio from: {audio_url}")
            
            # Download the audio file
            filename, filepath = self.download_audio_file(audio_url)
            print(f"✅ Downloaded: {filename}")
            
            # Transcribe audio
            print(f"🎤 Transcribing audio...")
            sentence_segments, word_segments = self.transcribe_audio(filepath)
            print(f"✅ Transcription completed")
            
            # Create SRT files
            base_name = filename.rsplit('.', 1)[0]
            
            # Create sentence-based SRT file
            srt_filename = f"{base_name}_sentences.srt"
            srt_filepath = os.path.join("transcripts", srt_filename)
            self.create_srt_file(sentence_segments, srt_filepath)
            
            # Create word-based SRT file
            word_srt_filename = f"{base_name}_words.srt"
            word_srt_filepath = os.path.join("transcripts", word_srt_filename)
            self.create_word_srt_file(word_segments, word_srt_filepath)
            
            # Create segments file
            audio_segments = self.create_audio_segments(sentence_segments, 15)
            segments_filename = f"{base_name}_segments.json"
            segments_filepath = os.path.join("segments", segments_filename)
            self.create_segments_file(audio_segments, segments_filepath)
            
            print(f"✅ Audio processing completed")
            return {
                'filename': filename,
                'filepath': filepath,
                'srt_filepath': srt_filepath,
                'word_srt_filepath': word_srt_filepath,
                'segments_filepath': segments_filepath
            }
            
        except Exception as e:
            print(f"❌ Error processing audio: {e}")
            raise
    
    def generate_images(self):
        """Generate images using optimized Ideogram script"""
        try:
            print(f"🎨 Generating images with optimized parallel processing...")
            result = subprocess.run(['venv/bin/python', 'generate_images_ideogram_optimized.py'], 
                                 capture_output=True, text=True, check=True)
            print(f"✅ Images generated successfully with optimization")
            return True
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Image generation failed: {e}")
            return False
        except Exception as e:
            print(f"⚠️ Image generation error: {e}")
            return False
    
    def add_highlights(self):
        """Add highlight tags to slides"""
        try:
            print(f"✨ Adding highlights...")
            result = subprocess.run(['python3', 'gpt_highlight_bullets.py'], 
                                 capture_output=True, text=True, check=True)
            print(f"✅ Highlights added successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Highlight script failed: {e}")
            return False
        except Exception as e:
            print(f"⚠️ Highlight error: {e}")
            return False
    
    def generate_video(self, audio_data, course_name, topic_name):
        """Generate video with the processed audio data"""
        try:
            print(f"🎬 Generating video for: {topic_name}")
            
            # Initialize video generator
            video_gen = self.VideoGenerator(
                segments_folder="segments",
                transcripts_folder="transcripts",
                font_folder='circular-std-font-family'
            )
            
            # Create course directory
            course_dir = os.path.join(self.course_dir, self.sanitize_filename(course_name))
            os.makedirs(course_dir, exist_ok=True)
            
            # Create video filename
            video_filename = f"{self.sanitize_filename(topic_name)}.mp4"
            output_video = os.path.join(course_dir, video_filename)
            
            # Generate video
            video_gen.generate_video(
                audio_data['segments_filepath'],
                audio_data['word_srt_filepath'],
                audio_data['filepath'],
                output_video,
                show_subtitles=True,
                selected_background=self.background_image
            )
            
            print(f"✅ Video generated: {output_video}")
            return output_video
            
        except Exception as e:
            print(f"❌ Error generating video: {e}")
            raise
    
    def update_csv_status(self, row_index, status="Done"):
        """Update the CSV file with completion status"""
        try:
            # Read the CSV file
            rows = []
            with open(self.csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                rows = list(reader)
            
            # Update the status column (4th column, index 3)
            if row_index < len(rows):
                rows[row_index][3] = status
            
            # Write back to CSV
            with open(self.csv_file_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerows(rows)
            
            print(f"✅ Updated CSV status for row {row_index + 1}")
            
        except Exception as e:
            print(f"⚠️ Error updating CSV: {e}")
    
    def process_csv(self):
        """Process the entire CSV file"""
        try:
            print(f"🚀 Starting bulk video generation from: {self.csv_file_path}")
            print(f"📁 Videos will be saved to: {self.course_dir}")
            print(f"🖼️ Using background: {self.background_image}")
            print("=" * 60)
            
            # Read CSV file
            with open(self.csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                rows = list(reader)
            
            total_rows = len(rows)
            print(f"📊 Found {total_rows} videos to process")
            
            for i, row in enumerate(rows):
                if i == 0:  # Skip header row
                    continue
                
                try:
                    course_name = row[0].strip()
                    topic_name = row[1].strip()
                    audio_url = row[2].strip()
                    current_status = row[3].strip() if len(row) > 3 else ""
                    
                    # Skip if already done
                    if current_status.lower() == "done":
                        print(f"⏭️ Skipping {topic_name} (already done)")
                        continue
                    
                    print(f"\n🎯 Processing {i}/{total_rows-1}: {course_name} - {topic_name}")
                    print("-" * 50)
                    
                    # Step 1: Download and process audio
                    audio_data = self.download_and_process_audio(audio_url, course_name, topic_name)
                    
                    # Step 2: Generate images
                    self.generate_images()
                    
                    # Step 3: Add highlights
                    self.add_highlights()
                    
                    # Step 4: Generate video
                    video_path = self.generate_video(audio_data, course_name, topic_name)
                    
                    # Step 5: Update CSV status
                    self.update_csv_status(i, "Done")
                    
                    print(f"✅ Completed: {topic_name}")
                    print(f"📁 Video saved: {video_path}")
                    
                    # Play beep sound to indicate completion
                    self.play_beep()
                    
                    # Add delay between processing to avoid overwhelming the system
                    time.sleep(1)  # Reduced delay since we're optimizing
                    
                except Exception as e:
                    print(f"❌ Error processing row {i}: {e}")
                    # Update CSV with error status
                    self.update_csv_status(i, f"Error: {str(e)[:50]}")
                    continue
            
            print(f"\n🎉 Bulk video generation completed!")
            print(f"📁 Check the Course folder for generated videos")
            
        except Exception as e:
            print(f"❌ Error processing CSV: {e}")

def main():
    # Check if background image exists
    background_image = "1.jpg"
    if not os.path.exists(os.path.join("background", background_image)):
        print(f"❌ Background image not found: background/{background_image}")
        print("Please ensure 1.jpg exists in the background folder")
        return
    
    # Find CSV files in bulk_csv folder
    csv_folder = "bulk_csv"
    if not os.path.exists(csv_folder):
        print(f"❌ CSV folder not found: {csv_folder}")
        return
    
    csv_files = [f for f in os.listdir(csv_folder) if f.endswith('.csv')]
    
    if not csv_files:
        print(f"❌ No CSV files found in {csv_folder}")
        return
    
    print(f"📁 Found CSV files: {csv_files}")
    
    for csv_file in csv_files:
        csv_path = os.path.join(csv_folder, csv_file)
        print(f"\n🎬 Processing: {csv_file}")
        
        # Create bulk generator
        generator = BulkVideoGenerator(csv_path, background_image)
        
        # Process the CSV
        generator.process_csv()
        
        print(f"✅ Completed processing: {csv_file}")

if __name__ == "__main__":
    main() 