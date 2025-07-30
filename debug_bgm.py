#!/usr/bin/env python3
"""
Debug BGM Status
Quick script to check BGM configuration and show expected logs
"""

import os
import sys

def check_bgm_files():
    """Check if BGM files exist"""
    print("🔍 Checking BGM Files...")
    print("=" * 40)
    
    bgm_dir = "BGM"
    if not os.path.exists(bgm_dir):
        print("❌ BGM directory not found!")
        return False
    
    print(f"✅ BGM directory found: {bgm_dir}")
    
    theme_folders = {
        "Hook": "Start HOOK",
        "What": "WHAT", 
        "Why": "WHY",
        "How": "HOW",
        "Ending Hook": "End HOOK"
    }
    
    all_files_exist = True
    for theme, folder in theme_folders.items():
        folder_path = os.path.join(bgm_dir, folder)
        if os.path.exists(folder_path):
            files = [f for f in os.listdir(folder_path) if f.endswith('.mp3')]
            if files:
                total_size = sum(os.path.getsize(os.path.join(folder_path, f)) for f in files) / (1024 * 1024)
                print(f"✅ {theme}: {folder} ({len(files)} files, {total_size:.1f} MB)")
            else:
                print(f"❌ {theme}: {folder} (no MP3 files)")
                all_files_exist = False
        else:
            print(f"❌ {theme}: {folder} (folder not found)")
            all_files_exist = False
    
    return all_files_exist

def check_bgm_processor():
    """Test BGM processor initialization"""
    print("\n🔧 Testing BGM Processor...")
    print("=" * 40)
    
    try:
        from bgm_processor import BGMProcessor
        processor = BGMProcessor()
        print("✅ BGM processor initialized successfully")
        
        # Test getting a BGM file
        bgm_file = processor.get_random_bgm_file("Hook")
        if bgm_file and os.path.exists(bgm_file):
            print(f"✅ Test BGM file: {os.path.basename(bgm_file)}")
            return True
        else:
            print("❌ Could not get test BGM file")
            return False
            
    except Exception as e:
        print(f"❌ BGM processor test failed: {e}")
        return False

def check_main_model_integration():
    """Check if BGM is properly integrated in mainModel"""
    print("\n🔗 Checking MainModel Integration...")
    print("=" * 40)
    
    try:
        from mainModel import process_bgm_audio
        print("✅ process_bgm_audio function imported successfully")
        
        # Check if BGM parameters are in the API endpoint
        import inspect
        from mainModel import process_and_generate_video
        
        sig = inspect.signature(process_and_generate_video)
        params = list(sig.parameters.keys())
        
        if 'bgm_volume' in params and 'bgm_crossfade' in params:
            print("✅ BGM parameters found in API endpoint")
            return True
        else:
            print("❌ BGM parameters missing from API endpoint")
            return False
            
    except Exception as e:
        print(f"❌ MainModel integration check failed: {e}")
        return False

def show_expected_logs():
    """Show what BGM logs should look like"""
    print("\n📋 Expected BGM Logs...")
    print("=" * 40)
    
    print("🔍 When BGM is working, you should see these logs:")
    print()
    print("1. [COMBINED API] Starting BGM processing...")
    print("2. [BGM] Starting BGM processing...")
    print("3. [BGM] Loaded X segments from segments.json")
    print("4. [BGM] Loaded X transcription segments")
    print("5. [BGM] Selected BGM for Hook: Curious_Thoughts.mp3")
    print("6. [BGM] Starting BGM overlay with volume: 80, crossfade: 2.0s")
    print("7. [BGM] Original audio duration: X.X seconds")
    print("8. [BGM] Loaded BGM file: BGM/Start HOOK/Curious_Thoughts.mp3")
    print("9. [BGM] Adjusted BGM volume to -10.0dB (volume setting: 80)")
    print("10. [BGM] Added BGM for segment 0 from 0.0s to X.Xs")
    print("11. [BGM] Mixing original audio with BGM overlay...")
    print("12. [BGM] BGM overlay completed: path/to/file_bgm.mp3")
    print("13. [COMBINED API] BGM processing completed, using: path/to/file_bgm.mp3")
    print()
    print("❌ If BGM fails, you'll see:")
    print("   [COMBINED API] BGM processing failed, using original audio: [error]")

def show_test_command():
    """Show how to test BGM with API"""
    print("\n🧪 Testing BGM with API...")
    print("=" * 40)
    
    print("Use this curl command to test BGM:")
    print()
    print('curl -X POST "http://localhost:8080/process_and_generate_video" \\')
    print('  -F "script=Hello, this is a test script for BGM processing." \\')
    print('  -F "video_name=test_bgm_debug" \\')
    print('  -F "bgm_volume=80" \\')
    print('  -F "bgm_crossfade=2000"')
    print()
    print("💡 Key points:")
    print("   - Use bgm_volume=80 or higher for audible BGM")
    print("   - Check console logs for BGM processing messages")
    print("   - Look for '_bgm' suffix in processed audio files")

def main():
    """Run all BGM debug checks"""
    print("🚀 BGM Debug Check")
    print("=" * 60)
    
    checks_passed = 0
    total_checks = 0
    
    # Check 1: BGM files
    total_checks += 1
    if check_bgm_files():
        checks_passed += 1
        print("✅ BGM files check PASSED")
    else:
        print("❌ BGM files check FAILED")
    
    # Check 2: BGM processor
    total_checks += 1
    if check_bgm_processor():
        checks_passed += 1
        print("✅ BGM processor check PASSED")
    else:
        print("❌ BGM processor check FAILED")
    
    # Check 3: MainModel integration
    total_checks += 1
    if check_main_model_integration():
        checks_passed += 1
        print("✅ MainModel integration check PASSED")
    else:
        print("❌ MainModel integration check FAILED")
    
    # Show additional information
    show_expected_logs()
    show_test_command()
    
    print("\n" + "=" * 60)
    print("📊 Debug Results:")
    print(f"   Checks Passed: {checks_passed}/{total_checks}")
    
    if checks_passed == total_checks:
        print("\n🎉 ALL BGM CHECKS PASSED!")
        print("✅ BGM should be working correctly")
        print("💡 If you're not hearing BGM:")
        print("   1. Check console logs for BGM messages")
        print("   2. Try increasing bgm_volume to 80-90")
        print("   3. Look for '_bgm' suffix in audio files")
    else:
        print("\n❌ Some BGM checks failed")
        print("🔧 Fix the issues above before testing")
    
    return checks_passed == total_checks

if __name__ == "__main__":
    main() 