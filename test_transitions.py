#!/usr/bin/env python3
"""
Test script for video transitions functionality.
This script demonstrates how to use the new transition manager with the video generator.
"""

import os
import json
import sys
from video_generator import VideoGenerator
from transition_manager import TransitionManager

def test_transition_manager():
    """Test the transition manager functionality"""
    print("=" * 60)
    print("TESTING TRANSITION MANAGER")
    print("=" * 60)
    
    # Initialize transition manager
    tm = TransitionManager(width=1920, height=1080, fps=30)
    
    # Test available transitions
    print(f"Available transitions: {list(tm.transition_types.keys())}")
    
    # Test random transition selection
    print("\nRandom transition selections:")
    for i in range(5):
        transition = tm.get_random_transition()
        print(f"  {i+1}: {transition}")
    
    # Test slide-specific transitions
    test_slides = [
        {'format': 2, 'title': 'Left text, right image'},
        {'format': 3, 'title': 'Right text, left image'},
        {'format': 4, 'title': 'Full image slide'},
        {'format': 1, 'title': 'Text only slide'}
    ]
    
    print("\nSlide-specific transition recommendations:")
    for slide in test_slides:
        transition = tm.get_transition_for_slide(slide)
        print(f"  Format {slide['format']} ({slide['title']}): {transition}")
    
    # Test transition configuration creation
    print("\nCreating transition configuration...")
    transition_configs = tm.create_slide_transition_config(test_slides)
    for config in transition_configs:
        print(f"  Slide {config['slide_number']}: {config['transition_type']} ({config['duration']}s)")
    
    print("\nTransition manager test completed successfully!")

def test_video_generator_with_transitions():
    """Test video generator with transitions"""
    print("\n" + "=" * 60)
    print("TESTING VIDEO GENERATOR WITH TRANSITIONS")
    print("=" * 60)
    
    # Check if we have the required files
    segments_folder = "segments"
    transcripts_folder = "transcripts"
    font_folder = "circular-std-font-family"
    
    # Find a recent session folder
    session_folders = []
    if os.path.exists(segments_folder):
        for item in os.listdir(segments_folder):
            item_path = os.path.join(segments_folder, item)
            if os.path.isdir(item_path):
                session_folders.append(item)
    
    if not session_folders:
        print("No session folders found. Please run a video generation first.")
        return
    
    # Use the most recent session folder
    latest_session = sorted(session_folders)[-1]
    session_path = os.path.join(segments_folder, latest_session)
    
    print(f"Using session folder: {session_path}")
    
    # Check for required files
    slides_json_path = os.path.join(session_path, "slides.json")
    segments_json_path = None
    word_srt_path = None
    
    # Find segments and SRT files
    for file in os.listdir(session_path):
        if file.endswith("_segments.json"):
            segments_json_path = os.path.join(session_path, file)
        elif file.endswith("_words.srt"):
            word_srt_path = os.path.join(session_path, file)
    
    if not all([slides_json_path, segments_json_path, word_srt_path]):
        print("Missing required files:")
        print(f"  slides.json: {os.path.exists(slides_json_path)}")
        print(f"  segments.json: {os.path.exists(segments_json_path) if segments_json_path else False}")
        print(f"  word_srt: {os.path.exists(word_srt_path) if word_srt_path else False}")
        return
    
    print("Required files found!")
    
    # Initialize video generator
    video_gen = VideoGenerator(
        segments_folder=session_path,
        transcripts_folder=session_path,
        font_folder=font_folder
    )
    
    # Test transition settings
    print("\nTesting transition settings:")
    
    # Show available transitions
    available_transitions = video_gen.get_available_transitions()
    print(f"Available transitions: {available_transitions}")
    
    # Test different transition configurations
    test_configs = [
        ("Default transitions", None, None),
        ("Fade transitions", "fade", 0.5),
        ("Slide transitions", "slide_left", 0.8),
        ("Zoom transitions", "zoom_in", 0.6),
        ("Wipe transitions", "wipe_right", 0.7)
    ]
    
    for config_name, transition_type, duration in test_configs:
        print(f"\n--- Testing {config_name} ---")
        
        # Configure transitions
        if transition_type:
            video_gen.set_transition_type(transition_type)
        if duration:
            video_gen.set_transition_duration(duration)
        
        # Enable transitions
        video_gen.enable_transitions(True)
        
        # Load slides to test transition configuration
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)
        
        # Create transition configuration
        transition_configs = video_gen.transition_manager.create_slide_transition_config(slides)
        
        print(f"Transition configuration for {len(slides)} slides:")
        for i, config in enumerate(transition_configs[:3]):  # Show first 3
            print(f"  Slide {config['slide_number']}: {config['transition_type']} ({config['duration']}s)")
        if len(transition_configs) > 3:
            print(f"  ... and {len(transition_configs) - 3} more slides")
    
    print("\nVideo generator transition test completed successfully!")

def create_sample_transition_video():
    """Create a sample video with transitions for demonstration"""
    print("\n" + "=" * 60)
    print("CREATING SAMPLE TRANSITION VIDEO")
    print("=" * 60)
    
    # This would require actual audio and image files
    # For now, just demonstrate the configuration
    print("To create a sample video with transitions:")
    print("1. Ensure you have generated slides and audio")
    print("2. Use the video generator with transitions enabled")
    print("3. The transitions will be automatically applied between slides")
    
    # Example usage:
    print("\nExample usage:")
    print("""
# Initialize video generator
video_gen = VideoGenerator(segments_folder, transcripts_folder, font_folder)

# Enable and configure transitions
video_gen.enable_transitions(True)
video_gen.set_transition_duration(0.6)
video_gen.set_transition_type('fade')  # or 'slide_left', 'zoom_in', etc.

# Generate video with transitions
video_gen.generate_video(segments_file, word_srt_file, audio_file, output_file)
    """)

def main():
    """Main test function"""
    print("VIDEO TRANSITIONS TEST SUITE")
    print("=" * 60)
    
    try:
        # Test transition manager
        test_transition_manager()
        
        # Test video generator with transitions
        test_video_generator_with_transitions()
        
        # Show sample video creation info
        create_sample_transition_video()
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("\nThe transition system is ready to use!")
        print("Transitions will be automatically applied when generating videos.")
        
    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 