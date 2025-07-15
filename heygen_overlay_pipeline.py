import json
import os
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURABLE ---
SLIDES_JSON_PATH = 'segments/slides.json'
FONT_PATH = 'circular-std-font-family/CircularStd-Book.ttf'
TITLE_FONT_SIZE = 72
BODY_FONT_SIZE = 36
SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
LEFT_MARGIN = 80
TOP_MARGIN = 120
BULLET_SPACING = 44  # BODY_FONT_SIZE + 8
SUBTITLE_HEIGHT = 60  # Estimated subtitle box height
BOTTOM_MARGIN = 80  # Space from bottom for subtitle

# --- Step 1: Identify empty space in format 2 and 3 slides ---
def wrap_text(text, font, max_width, draw):
    # Simple word wrap for PIL
    words = text.split()
    lines = []
    current_line = ''
    for word in words:
        test_line = current_line + (' ' if current_line else '') + word
        # Use textbbox to get width
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

def calculate_empty_space(slide, title_font, body_font):
    # Only for format 2 and 3
    format_type = slide.get('format')
    if format_type not in [2, 3]:
        return None
    title = slide.get('title', '')
    bullets = slide.get('bullets', [])
    # Calculate text area (left or right half)
    max_text_width = SLIDE_WIDTH // 2 - 2 * LEFT_MARGIN
    img = Image.new('RGB', (SLIDE_WIDTH, SLIDE_HEIGHT))
    draw = ImageDraw.Draw(img)
    y = TOP_MARGIN
    # Title
    title_lines = wrap_text(title, title_font, max_text_width, draw)
    for line in title_lines:
        y += title_font.size + 10
    y += 120  # Space between title and bullets
    # Bullets
    for bullet in bullets:
        bullet_lines = wrap_text(bullet, body_font, max_text_width, draw)
        for line in bullet_lines:
            y += body_font.size + 8
        y += 24  # Extra space between bullets
    bullets_end_y = y
    # Subtitle area (bottom)
    subtitle_y = SLIDE_HEIGHT - BOTTOM_MARGIN - SUBTITLE_HEIGHT
    # The empty space is from bullets_end_y to subtitle_y
    empty_space_top = bullets_end_y
    empty_space_bottom = subtitle_y
    empty_space_height = max(0, empty_space_bottom - empty_space_top)
    # For format 2: text is on left, for 3: text is on right
    if format_type == 2:
        x = LEFT_MARGIN
    else:
        x = SLIDE_WIDTH // 2 + LEFT_MARGIN
    width = SLIDE_WIDTH // 2 - 2 * LEFT_MARGIN
    return {
        'slide_number': slide.get('slide_number'),
        'format': format_type,
        'empty_space': {
            'x': x,
            'y': empty_space_top,
            'width': width,
            'height': empty_space_height
        }
    }

def main():
    # Load fonts
    try:
        title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
        body_font = ImageFont.truetype(FONT_PATH, BODY_FONT_SIZE)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
    # Load slides
    with open(SLIDES_JSON_PATH, 'r', encoding='utf-8') as f:
        slides = json.load(f)
    empty_spaces = []
    for slide in slides:
        result = calculate_empty_space(slide, title_font, body_font)
        if result:
            empty_spaces.append(result)
    # Save for next steps
    with open('heygen_empty_spaces.json', 'w', encoding='utf-8') as f:
        json.dump(empty_spaces, f, indent=2)
    print(f"Identified empty spaces for {len(empty_spaces)} slides (formats 2 & 3). Saved to heygen_empty_spaces.json.")

if __name__ == '__main__':
    main() 