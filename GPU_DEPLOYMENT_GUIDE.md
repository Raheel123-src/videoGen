# VideoGen2 GPU Deployment Guide (Modal T4)

## 🚀 Quick Deployment

### 1. One-Click Deployment
```bash
./deploy_modal_gpu.sh
```

### 2. Manual Deployment
```bash
# Install Modal CLI
pip install modal

# Authenticate
modal token new

# Create secrets (if not exists)
modal secret create VideoGenSecret \
  OPENAI_API_KEY=your_openai_api_key \
  ELEVENLABS_API_KEY=your_elevenlabs_api_key \
  ELEVENLABS_VOICE_ID=ftDdhfYtmfGP0tFlBYA1 \
  AWS_ACCESS_KEY_ID=your_aws_access_key_id \
  AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key \
  AWS_DEFAULT_REGION=us-east-1 \
  S3_BUCKET_NAME=your_s3_bucket_name \
  IDEOGRAM_API_KEY=your_ideogram_api_key

# Deploy
modal deploy modal_app.py
```

## ⚡ GPU T4 Performance Features

### **Hardware Configuration**
- **GPU**: NVIDIA T4 (16GB VRAM)
- **CPU**: 16 cores (2x increase)
- **RAM**: 32GB (4x increase)
- **Concurrency**: 10 concurrent requests
- **Timeout**: 15 minutes per request

### **Performance Improvements**
- 🚀 **3-5x faster** image generation with GPU
- 🚀 **2-3x faster** video processing
- 🚀 **10 concurrent requests** (vs 1-2 before)
- 🚀 **Better memory management** for large videos

## 🧪 Testing with Target Audience

### **Test Different Environments**
```bash
# Manufacturing
curl -X POST "https://your-modal-url.modal.run/process_and_generate_video" \
  -F "script=Welcome to our comprehensive guide on quality control in manufacturing." \
  -F "video_name=manufacturing_guide" \
  -F "target_audience=manufacturing unit of phones" \
  -F "show_subtitles=true"

# Hospital
curl -X POST "https://your-modal-url.modal.run/process_and_generate_video" \
  -F "script=Today we'll discuss patient care and medical procedures." \
  -F "video_name=hospital_training" \
  -F "target_audience=hospital emergency room" \
  -F "show_subtitles=true"

# Sales Team
curl -X POST "https://your-modal-url.modal.run/process_and_generate_video" \
  -F "script=Let's explore effective sales techniques and customer engagement." \
  -F "video_name=sales_training" \
  -F "target_audience=sales team office" \
  -F "show_subtitles=true"

# Tech Startup
curl -X POST "https://your-modal-url.modal.run/process_and_generate_video" \
  -F "script=Welcome to our guide on artificial intelligence and machine learning." \
  -F "video_name=tech_guide" \
  -F "target_audience=tech startup office" \
  -F "show_subtitles=true"
```

## 📊 Monitoring

### **Check Deployment Status**
```bash
modal app videogen2-gpu-fastapi
```

### **View Logs**
```bash
modal logs videogen2-gpu-fastapi
```

### **Monitor GPU Usage**
```bash
modal logs videogen2-gpu-fastapi --follow
```

## 💰 Cost Considerations

### **GPU T4 Pricing**
- **Per hour**: ~$0.35-0.50/hour
- **Per video**: ~$0.05-0.15 (depending on length)
- **Concurrent processing**: More efficient for multiple requests

### **Cost Optimization**
- **Batch processing**: Process multiple videos together
- **Concurrent requests**: Utilize full GPU capacity
- **Auto-scaling**: Modal scales down when not in use

## 🔧 Troubleshooting

### **GPU Issues**
```bash
# Check GPU availability
modal logs videogen2-gpu-fastapi | grep -i gpu

# Restart deployment if needed
modal deploy modal_app.py --force
```

### **Memory Issues**
- GPU T4 has 16GB VRAM - sufficient for most video processing
- If issues occur, check logs for memory usage

### **Timeout Issues**
- Increased timeout to 15 minutes
- For very long videos, consider splitting into segments

## 🎯 Production Checklist

- [ ] GPU T4 deployment successful
- [ ] All API keys configured
- [ ] Target audience feature tested
- [ ] Concurrent requests tested
- [ ] Performance benchmarks met
- [ ] Cost monitoring set up

## 📈 Expected Performance

### **Image Generation**
- **Before**: 30-60 seconds per image
- **After**: 10-20 seconds per image (3x faster)

### **Video Processing**
- **Before**: 5-10 minutes per video
- **After**: 2-5 minutes per video (2-3x faster)

### **Concurrent Processing**
- **Before**: 1-2 requests at a time
- **After**: 10 requests simultaneously

## 🔄 Updates

### **Update Deployment**
```bash
modal deploy modal_app.py
```

### **Update Secrets**
```bash
modal secret update VideoGenSecret \
  OPENAI_API_KEY=new_key
```

## 🆕 New Features

### **Dynamic Target Audience**
- ✅ Environment-specific image generation
- ✅ Context-aware prompts
- ✅ Professional environment matching
- ✅ Cultural and industry-specific visuals

### **Enhanced Performance**
- ✅ GPU-accelerated processing
- ✅ Increased concurrency
- ✅ Better memory management
- ✅ Faster response times 