#!/usr/bin/env python3

import os
import sys
import subprocess

def check_dependencies():
    """Check if all required dependencies and files exist"""
    print("🔍 Checking dependencies...")
    
    # Check if background image exists
    if not os.path.exists("background/1.jpg"):
        print("❌ Background image not found: background/1.jpg")
        print("Please ensure 1.jpg exists in the background folder")
        return False
    
    # Check if CSV folder exists
    if not os.path.exists("bulk_csv"):
        print("❌ CSV folder not found: bulk_csv")
        print("Please create the bulk_csv folder and add your CSV files")
        return False
    
    # Check if required scripts exist
    required_scripts = [
        "generate_images_ideogram_optimized.py",
        "gpt_highlight_bullets.py",
        "app.py"
    ]
    
    for script in required_scripts:
        if not os.path.exists(script):
            print(f"❌ Required script not found: {script}")
            return False
    
    # Check if virtual environment exists
    if not os.path.exists("venv"):
        print("❌ Virtual environment not found: venv")
        print("Please create a virtual environment first")
        return False
    
    print("✅ All dependencies found")
    return True

def setup_directories():
    """Create necessary directories"""
    print("📁 Setting up directories...")
    
    directories = [
        "uploads/Course",
        "segments",
        "transcripts",
        "generated_images_ideogram"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Created: {directory}")

def main():
    print("🚀 Bulk Video Generator")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Setup incomplete. Please fix the issues above.")
        return
    
    # Setup directories
    setup_directories()
    
    print("\n🎬 Starting bulk video generation...")
    print("This will process all CSV files in the bulk_csv folder")
    print("Videos will be saved to uploads/Course/[CourseName]/[TopicName].mp4")
    print("CSV status will be updated as videos are completed")
    print("\n" + "=" * 50)
    
    # Run the bulk generator
    try:
        result = subprocess.run([sys.executable, "bulk_video_generator.py"], 
                              check=True, text=True)
        print("\n🎉 Bulk generation completed successfully!")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Bulk generation failed: {e}")
        print("Check the error messages above for details")
        
    except KeyboardInterrupt:
        print("\n⏹️ Bulk generation interrupted by user")
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main() 