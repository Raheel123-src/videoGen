#!/usr/bin/env python3
"""
Demonstration script for video transitions.
This script shows how to generate a video with different transition configurations.
"""

import os
import sys
from video_generator import VideoGenerator

def demo_transitions():
    """Demonstrate different transition configurations"""
    print("VIDEO TRANSITIONS DEMONSTRATION")
    print("=" * 60)
    
    # Check for existing session data
    segments_folder = "segments"
    if not os.path.exists(segments_folder):
        print("No segments folder found. Please run a video generation first.")
        return
    
    # Find the most recent session
    session_folders = [f for f in os.listdir(segments_folder) 
                      if os.path.isdir(os.path.join(segments_folder, f))]
    
    if not session_folders:
        print("No session folders found. Please run a video generation first.")
        return
    
    latest_session = sorted(session_folders)[-1]
    session_path = os.path.join(segments_folder, latest_session)
    
    print(f"Using session: {latest_session}")
    
    # Check for required files
    required_files = {
        'slides.json': os.path.join(session_path, 'slides.json'),
        'segments.json': None,
        'word_srt': None,
        'audio': None
    }
    
    # Find segments and SRT files
    for file in os.listdir(session_path):
        if file.endswith('_segments.json'):
            required_files['segments.json'] = os.path.join(session_path, file)
        elif file.endswith('_words.srt'):
            required_files['word_srt'] = os.path.join(session_path, file)
        elif file.endswith('.mp3') or file.endswith('.wav'):
            required_files['audio'] = os.path.join(session_path, file)
    
    # Check if all required files exist
    missing_files = [name for name, path in required_files.items() 
                    if path is None or not os.path.exists(path)]
    
    if missing_files:
        print(f"Missing required files: {missing_files}")
        print("Please ensure you have generated slides, segments, and audio files.")
        return
    
    print("All required files found!")
    
    # Initialize video generator
    video_gen = VideoGenerator(
        segments_folder=session_path,
        transcripts_folder=session_path,
        font_folder='circular-std-font-family'
    )
    
    # Demo different transition configurations
    demo_configs = [
        {
            'name': 'Fade Transitions',
            'transition_type': 'fade',
            'duration': 0.5,
            'description': 'Smooth fade in/out between slides'
        },
        {
            'name': 'Slide Transitions',
            'transition_type': 'slide_left',
            'duration': 0.6,
            'description': 'Slides move from right to left'
        },
        {
            'name': 'Zoom Transitions',
            'transition_type': 'zoom_in',
            'duration': 0.7,
            'description': 'Zoom in effect between slides'
        },
        {
            'name': 'Wipe Transitions',
            'transition_type': 'wipe_right',
            'duration': 0.4,
            'description': 'Wipe effect from left to right'
        },
        {
            'name': 'Auto-Select Transitions',
            'transition_type': None,  # Let system auto-select
            'duration': 0.6,
            'description': 'Intelligent transition selection based on slide format'
        }
    ]
    
    print("\nAvailable transition configurations:")
    for i, config in enumerate(demo_configs, 1):
        print(f"{i}. {config['name']}: {config['description']}")
    
    print("\nTo generate a video with transitions:")
    print("1. Choose a configuration from above")
    print("2. Configure the video generator")
    print("3. Call generate_video()")
    
    # Example configuration
    print("\nExample configuration:")
    print("""
# Choose configuration (e.g., Fade Transitions)
config = demo_configs[0]  # Fade Transitions

# Configure video generator
video_gen.enable_transitions(True)
video_gen.set_transition_duration(config['duration'])
if config['transition_type']:
    video_gen.set_transition_type(config['transition_type'])

# Generate video
output_file = f"demo_{config['name'].lower().replace(' ', '_')}.mp4"
video_gen.generate_video(
    segments_file=required_files['segments.json'],
    word_srt_file=required_files['word_srt'],
    audio_file=required_files['audio'],
    output_file=output_file,
    show_subtitles=True,
    selected_background='1.jpg'
)
    """)
    
    # Show available transitions
    print(f"\nAvailable transition types: {video_gen.get_available_transitions()}")
    
    print("\nTransition system is ready for use!")
    print("Transitions will be automatically applied when generating videos through the main API.")

def show_integration_info():
    """Show how transitions are integrated into the main system"""
    print("\n" + "=" * 60)
    print("INTEGRATION INFORMATION")
    print("=" * 60)
    
    print("The transition system is automatically integrated into:")
    print("1. VideoGenerator class - for programmatic use")
    print("2. mainModel.py API - for web API use")
    print("3. All video generation workflows")
    
    print("\nDefault settings:")
    print("- Transitions: Enabled")
    print("- Duration: 0.6 seconds")
    print("- Type: Auto-selected based on slide format")
    
    print("\nTo customize transitions in the API:")
    print("1. Edit mainModel.py")
    print("2. Modify the video generation section")
    print("3. Set your preferred transition settings")
    
    print("\nExample API customization:")
    print("""
# In mainModel.py, find the video generation section and modify:
video_gen.enable_transitions(True)
video_gen.set_transition_duration(0.8)  # Longer transitions
video_gen.set_transition_type('slide_left')  # Specific type
    """)

def main():
    """Main demonstration function"""
    try:
        demo_transitions()
        show_integration_info()
        
        print("\n" + "=" * 60)
        print("DEMONSTRATION COMPLETED")
        print("=" * 60)
        print("The transition system is fully functional and ready to use!")
        print("Generate videos through the main API to see transitions in action.")
        
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 