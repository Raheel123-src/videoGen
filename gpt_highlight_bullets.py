import os
import openai
from dotenv import load_dotenv
import json
import sys

# Usage: python gpt_highlight_bullets.py slides.json
if len(sys.argv) < 2:
    print('Usage: python gpt_highlight_bullets.py slides.json')
    sys.exit(1)

input_path = sys.argv[1]

# Load API key from .env
load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

with open(input_path, 'r', encoding='utf-8') as f:
    slides = json.load(f)

# Dummy highlight logic for now: highlight the first word in the first bullet of each slide
for slide in slides:
    bullets = slide.get('bullets', [])
    for i, bullet in enumerate(bullets):
        if '<highlight>' not in bullet and i == 0:
            words = bullet.split()
            if len(words) > 1:
                words[1] = f'<highlight>{words[1]}</highlight>'
                bullets[i] = ' '.join(words)
    slide['bullets'] = bullets

with open(input_path, 'w', encoding='utf-8') as f:
    json.dump(slides, f, ensure_ascii=False, indent=2)

print('[DEBUG] presentation.md updated with highlights.') 