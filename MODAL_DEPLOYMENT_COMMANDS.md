# 🚀 Modal Deployment Commands & Guide

## ✅ **Modal App Status: READY FOR DEPLOYMENT**

The `modal_app.py` has been updated and is ready for deployment with the latest changes including:
- ✅ Audio duration fix
- ✅ HeyGen avatar bullet count rule (skip if > 4 bullets)
- ✅ Optimized file inclusion (only necessary files)
- ✅ GPU L4 configuration

## 🔧 **Pre-Deployment Checklist**

### **1. Install Modal CLI**
```bash
pip install modal
```

### **2. Authenticate with Modal**
```bash
modal token new
```

### **3. Set Up Modal Secrets**

First, create the secret with all required API keys:

```bash
modal secret create VideoGenSecret \
  OPENAI_API_KEY=your_openai_api_key \
  ELEVENLABS_API_KEY=your_elevenlabs_api_key \
  ELEVENLABS_VOICE_ID=ftDdhfYtmfGP0tFlBYA1 \
  AWS_ACCESS_KEY_ID=your_aws_access_key_id \
  AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key \
  AWS_DEFAULT_REGION=us-east-1 \
  S3_BUCKET_NAME=your_s3_bucket_name \
  IDEOGRAM_API_KEY=your_ideogram_api_key \
  HEYGEN_API_KEY=your_heygen_api_key
```

**Required API Keys:**
- ✅ **OpenAI API Key** - For transcription and GPT corrections
- ✅ **ElevenLabs API Key** - For text-to-speech generation
- ✅ **Ideogram API Key** - For image generation (optional)
- ✅ **HeyGen API Key** - For avatar videos (optional)
- ✅ **AWS S3 Keys** - For video storage (optional)

### **4. Verify Secret Creation**
```bash
modal secret list
```

## 🚀 **Deployment Commands**

### **Option 1: Deploy Using Modal CLI**
```bash
# Navigate to your project directory
cd /path/to/videoGen

# Deploy the application
modal deploy modal_app.py
```

### **Option 2: Deploy Using Shell Script**
```bash
# Make the script executable
chmod +x deploy_modal_gpu.sh

# Run the deployment script
./deploy_modal_gpu.sh
```

### **Option 3: Deploy with Custom Name**
```bash
modal deploy modal_app.py --name videogen3-gpu-fastapi
```

## 📊 **Post-Deployment Commands**

### **1. Check Deployment Status**
```bash
# List all your apps
modal app list

# Get specific app details
modal app videogen3-gpu-fastapi
```

### **2. Monitor Logs**
```bash
# View real-time logs
modal logs videogen3-gpu-fastapi

# View logs for specific function
modal logs videogen3-gpu-fastapi --function fastapi_app
```

### **3. Test the Deployment**
```bash
# Get your deployment URL
modal app videogen3-gpu-fastapi

# Test with curl
curl -X POST "https://your-modal-url.modal.run/process_and_generate_video" \
  -F "script=Welcome to our comprehensive guide on artificial intelligence and machine learning." \
  -F "video_name=test_video" \
  -F "target_audience=tech startup office" \
  -F "show_subtitles=true"
```

## 🔍 **Troubleshooting Commands**

### **1. Check Secret Configuration**
```bash
# List all secrets
modal secret list

# Check specific secret
modal secret get VideoGenSecret
```

### **2. Debug Deployment Issues**
```bash
# View detailed logs
modal logs videogen3-gpu-fastapi --tail 100

# Check function status
modal function list
```

### **3. Redeploy if Needed**
```bash
# Force redeploy
modal deploy modal_app.py --force

# Deploy with different name
modal deploy modal_app.py --name videogen3-gpu-fastapi-v2
```

## 🎯 **Configuration Details**

### **GPU Configuration:**
- ✅ **GPU:** L4 (High performance)
- ✅ **CPU:** 16 cores
- ✅ **Memory:** 32GB RAM
- ✅ **Concurrency:** Up to 20 concurrent sessions
- ✅ **Timeout:** 15 minutes per request

### **Environment Variables:**
- ✅ **GPU Enabled:** `MOVIEPY_USE_GPU=1`
- ✅ **FFmpeg GPU:** `FFMPEG_GPU=1`
- ✅ **CUDA Device:** `CUDA_VISIBLE_DEVICES=0`

## 📁 **Files Included in Deployment**

### **Core Application:**
- ✅ `mainModel.py` - Main FastAPI application
- ✅ `video_generator.py` - Video generation engine
- ✅ `bgm_processor.py` - Background music processor
- ✅ `heygen_empty_spaces.json` - HeyGen configuration

### **Static Assets:**
- ✅ `background/` - Background images
- ✅ `BGM/` - Background music files
- ✅ `circular-std-font-family/` - Font files
- ✅ `uploads/` - Upload directory
- ✅ `transcripts/` - Transcript directory
- ✅ `segments/` - Video segments
- ✅ `generated_images_ideogram/` - Generated images

## 🧪 **Testing Commands**

### **1. Test API Endpoints**
```bash
# Test video generation
curl -X POST "https://your-modal-url.modal.run/process_and_generate_video" \
  -F "script=This is a test video about artificial intelligence." \
  -F "video_name=test_ai_video" \
  -F "target_audience=tech professionals" \
  -F "show_subtitles=true"

# Check status
curl "https://your-modal-url.modal.run/video_status?session_id=your_session_id"

# Get results
curl "https://your-modal-url.modal.run/session_result/your_session_id"
```

### **2. Test with Different Parameters**
```bash
# Test with HeyGen avatar
curl -X POST "https://your-modal-url.modal.run/process_and_generate_video" \
  -F "script=Welcome to our comprehensive guide on machine learning." \
  -F "video_name=ml_guide" \
  -F "target_audience=data scientists" \
  -F "heygen_avatar_id=Jocelyn_sitting_office_side" \
  -F "bgm_volume=60" \
  -F "show_subtitles=true"
```

## 🚨 **Common Issues & Solutions**

### **1. Secret Not Found**
```bash
# Recreate secret
modal secret delete VideoGenSecret
modal secret create VideoGenSecret [your_keys]
```

### **2. Deployment Fails**
```bash
# Check logs
modal logs videogen3-gpu-fastapi --tail 50

# Redeploy with force
modal deploy modal_app.py --force
```

### **3. GPU Not Available**
```bash
# Check GPU availability
modal function list

# Try different GPU
# Edit modal_app.py to use gpu="T4" instead of "L4"
```

## 📈 **Monitoring & Scaling**

### **1. Monitor Usage**
```bash
# View app metrics
modal app videogen3-gpu-fastapi

# Check function calls
modal function list
```

### **2. Scale if Needed**
```bash
# The app automatically scales with @modal.concurrent(max_inputs=20)
# No manual scaling needed
```

## ✅ **Success Indicators**

Your deployment is successful when:
- ✅ Modal CLI shows deployment URL
- ✅ API endpoints respond to requests
- ✅ Video generation completes successfully
- ✅ GPU resources are utilized
- ✅ Logs show no critical errors

## 🎉 **Ready to Deploy!**

Your `modal_app.py` is fully configured and ready for deployment. Run the deployment commands above to get your application live on Modal with GPU acceleration! 