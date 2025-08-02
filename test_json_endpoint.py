#!/usr/bin/env python3
"""
Test script for the new JSON endpoint
"""

import requests
import json
import time

def test_json_endpoint():
    """Test the new JSON endpoint with a simple request"""
    
    # Test URL
    url = "https://d6ff64283580.ngrok-free.app/process_and_generate_video_json"
    
    # Test payload - only video_name (should fail validation)
    payload = {
        "video_name": "test_json_endpoint",
        "script": None,
        "audio_url": None,
        "speed": None,
        "voice_id": None,
        "stability": None,
        "similarity_boost": None,
        "show_subtitles": "true",
        "target_audience": None,
        "has_heygen": False,
        "bgm_volume": 50,
        "bgm_crossfade": 2000
    }
    
    print("🧪 Testing JSON endpoint with invalid request (no audio input)...")
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            session_id = response.json().get("session_id")
            print(f"✅ JSON endpoint accepted request. Session ID: {session_id}")
            
            # Wait a moment and check status
            time.sleep(2)
            status_url = f"https://d6ff64283580.ngrok-free.app/video_status?session_id={session_id}"
            status_response = requests.get(status_url)
            print(f"Status Check: {status_response.json()}")
            
        else:
            print(f"❌ JSON endpoint failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing JSON endpoint: {e}")

def test_json_endpoint_with_script():
    """Test the JSON endpoint with a valid script"""
    
    url = "https://d6ff64283580.ngrok-free.app/process_and_generate_video_json"
    
    payload = {
        "video_name": "test_json_script",
        "script": "Hello, this is a test script for the JSON endpoint. We are testing if the new JSON API works correctly.",
        "audio_url": None,
        "speed": 1.0,
        "voice_id": "ftDdhfYtmfGP0tFlBYA1",
        "stability": 0.35,
        "similarity_boost": 0.40,
        "show_subtitles": "true",
        "target_audience": "Professional",
        "has_heygen": False,
        "bgm_volume": 50,
        "bgm_crossfade": 2000
    }
    
    print("\n🧪 Testing JSON endpoint with valid script...")
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            session_id = response.json().get("session_id")
            print(f"✅ JSON endpoint accepted valid request. Session ID: {session_id}")
        else:
            print(f"❌ JSON endpoint failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing JSON endpoint: {e}")

if __name__ == "__main__":
    print("🚀 Testing new JSON endpoint...")
    test_json_endpoint()
    test_json_endpoint_with_script()
    print("\n✅ JSON endpoint testing completed!") 