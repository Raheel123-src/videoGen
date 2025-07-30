#!/bin/bash

echo "🚀 Quick Modal Deployment Script"
echo "================================"

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

echo "✅ Modal CLI ready"

# Check if secret exists
if ! modal secret list | grep -q "VideoGenSecret"; then
    echo "❌ VideoGenSecret not found!"
    echo ""
    echo "Please create the secret first:"
    echo "modal secret create VideoGenSecret \\"
    echo "  OPENAI_API_KEY=your_openai_api_key \\"
    echo "  ELEVENLABS_API_KEY=your_elevenlabs_api_key \\"
    echo "  ELEVENLABS_VOICE_ID=ftDdhfYtmfGP0tFlBYA1 \\"
    echo "  AWS_ACCESS_KEY_ID=your_aws_access_key_id \\"
    echo "  AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key \\"
    echo "  AWS_DEFAULT_REGION=us-east-1 \\"
    echo "  S3_BUCKET_NAME=your_s3_bucket_name \\"
    echo "  IDEOGRAM_API_KEY=your_ideogram_api_key \\"
    echo "  HEYGEN_API_KEY=your_heygen_api_key"
    exit 1
fi

echo "✅ VideoGenSecret found"

# Deploy the application
echo "🚀 Deploying to Modal with GPU L4..."
modal deploy modal_app.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment successful!"
    echo ""
    echo "🌐 Your deployment URL:"
    modal app videogen3-gpu-fastapi
    echo ""
    echo "📊 Monitor your deployment:"
    echo "modal logs videogen3-gpu-fastapi"
    echo ""
    echo "🧪 Test your deployment:"
    echo "curl -X POST \"https://your-modal-url.modal.run/process_and_generate_video\" \\"
    echo "  -F \"script=Welcome to our comprehensive guide on artificial intelligence and machine learning.\" \\"
    echo "  -F \"video_name=test_video\" \\"
    echo "  -F \"target_audience=tech startup office\" \\"
    echo "  -F \"show_subtitles=true\""
    echo ""
    echo "🎉 Deployment complete! Your app is now live on Modal with GPU acceleration."
else
    echo "❌ Deployment failed!"
    echo "Check the logs above for errors."
    exit 1
fi 