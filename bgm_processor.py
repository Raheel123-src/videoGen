import os
import json
import random
import requests
import re
from typing import List, Dict, Tuple, Optional
from pydub import AudioSegment
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class BGMProcessor:
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.bgm_base_path = "BGM"
        self.theme_folders = {
            "Hook": "Start HOOK",
            "What": "WHAT", 
            "Why": "WHY",  # Fixed: removed trailing space
            "How": "HOW",
            "Ending Hook": "End HOOK"
        }
        
    def parse_srt_to_segments(self, srt_file_path: str) -> List[Dict]:
        """
        Parse SRT file and convert to segments format
        """
        segments = []
        
        with open(srt_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Split by double newlines to get individual subtitle blocks
        subtitle_blocks = content.strip().split('\n\n')
        
        for block in subtitle_blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                # Skip the subtitle number (first line)
                time_line = lines[1]
                text = ' '.join(lines[2:])
                
                # Parse time format: 00:00:00,000 --> 00:00:00,000
                time_match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
                if time_match:
                    start_h, start_m, start_s, start_ms = map(int, time_match.groups()[:4])
                    end_h, end_m, end_s, end_ms = map(int, time_match.groups()[4:])
                    
                    start_time = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
                    end_time = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000
                    
                    segments.append({
                        'start': start_time,
                        'end': end_time,
                        'text': text
                    })
        
        return segments

    def analyze_content_themes(self, transcription_segments: List[Dict], slides_data: List[Dict]) -> List[Dict]:
        """
        Analyze transcription and slides to categorize content into 5 themes using GPT
        """
        # Prepare the data for GPT analysis
        transcription_text = ""
        for segment in transcription_segments:
            start_time = segment.get('start', 0)
            end_time = segment.get('end', 0)
            text = segment.get('text', '')
            transcription_text += f"[{start_time:.1f}-{end_time:.1f}] {text}\n"
        
        slides_text = ""
        for slide in slides_data:
            slide_num = slide.get('slide_number', 0)
            title = slide.get('title', '')
            bullets = slide.get('bullets', [])
            slides_text += f"Slide {slide_num}: {title}\n"
            for bullet in bullets:
                slides_text += f"  - {bullet}\n"
        
        # Calculate total duration from transcription
        total_duration = max(segment.get('end', 0) for segment in transcription_segments) if transcription_segments else 0
        
        prompt = f"""
You are an expert at analyzing transcripts and categorizing content into 5 specific themes. Given a list of segments with start/end times and text, along with slide content, group consecutive segments into these 5 categories:

1. **Hook** - Introduction, attention-grabbing content, opening statements
2. **What** - Definition, explanation of what something is, description of concepts
3. **Why** - Reasons, motivations, benefits, importance, purpose
4. **How** - Methods, processes, steps, implementation, practical application
5. **Ending Hook** - Conclusion, call-to-action, final thoughts, closing statements

**IMPORTANT**: 
- Consider both the transcript content AND the slide content when categorizing
- The total duration is {total_duration:.1f} seconds
- You MUST cover the ENTIRE duration with exactly 5 theme categories
- Each theme should have a reasonable duration (not 0 seconds)
- Distribute themes evenly across the content

Return a JSON array of groups, each with:
- start: start time in seconds
- end: end time in seconds  
- theme: one of "Hook", "What", "Why", "How", "Ending Hook"

**Transcription Segments:**
{transcription_text}

**Slides Content:**
{slides_text}

Return only the JSON array with exactly 5 theme categories covering the entire {total_duration:.1f} seconds.
"""
        
        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a transcript analysis expert. Always return valid JSON with exactly 5 theme categories: Hook, What, Why, How, Ending Hook. Each theme must have a duration > 0 seconds."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.2,
            max_tokens=800
        )
        
        try:
            result = response.choices[0].message.content.strip()
            # Clean up the response to extract JSON
            if result.startswith('```json'):
                result = result[7:]
            if result.endswith('```'):
                result = result[:-3]
            
            theme_groups = json.loads(result)
            print(f"[BGM] GPT Analysis Result: {theme_groups}")
            return theme_groups
            
        except Exception as e:
            print(f"[BGM] Error parsing GPT response: {e}")
            print(f"[BGM] Raw response: {response.choices[0].message.content}")
            raise
    
    def get_bgm_for_slide(self, slide_number: int, segments_data: List[Dict]) -> Optional[str]:
        """
        Get BGM file for a specific slide based on its content and position
        """
        if slide_number >= len(segments_data):
            return None
            
        segment = segments_data[slide_number]
        text = segment.get('text', '').lower()
        
        # Determine theme based on content keywords or position
        if slide_number == 0:
            return self.get_random_bgm_file("Hook")
        elif slide_number == len(segments_data) - 1:
            return self.get_random_bgm_file("Ending Hook")
        elif any(keyword in text for keyword in ['what', 'introduction', 'start', 'begin']):
            return self.get_random_bgm_file("What")
        elif any(keyword in text for keyword in ['why', 'reason', 'cause', 'because']):
            return self.get_random_bgm_file("Why")
        elif any(keyword in text for keyword in ['how', 'process', 'method', 'way', 'steps']):
            return self.get_random_bgm_file("How")
        else:
            # Default based on position
            if slide_number < len(segments_data) * 0.2:
                return self.get_random_bgm_file("Hook")
            elif slide_number < len(segments_data) * 0.4:
                return self.get_random_bgm_file("What")
            elif slide_number < len(segments_data) * 0.6:
                return self.get_random_bgm_file("Why")
            elif slide_number < len(segments_data) * 0.8:
                return self.get_random_bgm_file("How")
            else:
                return self.get_random_bgm_file("Ending Hook")

    def get_random_bgm_file(self, theme: str) -> str:
        """
        Get a random BGM file from the specified theme folder
        """
        folder_name = self.theme_folders.get(theme)
        if not folder_name:
            print(f"[BGM] Unknown theme: {theme}")
            return None
            
        folder_path = os.path.join(self.bgm_base_path, folder_name)
        if not os.path.exists(folder_path):
            print(f"[BGM] BGM folder not found: {folder_path}")
            return None
            
        # Get all MP3 files in the folder
        mp3_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.mp3')]
        if not mp3_files:
            print(f"[BGM] No MP3 files found in {folder_path}")
            return None
            
        # Randomly select one
        selected_file = random.choice(mp3_files)
        bgm_path = os.path.join(folder_path, selected_file)
        print(f"[BGM] Selected BGM for {theme}: {selected_file}")
        return bgm_path
    
    def overlay_bgm_on_audio(self, original_audio_path: str, segments_data: List[Dict], transcription_segments: List[Dict], bgm_volume: int = 50, crossfade_duration: int = 2000) -> str:
        """
        Overlay BGM tracks on the original audio based on segment transitions with smooth crossfades
        """
        print(f"[BGM] Starting BGM overlay with volume: {bgm_volume}, crossfade: {crossfade_duration/1000:.1f}s")
        
        # Load original audio
        original_audio = AudioSegment.from_file(original_audio_path)
        total_duration = len(original_audio)
        print(f"[BGM] Original audio duration: {total_duration/1000:.1f} seconds")
        
        # Create a silent audio segment for BGM overlay
        bgm_overlay = AudioSegment.silent(duration=total_duration)
        
        # Apply BGM for each segment with crossfades
        for segment_idx, segment in enumerate(segments_data):
            start_time = segment.get('start_time', 0) * 1000  # Convert to milliseconds
            end_time = segment.get('end_time', 0) * 1000
            
            # Get BGM file for this segment
            bgm_file = self.get_bgm_for_slide(segment_idx, segments_data)
            if not bgm_file:
                print(f"[BGM] Skipping BGM for segment {segment_idx} - no file available")
                continue
                
            try:
                # Load BGM audio
                bgm_audio = AudioSegment.from_file(bgm_file)
                print(f"[BGM] Loaded BGM file: {bgm_file}, duration: {len(bgm_audio)/1000:.1f}s")
                
                # Calculate the duration for this segment
                segment_duration = end_time - start_time
                
                # Loop or trim BGM to match segment duration
                if len(bgm_audio) < segment_duration:
                    # Loop the BGM to fill the duration
                    loops_needed = int(segment_duration / len(bgm_audio)) + 1
                    bgm_audio = bgm_audio * loops_needed
                    print(f"[BGM] Looped BGM {loops_needed} times to fill {segment_duration/1000:.1f}s")
                
                # Trim to exact duration
                bgm_audio = bgm_audio[:segment_duration]
                
                # Adjust volume (bgm_volume is 1-100)
                # Convert to dB: 100 = 0dB (full volume), 1 = -50dB (very quiet)
                # Formula: volume_db = (bgm_volume - 100) * 0.5
                volume_db = (bgm_volume - 100) * 0.5
                bgm_audio = bgm_audio + volume_db
                print(f"[BGM] Adjusted BGM volume to {volume_db:.1f}dB (volume setting: {bgm_volume})")
                
                # Apply crossfade if this isn't the first segment
                if segment_idx > 0:
                    # Calculate crossfade start and end points
                    crossfade_start = start_time - crossfade_duration
                    crossfade_end = start_time + crossfade_duration
                    
                    # Ensure crossfade doesn't go before 0
                    if crossfade_start < 0:
                        crossfade_start = 0
                    
                    # Create crossfade region
                    crossfade_region_start = max(0, crossfade_duration - (start_time - crossfade_start))
                    crossfade_region_end = min(crossfade_duration, crossfade_duration + (start_time - crossfade_start))
                    
                    # Apply crossfade
                    if crossfade_region_end > crossfade_region_start:
                        # Fade out the previous BGM in the crossfade region
                        fade_out_region = bgm_overlay[crossfade_start:start_time]
                        if len(fade_out_region) > 0:
                            fade_out_region = fade_out_region.fade_out(len(fade_out_region))
                            bgm_overlay = bgm_overlay.overlay(fade_out_region, position=crossfade_start)
                        
                        # Fade in the current BGM in the crossfade region
                        fade_in_region = bgm_audio[:crossfade_region_end]
                        if len(fade_in_region) > 0:
                            fade_in_region = fade_in_region.fade_in(len(fade_in_region))
                            bgm_overlay = bgm_overlay.overlay(fade_in_region, position=crossfade_start)
                        
                        # Add the rest of the current BGM (after crossfade)
                        if crossfade_region_end < len(bgm_audio):
                            remaining_bgm = bgm_audio[crossfade_region_end:]
                            bgm_overlay = bgm_overlay.overlay(remaining_bgm, position=start_time)
                        
                        print(f"[BGM] Applied crossfade for segment {segment_idx} from {crossfade_start/1000:.1f}s to {crossfade_end/1000:.1f}s")
                    else:
                        # No crossfade needed, just overlay normally
                        bgm_overlay = bgm_overlay.overlay(bgm_audio, position=start_time)
                else:
                    # First segment - no crossfade needed
                    bgm_overlay = bgm_overlay.overlay(bgm_audio, position=start_time)
                
                print(f"[BGM] Added BGM for segment {segment_idx} from {start_time/1000:.1f}s to {end_time/1000:.1f}s")
                
            except Exception as e:
                print(f"[BGM] Error processing BGM for segment {segment_idx}: {e}")
                continue
        
        # Mix original audio with BGM overlay
        print(f"[BGM] Mixing original audio with BGM overlay...")
        final_audio = original_audio.overlay(bgm_overlay)
        
        # Save the result
        original_dir = os.path.dirname(original_audio_path)
        original_filename = os.path.basename(original_audio_path)
        name_without_ext = os.path.splitext(original_filename)[0]
        output_filename = f"{name_without_ext}_bgm.mp3"
        output_path = os.path.join(original_dir, output_filename)
        
        # Ensure directory exists
        os.makedirs(original_dir, exist_ok=True)
        
        # Export as MP3
        final_audio.export(output_path, format="mp3")
        print(f"[BGM] BGM overlay completed: {output_path}")
        print(f"[BGM] Final audio duration: {len(final_audio)/1000:.1f} seconds")
        
        return output_path

    def process_audio_with_bgm(self, original_audio_path: str, transcription_file: str, segments_json_path: str, bgm_volume: int = 50, crossfade_duration: int = 2000) -> str:
        """
        Main function to process audio with BGM overlay
        """
        print("[BGM] Starting BGM processing...")
        
        # Load segments data
        with open(segments_json_path, 'r') as f:
            segments_data = json.load(f)['segments']
        print(f"[BGM] Loaded {len(segments_data)} segments from segments.json")
        
        # Load transcription segments
        if transcription_file.endswith('.srt'):
            transcription_segments = self.parse_srt_to_segments(transcription_file)
        else:
            with open(transcription_file, 'r') as f:
                transcription_data = json.load(f)
                transcription_segments = transcription_data.get('segments', [])
        
        print(f"[BGM] Loaded {len(transcription_segments)} transcription segments")
        
        # Overlay BGM
        return self.overlay_bgm_on_audio(original_audio_path, segments_data, transcription_segments, bgm_volume, crossfade_duration)

# Example usage
if __name__ == "__main__":
    # Test files
    audio_file = "uploads/BGMandNEW_IMG_TEST_7100ee52/audio_88cc77083e7145919880101de64df34e.mp3"
    transcription_file = "/Users/raheel/Desktop/Lisa/VIDTEST2/videoGen/transcripts/BGMandNEW_IMG_TEST_7100ee52/audio_88cc77083e7145919880101de64df34e_sentences.srt"
    segments_file = "segments/BGMandNEW_IMG_TEST_7100ee52/audio_88cc77083e7145919880101de64df34e_segments.json"
    
    # Process audio with BGM
    processor = BGMProcessor()
    
    # Crossfade options:
    # - 1000ms (1s): Quick transitions
    # - 2000ms (2s): Smooth transitions (default)
    # - 3000ms (3s): Very smooth transitions
    # - 0ms: No crossfade (abrupt transitions)
    
    output_path = processor.process_audio_with_bgm(
        audio_file, 
        transcription_file, 
        segments_file, 
        bgm_volume=50,  # 1-100 scale
        crossfade_duration=2000  # 2 seconds crossfade
    )
    print(f"✅ BGM processing completed: {output_path}")
    print(f"📁 Processed audio saved in same directory as original with '_bgm' suffix") 