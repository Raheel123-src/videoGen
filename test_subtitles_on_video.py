import argparse
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import re

def parse_srt(srt_path):
    """Parse SRT file into a list of dicts with start, end, and text."""
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\d+\n|\Z)', re.MULTILINE)
    subtitles = []
    for match in pattern.finditer(content):
        idx, start, end, text = match.groups()
        text = text.strip().replace('\n', ' ')
        subtitles.append({
            'start': srt_time_to_seconds(start),
            'end': srt_time_to_seconds(end),
            'text': text
        })
    return subtitles

def srt_time_to_seconds(srt_time):
    h, m, s_ms = srt_time.split(':')
    s, ms = s_ms.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

def add_subtitles_to_video(video_path, srt_path, output_path):
    video = VideoFileClip(video_path)
    subtitles = parse_srt(srt_path)
    subtitle_clips = []
    for sub in subtitles:
        txt_clip = TextClip(sub['text'], fontsize=48, font='Arial-Bold', color='white', stroke_color='black', stroke_width=2, method='caption', size=(video.w * 0.9, None), align='center')
        txt_clip = txt_clip.set_position(('center', 'bottom')).set_start(sub['start']).set_end(sub['end'])
        subtitle_clips.append(txt_clip)
    final = CompositeVideoClip([video] + subtitle_clips)
    final.write_videofile(output_path, codec='libx264', audio_codec='aac', preset='ultrafast')

def main():
    parser = argparse.ArgumentParser(description='Overlay SRT subtitles onto a video file.')
    parser.add_argument('--video', required=True, help='Path to input video file')
    parser.add_argument('--srt', required=True, help='Path to SRT subtitle file')
    parser.add_argument('--output', required=True, help='Path to output video file')
    args = parser.parse_args()
    add_subtitles_to_video(args.video, args.srt, args.output)

if __name__ == '__main__':
    main() 