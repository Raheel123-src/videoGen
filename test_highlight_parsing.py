#!/usr/bin/env python3
import re

def parse_markdown_content(markdown_content):
    """Parse only the title and bullets from a markdown section. Extract <highlight> tags in bullets."""
    elements = []
    lines = markdown_content.split('\n')
    title = None
    bullets = []
    in_bullets = False
    print(f"[PARSE DEBUG] Raw markdown content:")
    print(f"[PARSE DEBUG] {markdown_content[:200]}...")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('**Title**:'):
            title = line.replace('**Title**:', '').strip()
            print(f"[PARSE DEBUG] Found title: '{title}'")
        elif line.startswith('**Slide Bullets**:'):
            in_bullets = True
            print(f"[PARSE DEBUG] Entering bullets section")
        elif in_bullets and line.startswith('- '):
            bullet_text = line[2:].strip()
            # Extract highlights
            highlights = []
            plain_text = ''
            last_idx = 0
            for m in re.finditer(r'<highlight>(.+?)</highlight>', bullet_text):
                start, end = m.span()
                word = m.group(1)
                highlights.append({'word': word, 'start': len(plain_text) + (m.start() - last_idx), 'end': len(plain_text) + (m.start() - last_idx) + len(word)})
                plain_text += bullet_text[last_idx:m.start()] + word
                last_idx = m.end()
            plain_text += bullet_text[last_idx:]
            print(f"[PARSE DEBUG] Found bullet: '{plain_text}' with highlights: {highlights}")
            if highlights:
                print(f"[PARSE DEBUG] Highlight words: {[h['word'] for h in highlights]}")
            bullets.append({'text': plain_text, 'highlights': highlights})
        elif in_bullets and not line.startswith('- '):
            print(f"[PARSE DEBUG] Exiting bullets section")
            break
    if title:
        elements.append({'type': 'title', 'text': title})
    for bullet in bullets:
        elements.append({'type': 'bullet', 'text': bullet['text'], 'highlights': bullet['highlights']})
    print(f"[PARSE DEBUG] Final elements: {len(elements)} items")
    for i, elem in enumerate(elements):
        print(f"[PARSE DEBUG] Element {i}: {elem['type']} = '{elem['text']}' highlights={elem.get('highlights')}")
    return elements

# Test parsing the current presentation.md
with open('segments/presentation.md', 'r', encoding='utf-8') as f:
    content = f.read()

print("=== Testing Highlight Parsing ===")
print("Raw content:")
print(content)
print("\n" + "="*50 + "\n")

# Parse the content
elements = parse_markdown_content(content)

print("\nParsed elements:")
for i, elem in enumerate(elements):
    print(f"Element {i}: {elem['type']} = '{elem['text']}'")
    if elem['type'] == 'bullet' and elem.get('highlights'):
        print(f"  Highlights: {elem['highlights']}")
        for h in elem['highlights']:
            print(f"    - '{h['word']}' at position {h['start']}-{h['end']}") 