# VideoGen2 Modal Deployment Guide

## 🚀 Quick Start

### 1. Install Modal CLI
```bash
pip install modal
```

### 2. Authenticate with Modal
```bash
modal token new
```

### 3. Set up Environment Variables

#### Option A: Using Modal Secrets (Recommended)
```bash
# Create a secret with all environment variables
modal secret create videogen2-env \
  OPENAI_API_KEY=your_openai_api_key \
  ELEVENLABS_API_KEY=your_elevenlabs_api_key \
  ELEVENLABS_VOICE_ID=ftDdhfYtmfGP0tFlBYA1 \
  AWS_ACCESS_KEY_ID=your_aws_access_key_id \
  AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key \
  AWS_DEFAULT_REGION=us-east-1 \
  S3_BUCKET_NAME=your_s3_bucket_name \
  IDEOGRAM_API_KEY=your_ideogram_api_key
```

#### Option B: Using .env file
1. Copy `env_template.txt` to `.env`
2. Fill in your actual API keys
3. Modal will automatically load the `.env` file

### 4. Deploy to Modal
```bash
modal deploy modal_app.py
```

### 5. Get Your Deployment URL
```bash
modal app videogen2-fastapi
```

## 📋 Required API Keys

### 1. OpenAI API Key
- **Purpose**: Transcript correction and GPT processing
- **Get it**: https://platform.openai.com/api-keys
- **Cost**: ~$0.01-0.05 per video (depending on transcript length)

### 2. ElevenLabs API Key
- **Purpose**: Text-to-speech audio generation
- **Get it**: https://elevenlabs.io/speech-synthesis
- **Cost**: ~$0.01-0.03 per video (depending on audio length)

### 3. Ideogram API Key
- **Purpose**: AI image generation for slides
- **Get it**: https://ideogram.ai/
- **Cost**: ~$0.01-0.02 per video (depending on number of slides)

### 4. AWS S3 Configuration
- **Purpose**: Video storage and hosting
- **Get it**: https://aws.amazon.com/s3/
- **Cost**: ~$0.01-0.05 per video (depending on video size)

## 🔧 Configuration Options

### Voice Settings
You can customize the voice by changing these values:
- `ELEVENLABS_VOICE_ID`: Different voice options
- `STABILITY`: Voice stability (0.0-1.0)
- `SIMILARITY_BOOST`: Voice similarity (0.0-1.0)

### AWS S3 Settings
- `AWS_DEFAULT_REGION`: Your preferred AWS region
- `S3_BUCKET_NAME`: Your S3 bucket name

## 🧪 Testing Your Deployment

### Test with curl
```bash
curl -X POST "https://your-modal-url.modal.run/process_and_generate_video" \
  -F "script=Welcome to our comprehensive guide on artificial intelligence and machine learning. Today we'll explore the fascinating world of AI, from basic concepts to advanced applications." \
  -F "video_name=test_video" \
  -F "show_subtitles=true"
```

### Test with Python
```python
import requests

url = "https://your-modal-url.modal.run/process_and_generate_video"
data = {
    'script': 'Welcome to our comprehensive guide on artificial intelligence and machine learning.',
    'video_name': 'test_video',
    'show_subtitles': 'true'
}

response = requests.post(url, data=data)
print(response.json())
```

## 📊 Monitoring and Logs

### View Logs
```bash
modal logs videogen2-fastapi
```

### Monitor Usage
```bash
modal app videogen2-fastapi
```

## 🔄 Updating Your Deployment

### Update Code
```bash
modal deploy modal_app.py
```

### Update Environment Variables
```bash
modal secret update videogen2-env \
  OPENAI_API_KEY=new_openai_api_key
```

## 💰 Cost Optimization

### CPU-Only Deployment
- Uses 8 CPU cores efficiently
- No GPU costs
- Optimized for cost-effective processing

### Concurrent Processing
- Handles multiple requests simultaneously
- Session isolation prevents conflicts
- Automatic cleanup reduces storage costs

## 🛠️ Troubleshooting

### Common Issues

1. **Missing API Keys**
   - Check all environment variables are set
   - Verify API keys are valid and have sufficient credits

2. **S3 Upload Failures**
   - Verify AWS credentials
   - Check S3 bucket permissions
   - Ensure bucket exists in specified region

3. **Image Generation Failures**
   - Check Ideogram API key
   - Verify API credits are available

4. **Video Generation Issues**
   - Check ffmpeg installation (handled by Modal)
   - Verify background images exist

### Getting Help
- Check Modal logs: `modal logs videogen2-fastapi`
- Review application status: `modal app videogen2-fastapi`
- Check Modal documentation: https://modal.com/docs

## 🎯 Production Checklist

- [ ] All API keys configured
- [ ] S3 bucket created and accessible
- [ ] Deployment successful
- [ ] Test request completed
- [ ] Video generated and uploaded to S3
- [ ] Concurrent requests tested
- [ ] Monitoring set up

## 📈 Scaling

Your deployment automatically scales based on demand:
- **Concurrent requests**: Handled with session isolation
- **CPU utilization**: 8 cores efficiently utilized
- **Memory**: Optimized for video processing
- **Storage**: Temporary files automatically cleaned up 