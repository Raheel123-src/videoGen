import os
import json
import shutil
from PIL import Image, ImageDraw, ImageFont
import re
import math
from datetime import timedelta
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, TextClip, concatenate_videoclips, VideoClip
from moviepy.video.fx.all import resize
import numpy as np
import random
from glob import glob
import sys

# Utility: always flush stdout after print

def print_flush(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

class VideoGenerator:
    def __init__(self, segments_folder, transcripts_folder, font_folder):
        self.segments_folder = segments_folder
        self.transcripts_folder = transcripts_folder
        self.font_folder = font_folder
        self.font_path = os.path.join(font_folder, "CircularStd-Book.ttf")
        self.bold_font_path = os.path.join("circular-std-font-family", "CircularStd-Bold.ttf")
        
        # Video settings - optimized for CPU-only processing
        self.width = 1280  # Reduced from 1920 for CPU efficiency
        self.height = 720   # Reduced from 1080 for CPU efficiency
        self.fps = 24  # Reduced from 30 for speed
        self.background_color = (255, 255, 255)  # White
        self.text_color = (0, 0, 0)  # Black
        
        # Font sizes
        self.title_size = 72
        self.subtitle_size = 48
        self.body_size = 36
        self.subtitle_font_size = 42
        
        # Pre-load fonts for speed
        try:
            self.title_font = ImageFont.truetype(self.bold_font_path, self.title_size)
            self.subtitle_font = ImageFont.truetype(self.font_path, self.subtitle_size)
            self.body_font = ImageFont.truetype(self.font_path, self.body_size)
            self.subtitle_overlay_font = ImageFont.truetype(self.font_path, self.subtitle_font_size)
        except:
            self.title_font = ImageFont.load_default()
            self.subtitle_font = ImageFont.load_default()
            self.body_font = ImageFont.load_default()
            self.subtitle_overlay_font = ImageFont.load_default()
    
    def load_segments_data(self, segments_file):
        """Load segments data from JSON file"""
        with open(segments_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_word_segments(self, word_srt_file):
        """Load word-level timing from SRT file"""
        word_segments = []
        with open(word_srt_file, 'r', encoding='utf-8') as f:
            content = f.read()
            blocks = content.strip().split('\n\n')
            
            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    # Parse timing
                    timing = lines[1]
                    start_time, end_time = self.parse_srt_time(timing)
                    
                    # Parse text
                    text = ' '.join(lines[2:]).strip()
                    word_segments.append({
                        'start': start_time,
                        'end': end_time,
                        'text': text
                    })
        
        return word_segments
    
    def parse_srt_time(self, timing_str):
        """Parse SRT time format (HH:MM:SS,mmm) to seconds"""
        time_parts = timing_str.split(' --> ')
        start_str = time_parts[0]
        end_str = time_parts[1]
        
        def time_to_seconds(time_str):
            time_parts = time_str.replace(',', '.').split(':')
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            seconds = float(time_parts[2])
            return hours * 3600 + minutes * 60 + seconds
        
        return time_to_seconds(start_str), time_to_seconds(end_str)
    
    def parse_markdown_content(self, markdown_content):
        """Parse the markdown section for format, title, bullets, and image prompt. Returns clean bullets and highlight info."""
        import re
        elements = []
        lines = markdown_content.split('\n')
        title = None
        bullets = []
        highlights = []
        in_bullets = False
        format_type = None
        image_prompt = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('**Format**:'):
                try:
                    format_type = int(line.replace('**Format**:', '').strip())
                except:
                    format_type = None
                elements.append({'type': 'format', 'value': format_type})
            elif line.startswith('**Title**:'):
                title = line.replace('**Title**:', '').strip()
                elements.append({'type': 'title', 'text': title})
            elif line.startswith('**Slide Bullets**:'):
                in_bullets = True
            elif in_bullets and line.startswith('- '):
                bullet_text = line[2:].strip()
                # Extract highlight word and remove tags
                m = re.search(r'<highlight>(.+?)</highlight>', bullet_text)
                if m:
                    highlight_word = m.group(1)
                    clean_bullet = re.sub(r'<highlight>(.+?)</highlight>', highlight_word, bullet_text)
                    highlights.append(highlight_word)
                else:
                    clean_bullet = bullet_text
                    highlights.append(None)
                bullets.append(clean_bullet)
                elements.append({'type': 'bullet', 'text': clean_bullet, 'highlight': highlight_word if m else None})
            elif in_bullets and not line.startswith('- '):
                in_bullets = False
            elif line.startswith('**Image**:'):
                image_prompt = line.replace('**Image**:', '').strip()
                elements.append({'type': 'image', 'prompt': image_prompt})
        # For convenience, return a dict for slide content
        return {
            'format': format_type,
            'title': title,
            'bullets': bullets,
            'highlights': highlights,
            'image_prompt': image_prompt
        }

    def _draw_subtitle(self, img, subtitle_text):
        if not subtitle_text:
            return
        draw = ImageDraw.Draw(img, 'RGBA')
        margin = 60
        max_width = self.width - 2 * margin
        font = self.subtitle_overlay_font
        # Wrap subtitle if needed
        words = subtitle_text.split()
        lines = []
        current_line = ''
        for word in words:
            test_line = current_line + (' ' if current_line else '') + word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        # Draw background rectangle
        total_height = len(lines) * (font.size + 8) - 8
        y = self.height - margin - total_height
        max_line_width = max(draw.textbbox((0,0), line, font=font)[2] - draw.textbbox((0,0), line, font=font)[0] for line in lines)
        x = (self.width - max_line_width) // 2 - 20
        rect_w = max_line_width + 40
        rect_h = total_height + 20
        rect_y = y - 10
        draw.rounded_rectangle([x, rect_y, x+rect_w, rect_y+rect_h], radius=18, fill=(255,255,255,180))
        # Draw lines on top
        y_line = y
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x_line = (self.width - w) // 2
            draw.text((x_line, y_line), line, fill=(0,0,0), font=font)
            y_line += font.size + 8

    def create_slide_image(self, slide_dict, current_time, segment_start_time, slide_bullet_offset=0, background_img=None, subtitle_text=None, reveal_state=None, segment_duration=None):
        """Render slide from slide_dict (JSON) according to format, with typewriter and highlight animation."""
        format_type = slide_dict.get('format', 1)
        title = slide_dict.get('title', None)
        bullets = slide_dict.get('bullets', [])
        image_prompt = slide_dict.get('image_prompt', None)
        highlight_info = slide_dict.get('highlight_info', None)  # Optionally pass highlight info
        if background_img is None:
            raise ValueError("[BG][ERROR] No background image provided to create_slide_image! This should never happen.")
        img = background_img.copy()
        # Load generated Ideogram image for image slots (for formats 2, 3, 4)
        slide_number = slide_dict.get('slide_number', 1)
        format_type = slide_dict.get('format', 1)
        ideogram_img_path = os.path.join('generated_images_ideogram', f'slide_{slide_number}_format_{format_type}.png')
        sample_img = None
        if os.path.exists(ideogram_img_path):
            sample_img = Image.open(ideogram_img_path)
            print_flush(f"[IMAGE] Using Ideogram image: {ideogram_img_path}")
        else:
            # Fallback to sample image if Ideogram image doesn't exist
            sample_img_path = os.path.join('uploads', 'sample_image.jpg')
            if os.path.exists(sample_img_path):
                sample_img = Image.open(sample_img_path)
                print_flush(f"[IMAGE] Using fallback sample image: {sample_img_path}")
            else:
                print_flush(f"[IMAGE] No image found for slide {slide_number}, format {format_type}")
        # Format 1: Heading + Bullets (text-only)
        if format_type == 1:
            draw = ImageDraw.Draw(img)
            x0 = 80
            y0 = 120
            max_text_width = self.width//2 - 2*x0
            if title:
                lines = self._wrap_text(title, self.title_font, max_text_width, draw)
                for line in lines:
                    draw.text((x0, y0), line, fill=self.text_color, font=self.title_font)
                    y0 += self.title_font.size + 10
                y0 += 120  # Increased spacing between title and bullets (3x)
            fade_in_duration = 0.5
            for i, bullet in enumerate(bullets):
                alpha = int(255 * min(1.0, max(0, (current_time - segment_start_time - i*fade_in_duration)/fade_in_duration)))
                bullet_text = '\u2022 ' + bullet
                # Parse <highlight> tags in bullet
                import re
                m = re.search(r'<highlight>(.+?)</highlight>', bullet_text)
                if m:
                    highlight_word = m.group(1)
                    clean_bullet = re.sub(r'<highlight>(.+?)</highlight>', highlight_word, bullet_text)
                else:
                    highlight_word = None
                    clean_bullet = bullet_text
                bullet_lines = self._wrap_text(clean_bullet, self.body_font, max_text_width, draw)
                for line in bullet_lines:
                    if highlight_word and highlight_word in line:
                        pre, word, post = line.partition(highlight_word)
                        w_pre = draw.textbbox((0,0), pre, font=self.body_font)[2]
                        w_word = draw.textbbox((0,0), word, font=self.body_font)[2]
                        h_word = self.body_font.size + 8
                        rect_x = x0 + w_pre
                        rect_y = y0 - 4
                        draw.rounded_rectangle([rect_x, rect_y, rect_x + w_word, rect_y + h_word], radius=8, fill=(255, 215, 0, int(alpha*0.8)))
                        draw.text((x0, y0), pre, fill=(0,0,0,alpha), font=self.body_font)
                        draw.text((x0 + w_pre, y0), word, fill=(0,0,0,alpha), font=self.body_font)
                        draw.text((x0 + w_pre + w_word, y0), post, fill=(0,0,0,alpha), font=self.body_font)
                    else:
                        draw.text((x0, y0), line, fill=(0,0,0,alpha), font=self.body_font)
                    y0 += self.body_font.size + 10
            self._draw_subtitle(img, subtitle_text)
            return img
        # Format 2: Left text, right image (overlay image on right half, background is full slide)
        elif format_type == 2:
            if sample_img is not None:
                import math, random
                # Use the true segment duration for Ken Burns
                duration = segment_duration if segment_duration is not None else 8
                t = current_time - segment_start_time
                t = max(0, min(t, duration))
                random.seed(slide_dict.get('slide_number', 0))
                # Randomly pick effect type and direction
                effect_types = [
                    'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down',
                    'diag_tl_br', 'diag_tr_bl', 'diag_bl_tr', 'diag_br_tl'
                ]
                effect = random.choice(effect_types)
                progress = t / max(duration, 0.01)
                base_w, base_h = self.width//2, self.height
                # Always start with a larger crop for movement, guarantee full coverage
                crop_scale_start = 1.18
                crop_scale_end = 1.0
                # For zoom in/out, interpolate scale
                if effect == 'zoom_in':
                    scale = crop_scale_start - (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                elif effect == 'zoom_out':
                    scale = crop_scale_end + (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                else:
                    # For pan/tilt/diagonal, always use crop_scale_start for full coverage
                    crop_w = int(base_w * crop_scale_start)
                    crop_h = int(base_h * crop_scale_start)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    # Pan/tilt/diagonal logic
                    max_dx = crop_w - base_w
                    max_dy = crop_h - base_h
                    if effect == 'pan_left':
                        dx = int(max_dx * progress)
                        dy = 0
                    elif effect == 'pan_right':
                        dx = int(max_dx * (1 - progress))
                        dy = 0
                    elif effect == 'pan_up':
                        dx = 0
                        dy = int(max_dy * progress)
                    elif effect == 'pan_down':
                        dx = 0
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_tl_br':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * progress)
                    elif effect == 'diag_tr_bl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * progress)
                    elif effect == 'diag_bl_tr':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_br_tl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * (1 - progress))
                    else:
                        dx = max_dx // 2
                        dy = max_dy // 2
                    sample_img_cropped = img_crop.crop((dx, dy, dx + base_w, dy + base_h))
                img.paste(sample_img_cropped, (self.width//2, 0))
            draw = ImageDraw.Draw(img, 'RGBA')
            x0 = 90  # Move title and bullets slightly more left for format 2
            y0 = 120
            max_text_width = self.width//2 - 2*x0
            # --- Animation timing logic ---
            title_reveal_duration = 2.0
            bullet_fade_duration = 1.0
            bullet_pause = 1.0
            highlight_anim_duration = 0.7
            # Title typewriter effect (0-2s)
            if title:
                lines = self._wrap_text(title, self.title_font, max_text_width, draw)
                total_title_chars = sum(len(line) for line in lines)
                chars_to_show = int(min(1.0, max(0, (current_time - segment_start_time) / title_reveal_duration)) * total_title_chars)
                chars_drawn = 0
                for line in lines:
                    line_to_draw = line[:max(0, min(len(line), chars_to_show - chars_drawn))]
                    draw.text((x0, y0), line_to_draw, fill=self.text_color, font=self.title_font)
                    chars_drawn += len(line)
                    y0 += self.title_font.size + 10
                y0 += 120  # Consistent spacing between title and bullets
            # Bullets fade in one by one, each over 0.7s, with 1s pause between
            bullets_start_time = segment_start_time + title_reveal_duration
            bullet_times = []
            for i in range(len(bullets)):
                bullet_times.append(bullets_start_time + i * (bullet_fade_duration + bullet_pause))
            all_bullets_revealed_time = bullets_start_time + len(bullets) * (bullet_fade_duration + bullet_pause) - bullet_pause
            for i, bullet in enumerate(bullets):
                bullet_appear = bullet_times[i]
                t = current_time - bullet_appear
                alpha = int(255 * min(1.0, max(0, t / bullet_fade_duration))) if t > 0 else 0
                if alpha == 0:
                    y0 += self.body_font.size + 32  # Still increment y0 to keep spacing
                    continue  # Skip drawing this bullet until its fade-in starts
                bullet_text = bullet
                # Parse <highlight> tags in bullet
                import re
                m = re.search(r'<highlight>(.+?)</highlight>', bullet_text)
                if m:
                    highlight_word = m.group(1)
                    clean_bullet = re.sub(r'<highlight>(.+?)</highlight>', highlight_word, bullet_text)
                else:
                    highlight_word = None
                    clean_bullet = bullet_text
                bullet_lines = self._wrap_text(clean_bullet, self.body_font, max_text_width, draw)
                for line_idx, line in enumerate(bullet_lines):
                    # Draw bullet dot only for the first line of each bullet point
                    if alpha > 0 and line_idx == 0:
                        dot_radius = 7
                        dot_y = y0 + self.body_font.size//2
                        draw.ellipse([x0 - 30, dot_y - dot_radius, x0 - 16, dot_y + dot_radius], fill=(0,0,0,alpha))
                    # Highlight animation logic
                    highlight_box_alpha = alpha
                    highlight_box_width = None
                    if highlight_word and highlight_word in line:
                        pre, word, post = line.partition(highlight_word)
                        w_pre = draw.textbbox((0,0), pre, font=self.body_font)[2]
                        w_word = draw.textbbox((0,0), word, font=self.body_font)[2]
                        h_word = self.body_font.size + 8
                        rect_x = x0 + w_pre
                        rect_y = y0 - 4
                        # Animate highlight box only after all bullets are revealed
                        highlight_anim_start = all_bullets_revealed_time
                        highlight_anim_t = current_time - highlight_anim_start
                        if highlight_anim_t > 0:
                            highlight_progress = min(1.0, highlight_anim_t / highlight_anim_duration)
                            highlight_box_width = int(w_word * highlight_progress)
                            draw.rounded_rectangle([rect_x, rect_y, rect_x + highlight_box_width, rect_y + h_word], radius=8, fill=(255, 215, 0, int(200*highlight_progress)))
                        draw.text((x0, y0), pre, fill=(0,0,0,alpha), font=self.body_font)
                        draw.text((x0 + w_pre, y0), word, fill=(0,0,0,alpha), font=self.body_font)
                        draw.text((x0 + w_pre + w_word, y0), post, fill=(0,0,0,alpha), font=self.body_font)
                    else:
                        draw.text((x0, y0), line, fill=(0,0,0,alpha), font=self.body_font)
                    y0 += self.body_font.size + 32  # More space between bullet lines for aesthetics
            self._draw_subtitle(img, subtitle_text)
            return img
        # Format 3: Left image, right text (overlay image on left half, background is full slide)
        elif format_type == 3:
            if sample_img is not None:
                import math, random
                # Use the true segment duration for Ken Burns
                duration = segment_duration if segment_duration is not None else 8
                t = current_time - segment_start_time
                t = max(0, min(t, duration))
                random.seed(slide_dict.get('slide_number', 0))
                effect_types = [
                    'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down',
                    'diag_tl_br', 'diag_tr_bl', 'diag_bl_tr', 'diag_br_tl'
                ]
                effect = random.choice(effect_types)
                progress = t / max(duration, 0.01)
                base_w, base_h = self.width//2, self.height
                crop_scale_start = 1.18
                crop_scale_end = 1.0
                if effect == 'zoom_in':
                    scale = crop_scale_start - (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                elif effect == 'zoom_out':
                    scale = crop_scale_end + (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                else:
                    crop_w = int(base_w * crop_scale_start)
                    crop_h = int(base_h * crop_scale_start)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    max_dx = crop_w - base_w
                    max_dy = crop_h - base_h
                    if effect == 'pan_left':
                        dx = int(max_dx * progress)
                        dy = 0
                    elif effect == 'pan_right':
                        dx = int(max_dx * (1 - progress))
                        dy = 0
                    elif effect == 'pan_up':
                        dx = 0
                        dy = int(max_dy * progress)
                    elif effect == 'pan_down':
                        dx = 0
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_tl_br':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * progress)
                    elif effect == 'diag_tr_bl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * progress)
                    elif effect == 'diag_bl_tr':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_br_tl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * (1 - progress))
                    else:
                        dx = max_dx // 2
                        dy = max_dy // 2
                    sample_img_cropped = img_crop.crop((dx, dy, dx + base_w, dy + base_h))
                img.paste(sample_img_cropped, (0, 0))
            draw = ImageDraw.Draw(img, 'RGBA')
            x0 = self.width//2 + 120  # Keep the same layout
            y0 = 120
            max_text_width = self.width//2 - 2*80
            # --- Animation timing logic (copied from format 2) ---
            title_reveal_duration = 2.0
            bullet_fade_duration = 1.0
            bullet_pause = 1.0
            highlight_anim_duration = 0.7
            # Title typewriter effect (0-2s)
            if title:
                lines = self._wrap_text(title, self.title_font, max_text_width, draw)
                total_title_chars = sum(len(line) for line in lines)
                chars_to_show = int(min(1.0, max(0, (current_time - segment_start_time) / title_reveal_duration)) * total_title_chars)
                chars_drawn = 0
                for line in lines:
                    line_to_draw = line[:max(0, min(len(line), chars_to_show - chars_drawn))]
                    draw.text((x0, y0), line_to_draw, fill=self.text_color, font=self.title_font)
                    chars_drawn += len(line)
                    y0 += self.title_font.size + 10
                y0 += 120  # Consistent spacing between title and bullets
            # Bullets fade in one by one, each over 0.7s, with 1s pause between
            bullets_start_time = segment_start_time + title_reveal_duration
            bullet_times = []
            for i in range(len(bullets)):
                bullet_times.append(bullets_start_time + i * (bullet_fade_duration + bullet_pause))
            all_bullets_revealed_time = bullets_start_time + len(bullets) * (bullet_fade_duration + bullet_pause) - bullet_pause
            for i, bullet in enumerate(bullets):
                bullet_appear = bullet_times[i]
                t = current_time - bullet_appear
                alpha = int(255 * min(1.0, max(0, t / bullet_fade_duration))) if t > 0 else 0
                if alpha == 0:
                    y0 += self.body_font.size + 32  # Still increment y0 to keep spacing
                    continue  # Skip drawing this bullet until its fade-in starts
                bullet_text = bullet
                # Parse <highlight> tags in bullet
                import re
                m = re.search(r'<highlight>(.+?)</highlight>', bullet_text)
                if m:
                    highlight_word = m.group(1)
                    clean_bullet = re.sub(r'<highlight>(.+?)</highlight>', highlight_word, bullet_text)
                else:
                    highlight_word = None
                    clean_bullet = bullet_text
                bullet_lines = self._wrap_text(clean_bullet, self.body_font, max_text_width, draw)
                for line_idx, line in enumerate(bullet_lines):
                    # Draw bullet dot only for the first line of each bullet point
                    if alpha > 0 and line_idx == 0:
                        dot_radius = 7
                        dot_y = y0 + self.body_font.size//2
                        draw.ellipse([x0 - 30, dot_y - dot_radius, x0 - 16, dot_y + dot_radius], fill=(0,0,0,alpha))
                    # Highlight animation logic
                    highlight_box_alpha = alpha
                    highlight_box_width = None
                    if highlight_word and highlight_word in line:
                        pre, word, post = line.partition(highlight_word)
                        w_pre = draw.textbbox((0,0), pre, font=self.body_font)[2]
                        w_word = draw.textbbox((0,0), word, font=self.body_font)[2]
                        h_word = self.body_font.size + 8
                        rect_x = x0 + w_pre
                        rect_y = y0 - 4
                        # Animate highlight box only after all bullets are revealed
                        highlight_anim_start = all_bullets_revealed_time
                        highlight_anim_t = current_time - highlight_anim_start
                        if highlight_anim_t > 0:
                            highlight_progress = min(1.0, highlight_anim_t / highlight_anim_duration)
                            highlight_box_width = int(w_word * highlight_progress)
                            draw.rounded_rectangle([rect_x, rect_y, rect_x + highlight_box_width, rect_y + h_word], radius=8, fill=(255, 215, 0, int(200*highlight_progress)))
                        draw.text((x0, y0), pre, fill=(0,0,0,alpha), font=self.body_font)
                        draw.text((x0 + w_pre, y0), word, fill=(0,0,0,alpha), font=self.body_font)
                        draw.text((x0 + w_pre + w_word, y0), post, fill=(0,0,0,alpha), font=self.body_font)
                    else:
                        draw.text((x0, y0), line, fill=(0,0,0,alpha), font=self.body_font)
                    y0 += self.body_font.size + 32  # More space between bullet lines for aesthetics
            self._draw_subtitle(img, subtitle_text)
            return img
        # Format 4: Full image only (overlay image on full slide, background is still present but covered)
        elif format_type == 4:
            if sample_img is not None:
                import math, random
                # Use the true segment duration for Ken Burns
                duration = segment_duration if segment_duration is not None else 8
                t = current_time - segment_start_time
                t = max(0, min(t, duration))
                random.seed(slide_dict.get('slide_number', 0))
                # Randomly pick effect type and direction
                effect_types = [
                    'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down',
                    'diag_tl_br', 'diag_tr_bl', 'diag_bl_tr', 'diag_br_tl'
                ]
                effect = random.choice(effect_types)
                progress = t / max(duration, 0.01)
                base_w, base_h = self.width, self.height
                # Always start with a larger crop for movement, guarantee full coverage
                crop_scale_start = 1.18
                crop_scale_end = 1.0
                if effect == 'zoom_in':
                    scale = crop_scale_start - (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                elif effect == 'zoom_out':
                    scale = crop_scale_end + (crop_scale_start - crop_scale_end) * progress
                    crop_w = int(base_w * scale)
                    crop_h = int(base_h * scale)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    sample_img_cropped = img_crop
                else:
                    crop_w = int(base_w * crop_scale_start)
                    crop_h = int(base_h * crop_scale_start)
                    img_crop = self._center_crop_cover(sample_img, crop_w, crop_h)
                    max_dx = crop_w - base_w
                    max_dy = crop_h - base_h
                    if effect == 'pan_left':
                        dx = int(max_dx * progress)
                        dy = 0
                    elif effect == 'pan_right':
                        dx = int(max_dx * (1 - progress))
                        dy = 0
                    elif effect == 'pan_up':
                        dx = 0
                        dy = int(max_dy * progress)
                    elif effect == 'pan_down':
                        dx = 0
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_tl_br':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * progress)
                    elif effect == 'diag_tr_bl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * progress)
                    elif effect == 'diag_bl_tr':
                        dx = int(max_dx * progress)
                        dy = int(max_dy * (1 - progress))
                    elif effect == 'diag_br_tl':
                        dx = int(max_dx * (1 - progress))
                        dy = int(max_dy * (1 - progress))
                    else:
                        dx = max_dx // 2
                        dy = max_dy // 2
                    sample_img_cropped = img_crop.crop((dx, dy, dx + base_w, dy + base_h))
                img.paste(sample_img_cropped, (0, 0))
            self._draw_subtitle(img, subtitle_text)
            return img
        # Format 5: Heading only, centered
        elif format_type == 5:
            draw = ImageDraw.Draw(img)
            if title:
                bbox = draw.textbbox((0,0), title, font=self.title_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (self.width - text_width)//2
                y = (self.height - text_height)//2
                draw.text((x, y), title, fill=self.text_color, font=self.title_font)
            self._draw_subtitle(img, subtitle_text)
            return img
        # Default fallback
        else:
            draw = ImageDraw.Draw(img)
            draw.text((100, 100), f"Slide format {format_type}", fill=self.text_color, font=self.title_font)
            self._draw_subtitle(img, subtitle_text)
            return img
    
    def create_subtitle_text(self, word_segments, current_time):
        """Create subtitle text for current time, showing at most 7 words per segment, refreshing only when a new 7-word segment is reached."""
        print_flush(f"[DEBUG] create_subtitle_text called with {len(word_segments)} word segments, current_time={current_time}")
        if word_segments:
            print_flush(f"[DEBUG] First word segment: {word_segments[0]}")
        # Flatten all words up to current_time
        revealed_words = []
        for word in word_segments:
            if word['end'] <= current_time:
                revealed_words.append(word['text'])
            else:
                break
        # Show the most recent 7-word segment
        n = len(revealed_words)
        if n == 0:
            return ""
        # Find which 7-word segment we are in
        segment_size = 7
        segment_idx = (n - 1) // segment_size
        start_idx = segment_idx * segment_size
        end_idx = min(start_idx + segment_size, n)
        current_segment_words = revealed_words[start_idx:end_idx]
        current_sentence_text = " ".join(current_segment_words)
        return current_sentence_text
    
    def generate_video(self, segments_file, word_srt_file, audio_file, output_file, show_subtitles=True, selected_background=None):
        """Generate the complete video with slides and subtitles using MoviePy, using slides.json for slide content."""
        print_flush("Cleaning up previous run files...")
        temp_slides_dir = "temp_slides"
        if os.path.exists(temp_slides_dir):
            shutil.rmtree(temp_slides_dir)
        temp_subtitles_dir = "temp_subtitles"
        if os.path.exists(temp_subtitles_dir):
            shutil.rmtree(temp_subtitles_dir)
        print_flush("Loading segments data...")
        segments_data = self.load_segments_data(segments_file)
        word_segments = self.load_word_segments(word_srt_file)
        # Load slides.json
        slides_json_path = os.path.join(self.segments_folder, 'slides.json')
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)
        print_flush(f"[DEBUG] Loaded {len(slides)} slides from slides.json")
        print_flush("Creating video clips...")
        video_clips = []
        total_segments = len(segments_data['segments'])
        # Select background image
        background_img = None
        if selected_background:
            selected_bg_path = os.path.join('background', selected_background)
            if os.path.exists(selected_bg_path):
                print_flush(f'[BG] Using user-selected background image: {selected_bg_path}')
                background_img = Image.open(selected_bg_path)
                print_flush(f'[BG] Loaded image mode: {background_img.mode}, size: {background_img.size}')
                if background_img.mode != 'RGB':
                    print_flush(f'[BG][WARN] Image mode is {background_img.mode}, converting to RGB.')
                    background_img = background_img.convert('RGB')
                background_img = background_img.resize((self.width, self.height))
            else:
                raise Exception(f'[BG] Selected background not found: {selected_bg_path}')
        else:
            background_images = glob(os.path.join('background', '*.png')) + glob(os.path.join('background', '*.jpg'))
            if not background_images:
                raise Exception('[BG] No background images found in background/ folder.')
            selected_bg_path = random.choice(background_images)
            print_flush(f'[BG] Using random background image: {selected_bg_path}')
            background_img = Image.open(selected_bg_path)
            print_flush(f'[BG] Loaded image mode: {background_img.mode}, size: {background_img.size}')
            if background_img.mode != 'RGB':
                print_flush(f'[BG][WARN] Image mode is {background_img.mode}, converting to RGB.')
                background_img = background_img.convert('RGB')
            background_img = background_img.resize((self.width, self.height))
        def create_slide_image_with_bg(slide_dict, current_time, segment_start_time, subtitle_text=None, reveal_state=None, segment_duration=None):
            print_flush(f'[BG] Copying background image for slide at time {current_time}')
            # Always pass the background_img argument
            return self.create_slide_image(slide_dict, current_time, segment_start_time, background_img=background_img, subtitle_text=subtitle_text, reveal_state=reveal_state, segment_duration=segment_duration)

        for idx, segment in enumerate(segments_data['segments']):
            print_flush(f"[DEBUG] Processing segment {idx}: {segment}")
            if idx < len(slides):
                slide_dict = slides[idx]
                print_flush(f"[DEBUG] Using slide_dict: {slide_dict}")
                duration = segment['end_time'] - segment['start_time']
                print_flush(f"[PROGRESS] Segment {idx+1}/{total_segments}")
                def create_make_frame(slide_dict, segment_start_time, segment_idx, segment_duration):
                    def make_frame(t):
                        current_time = segment_start_time + t
                        subtitle_text = self.create_subtitle_text(word_segments, current_time)
                        # --- Animation logic ---
                        # Animation timing parameters
                        typewriter_speed = 30  # chars per second
                        bullet_delay = 0.5     # seconds between bullets
                        highlight_delay = 0.5  # seconds after last bullet
                        # Title typewriter
                        title = slide_dict.get('title', '')
                        total_title_chars = len(title)
                        title_chars = min(int(typewriter_speed * t), total_title_chars)
                        # Bullets typewriter
                        bullets = slide_dict.get('bullets', [])
                        bullets_to_show = []
                        time_after_title = max(0, t - total_title_chars / typewriter_speed)
                        for i, bullet in enumerate(bullets):
                            start_time = i * bullet_delay
                            if time_after_title > start_time:
                                chars = min(int(typewriter_speed * (time_after_title - start_time)), len(bullet))
                                bullets_to_show.append(chars)
                            else:
                                bullets_to_show.append(0)
                        # Highlight logic
                        highlight_word = None
                        if bullets:
                            last_bullet_time = (len(bullets)-1) * bullet_delay + len(bullets[-1]) / typewriter_speed
                            if time_after_title > last_bullet_time + highlight_delay:
                                # Find highlight word (first word > 3 chars in first bullet)
                                for bullet in bullets:
                                    for word in bullet.split():
                                        if len(word) > 3:
                                            highlight_word = word
                                            break
                                    if highlight_word:
                                        break
                        reveal_state = {'title_chars': title_chars, 'bullets': bullets_to_show, 'highlight_word': highlight_word}
                        slide_img = create_slide_image_with_bg(slide_dict, current_time, segment_start_time, subtitle_text=subtitle_text, reveal_state=reveal_state, segment_duration=segment_duration)
                        if t < 0.1:
                            print_flush(f"[RENDER DEBUG] Segment {segment_idx} rendering: Title='{slide_dict.get('title','')}'")
                        return np.array(slide_img)
                    return make_frame
                make_frame = create_make_frame(slide_dict, segment['start_time'], idx, duration)
                clip = VideoClip(make_frame, duration=duration)
                print_flush(f"[CLIP DEBUG] Created clip for segment {idx} with duration {duration}s")
                video_clips.append(clip)
                print_flush(f"[CLIP DEBUG] Total clips so far: {len(video_clips)}")
            else:
                print_flush(f"[ERROR] No slide JSON for segment {idx}")
        print_flush("Concatenating video clips...")
        print_flush(f"[CONCAT DEBUG] Concatenating {len(video_clips)} video clips")
        for i, clip in enumerate(video_clips):
            print_flush(f"[CONCAT DEBUG] Clip {i}: duration={clip.duration}s")
        # Ensure the last slide stays until the end
        total_duration = segments_data['segments'][-1]['end_time']
        current_duration = sum([clip.duration for clip in video_clips])
        if current_duration < total_duration:
            print_flush(f"[FIX] Adding still frame for last slide to fill {total_duration - current_duration:.2f}s gap at end.")
            last_slide = slides[-1]
            last_segment = segments_data['segments'][-1]
            def make_last_frame(t):
                reveal_time = last_segment['start_time'] + last_segment['duration'] + 5
                return np.array(create_slide_image_with_bg(
                    last_slide,
                    reveal_time,
                    last_segment['start_time'],
                    segment_duration=last_segment['duration']
                ))
            gap_duration = total_duration - current_duration
            if gap_duration > 0.01:
                last_clip = VideoClip(make_last_frame, duration=gap_duration)
                video_clips.append(last_clip)
        final_video = concatenate_videoclips(video_clips)
        print_flush("Adding audio...")
        audio_clip = AudioFileClip(audio_file)
        print_flush("Compositing final video...")
        final_video = concatenate_videoclips(video_clips)
        final_video = final_video.set_audio(audio_clip)
        print_flush("Writing video file...")
        final_video.write_videofile(
            output_file,
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=8,
            verbose=False,
            logger=None
        )
        print_flush("Cleaning up...")
        final_video.close()
        audio_clip.close()
        for clip in video_clips:
            clip.close()
        print_flush(f"Video generated successfully: {output_file}")
        return output_file 

    def _wrap_text(self, text, font, max_width, draw):
        # Splits text into lines so that each line fits within max_width
        words = text.split()
        lines = []
        current_line = ''
        for word in words:
            test_line = current_line + (' ' if current_line else '') + word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines

    def _center_crop_cover(self, img, target_width, target_height):
        # Scale and crop the image to fill the target size (center crop, no squeeze)
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height
        if img_ratio > target_ratio:
            # Image is wider than target: crop left/right
            new_height = target_height
            new_width = int(target_height * img_ratio)
        else:
            # Image is taller than target: crop top/bottom
            new_width = target_width
            new_height = int(target_width / img_ratio)
        img = img.resize((new_width, new_height), Image.LANCZOS)
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height
        img = img.crop((left, top, right, bottom))
        return img 