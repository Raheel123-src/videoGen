#!/usr/bin/env python3
import re

def parse_markdown_content(markdown_content):
    """Parse only the title and bullets from a markdown section. Extract <highlight> tags in bullets."""
    elements = []
    lines = markdown_content.split('\n')
    title = None
    bullets = []
    in_bullets = False
    
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
            # Extract bullet text and highlights
            bullet_text = line[2:]  # Remove '- '
            plain_text = bullet_text
            highlights = []
            
            # Find all <highlight>...</highlight> tags
            highlight_pattern = r'<highlight>(.*?)</highlight>'
            matches = re.finditer(highlight_pattern, bullet_text)
            
            for match in matches:
                highlighted_word = match.group(1)
                start_pos = match.start()
                end_pos = match.end()
                
                # Remove the highlight tags from plain text
                plain_text = plain_text.replace(match.group(0), highlighted_word)
                
                # Calculate position after removing tags
                highlights.append({
                    'word': highlighted_word,
                    'position': start_pos
                })
            
            print(f"[PARSE DEBUG] Found bullet: '{plain_text}' with highlights: {highlights}")
            if highlights:
                print(f"[PARSE DEBUG] Highlight words: {[h['word'] for h in highlights]}")
                print(f"[PARSE DEBUG] Highlight details: {highlights}")
            bullets.append({'text': plain_text, 'highlights': highlights})
        elif in_bullets and not line.startswith('- '):
            # End of bullets section
            in_bullets = False
    
    if title:
        elements.append({'type': 'title', 'text': title})
    for bullet in bullets:
        elements.append({'type': 'bullet', 'text': bullet['text'], 'highlights': bullet['highlights']})
    
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

print("Parsed elements:")
for i, elem in enumerate(elements):
    print(f"Element {i}: {elem['type']} = '{elem['text']}'")
    if elem['type'] == 'bullet' and elem.get('highlights'):
        print(f"  Highlights: {elem['highlights']}")
        for h in elem['highlights']:
            print(f"    - '{h['word']}' at position {h['position']}")

print("\n" + "="*50 + "\n")
print("Testing highlight word finding...")

# Test finding highlighted words in bullet text
for elem in elements:
    if elem['type'] == 'bullet' and elem.get('highlights'):
        btext = elem['text']
        print(f"Testing bullet: '{btext}'")
        for h in elem['highlights']:
            hword = h['word']
            word_start = btext.lower().find(hword.lower())
            print(f"  Looking for '{hword}' in '{btext}'")
            print(f"  Found at position: {word_start}")
            if word_start != -1:
                print(f"  ✓ Word found and can be highlighted!")
            else:
                print(f"  ✗ Word NOT found!") 