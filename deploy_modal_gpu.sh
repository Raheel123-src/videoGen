#!/bin/bash

echo "🚀 Deploying VideoGen2 with GPU T4 to Modal..."

# Check if Modal CLI is installed
if ! command -v modal &> /dev/null; then
    echo "❌ Modal CLI not found. Installing..."
    pip install modal
fi

# Check if user is authenticated
if ! modal token list &> /dev/null; then
    echo "🔐 Please authenticate with Modal first:"
    echo "modal token new"
    exit 1
fi

echo "📋 Checking Modal secrets..."
if ! modal secret list | grep -q "VideoGenSecret"; then
    echo "❌ VideoGenSecret not found. Please create it first:"
    echo "modal secret create VideoGenSecret \\"
    echo "  OPENAI_API_KEY=your_openai_api_key \\"
    echo "  ELEVENLABS_API_KEY=your_elevenlabs_api_key \\"
    echo "  ELEVENLABS_VOICE_ID=ftDdhfYtmfGP0tFlBYA1 \\"
    echo "  AWS_ACCESS_KEY_ID=your_aws_access_key_id \\"
    echo "  AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key \\"
    echo "  AWS_DEFAULT_REGION=us-east-1 \\"
    echo "  S3_BUCKET_NAME=your_s3_bucket_name \\"
    echo "  IDEOGRAM_API_KEY=your_ideogram_api_key"
    exit 1
fi

echo "✅ VideoGenSecret found"

echo "🔧 Deploying to Modal with GPU T4..."
modal deploy modal_app.py

if [ $? -eq 0 ]; then
    echo "✅ Deployment successful!"
    echo ""
    echo "🌐 Your deployment URL:"
    modal app videogen2-gpu-fastapi
    echo ""
    echo "📊 Monitor your deployment:"
    echo "modal logs videogen2-gpu-fastapi"
    echo ""
    echo "🧪 Test your deployment:"
    echo "curl -X POST \"https://your-modal-url.modal.run/process_and_generate_video\" \\"
    echo "  -F \"script=Welcome to our comprehensive guide on artificial intelligence and machine learning.\" \\"
    echo "  -F \"video_name=test_video\" \\"
    echo "  -F \"target_audience=tech startup office\" \\"
    echo "  -F \"show_subtitles=true\""
else
    echo "❌ Deployment failed!"
    exit 1
fi 