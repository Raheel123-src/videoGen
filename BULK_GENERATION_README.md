# Bulk Video Generation System

This system automatically processes CSV files containing audio URLs and generates videos with the specified folder structure.

## 📁 Folder Structure

```
uploads/
└── Course/
    ├── Stress Management/
    │   ├── Early Signs of Stress.mp4
    │   ├── Acute vs. Chronic Stress.mp4
    │   └── ...
    ├── Emotional Intelligence/
    │   ├── intro.mp4
    │   ├── What is Emotional Intelligence?.mp4
    │   └── ...
    └── ...
```

## 📋 CSV Format

The CSV file should have the following columns:
- **Course**: Course name (e.g., "Stress Management")
- **Topic**: Topic name (e.g., "Early Signs of Stress")
- **Raw S3 URL**: Audio file URL
- **Status**: Leave empty for new entries, will be updated to "Done" when completed

Example:
```csv
Course,Topic,Raw S3 URL,Status
Stress Management,Early Signs of Stress,https://example.com/audio1.mp3,
Stress Management,Acute vs. Chronic Stress,https://example.com/audio2.mp3,
```

## 🚀 Usage

### 1. Prepare Your Files

1. **Place your CSV file** in the `bulk_csv/` folder
2. **Ensure `1.jpg` exists** in the `background/` folder (this will be used for all videos)
3. **Make sure your virtual environment is activated**

### 2. Run the Bulk Generator

```bash
# Option 1: Use the runner script (recommended)
python run_bulk_generation.py

# Option 2: Run directly
python bulk_video_generator.py
```

### 3. Monitor Progress

The system will:
- ✅ Process each row in the CSV
- ✅ Download audio from S3 URLs
- ✅ Transcribe audio using Whisper
- ✅ Generate slides with GPT-4o
- ✅ Create context-aware images with Ideogram
- ✅ Add highlight tags to slides
- ✅ Generate videos with synchronized audio and subtitles
- ✅ Save videos to `uploads/Course/[CourseName]/[TopicName].mp4`
- ✅ Update CSV status to "Done" when completed

## 📊 Features

### Automatic Processing
- **Skips completed videos** (rows with "Done" status)
- **Error handling** with status updates in CSV
- **Progress tracking** with detailed console output
- **Resume capability** - can restart and continue from where it left off

### Video Generation
- **Custom background**: Uses `1.jpg` for all videos
- **Subtitles enabled**: All videos include synchronized subtitles
- **Context-aware images**: Images match the content and tone of each topic
- **Professional quality**: High-resolution videos with smooth animations

### File Organization
- **Sanitized filenames**: Removes invalid characters for file system compatibility
- **Organized structure**: Videos grouped by course name
- **Consistent naming**: Topic names become video filenames

## 🔧 Configuration

### Background Image
- Place your background image as `background/1.jpg`
- This image will be used for all generated videos

### CSV Location
- Place CSV files in the `bulk_csv/` folder
- The system will process all `.csv` files in this folder

### Output Location
- Videos are saved to `uploads/Course/[CourseName]/[TopicName].mp4`
- Temporary files are created in `segments/` and `transcripts/` folders

## 📝 Status Tracking

The CSV file is automatically updated with status:
- **Empty**: Not processed yet
- **Done**: Successfully completed
- **Error: [message]**: Failed with error details

## ⚠️ Important Notes

1. **Internet Connection**: Required for downloading audio files and generating images
2. **API Keys**: Ensure your `.env` file has valid API keys for:
   - OpenAI (for transcription and slide generation)
   - Ideogram (for image generation)
3. **Storage Space**: Videos can be large, ensure sufficient disk space
4. **Processing Time**: Each video takes 2-5 minutes depending on audio length
5. **Rate Limits**: The system includes delays to respect API rate limits

## 🛠️ Troubleshooting

### Common Issues

1. **Background image not found**
   - Ensure `background/1.jpg` exists

2. **CSV folder not found**
   - Create the `bulk_csv/` folder and add your CSV files

3. **API errors**
   - Check your `.env` file for valid API keys
   - Ensure sufficient API credits

4. **Virtual environment issues**
   - Activate your virtual environment: `source venv/bin/activate`

### Error Recovery

- The system automatically updates CSV status on errors
- You can restart the process - it will skip completed videos
- Check console output for detailed error messages

## 📈 Performance Tips

1. **Batch Processing**: Process videos during off-peak hours
2. **Monitor Resources**: Ensure sufficient RAM and CPU for video processing
3. **Network**: Use stable internet connection for reliable downloads
4. **Storage**: Keep sufficient free space for temporary and final files

## 🎯 Example Output

After processing, your folder structure will look like:
```
uploads/
└── Course/
    ├── Stress Management/
    │   ├── Early Signs of Stress.mp4
    │   ├── Acute vs. Chronic Stress.mp4
    │   └── Stress and Productivity.mp4
    ├── Emotional Intelligence/
    │   ├── intro.mp4
    │   ├── What is Emotional Intelligence?.mp4
    │   └── Importance of Emotional Intelligence.mp4
    └── Effective Communication/
        ├── Crafting Clear Messages.mp4
        └── Effective Verbal Communication.mp4
```

Each video includes:
- ✅ Synchronized audio and subtitles
- ✅ Context-aware background images
- ✅ Professional slide animations
- ✅ Highlight effects on key points 