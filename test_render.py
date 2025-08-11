import os
import sys
import glob


def main():
    # Hardcoded inputs per request
    session_id = "Eisaivideo1_32e67675"
    audio_file = "uploads/Eisaivideo1_32e67675/audio_c5f77a77467c4f9eacdf3bba3fce805c_bgm.mp3"
    transcripts_folder = "transcripts/Eisaivideo1_32e67675"
    segments_folder = "segments/Eisaivideo1_32e67675"
    images_folder = "generated_images_ideogram/Eisaivideo1_32e67675"

    # Validate required paths
    for path in [audio_file, transcripts_folder, segments_folder, images_folder]:
        if not os.path.exists(path):
            print(f"[ERROR] Path not found: {path}")
            sys.exit(1)

    # Locate required files
    word_srt_candidates = sorted(glob.glob(os.path.join(transcripts_folder, "*_words.srt")))
    if not word_srt_candidates:
        print(f"[ERROR] No word-level SRT found in: {transcripts_folder}")
        sys.exit(1)
    word_srt_file = word_srt_candidates[-1]

    segments_json_candidates = sorted(glob.glob(os.path.join(segments_folder, "*_segments.json")))
    if not segments_json_candidates:
        print(f"[ERROR] No segments JSON found in: {segments_folder}")
        sys.exit(1)
    segments_file = segments_json_candidates[-1]

    # Output path: same folder as audio, filename TESTVIDEO.mp4
    output_dir = os.path.dirname(os.path.abspath(audio_file))
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "TESTVIDEO.mp4")

    print("[TEST] Using:")
    print(f"  session_id: {session_id}")
    print(f"  audio_file: {audio_file}")
    print(f"  transcripts_folder: {transcripts_folder}")
    print(f"  segments_folder: {segments_folder}")
    print(f"  images_folder: {images_folder}")
    print(f"  word_srt_file: {word_srt_file}")
    print(f"  segments_file: {segments_file}")
    print(f"  output_file: {output_file}")

    # Import generators
    from video_generator_portrait import VideoGeneratorPortrait

    # Initialize portrait generator (to match the user’s prior run)
    video_gen = VideoGeneratorPortrait(
        segments_folder=segments_folder,
        transcripts_folder=transcripts_folder,
        font_folder='circular-std-font-family',
        session_id=session_id,
    )

    # Render video
    print("[TEST] Starting render...")
    video_gen.generate_video(
        segments_file=segments_file,
        word_srt_file=word_srt_file,
        audio_file=audio_file,
        output_file=output_file,
        show_subtitles=True,
        selected_background=None,
    )
    print(f"[TEST] Render complete: {output_file}")


if __name__ == "__main__":
    main()



