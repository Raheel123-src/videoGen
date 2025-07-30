#!/usr/bin/env python3
"""
Deploy and test Modal GPU video generation
"""

import subprocess
import time
import requests
import json

def deploy_to_modal():
    """Deploy the app to Modal"""
    print("🚀 Deploying to Modal...")
    try:
        result = subprocess.run(
            ["modal", "deploy", "modal_app.py"],
            capture_output=True,
            text=True,
            check=True
        )
        print("✅ Deployment successful!")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print("❌ Deployment failed!")
        print(f"Error: {e.stderr}")
        return False

def get_modal_endpoint():
    """Get the Modal endpoint URL"""
    try:
        result = subprocess.run(
            ["modal", "app", "list"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the output to find the endpoint
        lines = result.stdout.split('\n')
        for line in lines:
            if 'videogen2-gpu-fastapi' in line and 'https://' in line:
                # Extract the URL
                url = line.split()[-1]
                return url.strip()
        
        return None
    except subprocess.CalledProcessError as e:
        print(f"❌ Could not get endpoint: {e.stderr}")
        return None

def test_gpu_endpoint(base_url):
    """Test the GPU video generation endpoint"""
    print(f"🧪 Testing GPU video generation at: {base_url}")
    
    test_url = f"{base_url}/test_gpu_video_generation"
    
    try:
        print("📡 Making request to GPU test endpoint...")
        response = requests.get(test_url, timeout=60)  # 60 second timeout
        
        if response.status_code == 200:
            result = response.json()
            print("✅ GPU test completed!")
            print(f"📊 Result: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"❌ GPU test failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("⏰ GPU test timed out (60 seconds)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ GPU test request failed: {e}")
        return None

def test_video_generation(base_url):
    """Test the actual video generation endpoint"""
    print(f"🎬 Testing actual video generation at: {base_url}")
    
    # Test data for video generation
    test_data = {
        "script": "Hello, this is a test video generation. We are testing GPU acceleration on Modal L4.",
        "video_name": "GPU_Test_Video",
        "show_subtitles": "true",
        "target_audience": "test"
    }
    
    try:
        print("📡 Making request to video generation endpoint...")
        response = requests.post(
            f"{base_url}/process_and_generate_video",
            data=test_data,
            timeout=300  # 5 minute timeout for video generation
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Video generation request successful!")
            print(f"📊 Result: {json.dumps(result, indent=2)}")
            
            if 'session_id' in result:
                session_id = result['session_id']
                print(f"🔄 Checking status for session: {session_id}")
                
                # Poll for completion
                for i in range(30):  # Wait up to 5 minutes
                    time.sleep(10)
                    status_response = requests.get(f"{base_url}/video_status?session_id={session_id}")
                    
                    if status_response.status_code == 200:
                        status_result = status_response.json()
                        print(f"📊 Status check {i+1}: {status_result['status']}")
                        
                        if status_result['status'] == 'done':
                            print("🎉 Video generation completed successfully!")
                            return status_result
                        elif status_result['status'] == 'error':
                            print(f"❌ Video generation failed: {status_result.get('error', 'Unknown error')}")
                            return status_result
                
                print("⏰ Video generation timed out")
                return None
            else:
                print("❌ No session_id in response")
                return result
        else:
            print(f"❌ Video generation failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("⏰ Video generation timed out (5 minutes)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Video generation request failed: {e}")
        return None

def main():
    """Main deployment and testing function"""
    print("🎯 Modal GPU Video Generation Test")
    print("=" * 50)
    
    # Step 1: Deploy to Modal
    if not deploy_to_modal():
        print("❌ Deployment failed, exiting...")
        return
    
    # Step 2: Get endpoint
    print("\n🔍 Getting Modal endpoint...")
    endpoint = get_modal_endpoint()
    if not endpoint:
        print("❌ Could not get endpoint, exiting...")
        return
    
    print(f"✅ Endpoint found: {endpoint}")
    
    # Step 3: Test GPU video generation
    print("\n🧪 Testing GPU video generation...")
    gpu_result = test_gpu_endpoint(endpoint)
    
    if gpu_result and gpu_result.get('success'):
        print("✅ GPU test passed!")
        
        # Step 4: Test actual video generation
        print("\n🎬 Testing actual video generation...")
        video_result = test_video_generation(endpoint)
        
        if video_result:
            print("✅ All tests completed!")
        else:
            print("❌ Video generation test failed")
    else:
        print("❌ GPU test failed")
        if gpu_result:
            print(f"Error: {gpu_result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    main() 