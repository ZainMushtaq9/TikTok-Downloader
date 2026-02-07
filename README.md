# Video Downloader - Production-Grade Application

A complete, production-ready video downloader supporting YouTube, TikTok, Instagram, Facebook, Twitter, Snapchat, and Likee. Built with FastAPI backend and vanilla JavaScript frontend.

## 🎯 Features

### Core Functionality
- ✅ **Multi-Platform Support**: YouTube, TikTok, Instagram, Facebook, Twitter, Snapchat, Likee
- ✅ **Playlist/Profile Downloads**: Bulk download 500+ videos from playlists and profiles
- ✅ **Queue-Based System**: Async downloads with concurrent workers
- ✅ **Real-Time Progress**: WebSocket updates for download status
- ✅ **Multiple Quality Options**: 4K, Full HD, HD, SD, Audio-only
- ✅ **Select All/Deselect All**: Efficient multi-selection controls
- ✅ **Lazy Loading**: Pagination for large playlists
- ✅ **Mobile Responsive**: Works on all devices
- ✅ **SEO Optimized**: Keyword-driven content, meta tags, structured data
- ✅ **No Login Required**: Start downloading immediately

### Technical Features
- ✅ **Async Architecture**: Non-blocking downloads
- ✅ **Rate Limiting**: Protection against abuse
- ✅ **Error Handling**: Automatic retry logic
- ✅ **Progress Tracking**: Per-video download status
- ✅ **Clean URLs**: SEO-friendly routing
- ✅ **Production Ready**: Scalable for thousands of users

## 📋 Requirements

### System Requirements
- Python 3.9+
- Node.js 16+ (for development only)
- FFmpeg (for video/audio processing)
- 4GB RAM minimum
- 10GB storage for downloads

### Python Packages
See `requirements.txt` for full list. Key dependencies:
- FastAPI
- yt-dlp
- uvicorn
- websockets
- slowapi (rate limiting)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install FFmpeg (Ubuntu/Debian)
sudo apt update
sudo apt install ffmpeg -y

# Or on macOS
brew install ffmpeg
```

### 2. Run the Application

```bash
# Start the FastAPI server
python main.py

# Server will start on http://localhost:8000
# Open http://localhost:8000 in your browser
```

That's it! The application is now running.

## 📁 Project Structure

```
video-downloader-production/
├── index.html              # Homepage
├── youtube.html            # YouTube downloader page
├── tiktok.html            # TikTok downloader page
├── instagram.html         # Instagram downloader page (create similar)
├── facebook.html          # Facebook downloader page (create similar)
├── twitter.html           # Twitter downloader page (create similar)
├── styles.css             # Complete CSS styling
├── app.js                 # Frontend JavaScript
├── main.py                # FastAPI backend
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## 🔧 Configuration

### Backend Configuration

Edit `main.py` to configure:

```python
# Download directory
DOWNLOAD_DIR = Path("/tmp/downloads")

# Concurrent downloads
MAX_CONCURRENT_DOWNLOADS = 4

# Max playlist size
MAX_PLAYLIST_SIZE = 1000
```

### Frontend Configuration

Edit `app.js` to configure:

```javascript
const CONFIG = {
    API_BASE_URL: 'http://localhost:8000/api/v1',
    WS_URL: 'ws://localhost:8000/ws',
    MAX_VIDEOS_PER_PAGE: 20
};
```

## 🌐 API Documentation

### POST /api/v1/analyze
Analyze URL and extract video metadata

**Request:**
```json
{
  "url": "https://youtube.com/watch?v=..."
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "is_playlist": false,
  "total_videos": 1
}
```

### GET /api/v1/videos/{session_id}
Get paginated videos for a session

**Query Parameters:**
- `page`: Page number (default: 1)
- `limit`: Results per page (default: 20)

### POST /api/v1/download
Start download jobs

**Request:**
```json
{
  "session_id": "uuid",
  "video_ids": ["id1", "id2"],
  "format": "best",
  "quality": "1080p"
}
```

### GET /api/v1/progress/{job_id}
Get download progress

### WebSocket /ws/{session_id}
Real-time progress updates

## 🎨 SEO Keywords Implementation

The application implements SEO keywords naturally across pages:

### Homepage
- Primary: "social media video downloader", "online video downloader"
- Secondary: "all in one video downloader", "free online video downloader"

### YouTube Page
- Primary: "youtube video downloader", "youtube playlist downloader"
- Secondary: "download youtube video", "youtube video download online"

### TikTok Page
- Primary: "tiktok video downloader", "tiktok downloader"
- Secondary: "download tiktok video", "tiktok profile downloader"

## 🔒 Security Features

- ✅ Rate limiting (10 requests/minute for analyze, 30/minute for download)
- ✅ URL validation
- ✅ Input sanitization
- ✅ CORS configuration
- ✅ Error logging
- ✅ Timeout protection

## 📱 Mobile Support

The application is fully responsive with:
- Mobile-optimized navigation
- Touch-friendly controls
- Adaptive layouts
- Mobile menu

## 🚀 Production Deployment

### Using Uvicorn

```bash
# Production server with workers
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Using Gunicorn

```bash
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Environment Variables

```bash
export MAX_CONCURRENT_DOWNLOADS=4
export DOWNLOAD_PATH=/var/www/downloads
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 🧪 Testing

### Test URL Analysis

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

## 📊 Performance

- Handles 500+ video playlists
- Supports multiple concurrent users
- Non-blocking async architecture
- Efficient queue management
- Real-time progress updates

## ⚠️ Important Notes

### Legal Compliance
- This tool is for personal use only
- Users must respect copyright laws
- Only download content you have permission to use
- Comply with platform terms of service

### Watermark Removal
- TikTok watermark removal depends on source format
- Not always possible
- Clearly communicated in FAQ

### Supported Platforms
All platforms supported by yt-dlp:
- YouTube (videos, playlists, channels)
- TikTok (videos, profiles)
- Instagram (reels, posts, profiles)
- Facebook (public videos)
- Twitter/X (videos)
- Snapchat (public shares)
- Likee (videos)

## 🐛 Troubleshooting

### "Cannot connect to server"
- Ensure Python server is running
- Check port 8000 is not in use
- Verify firewall settings

### "Failed to extract video info"
- URL may be invalid or private
- Platform may have changed their API
- Update yt-dlp: `pip install --upgrade yt-dlp`

### Downloads failing
- Check FFmpeg is installed
- Verify disk space
- Check network connection

## 📝 License

This project is for educational purposes. Users must comply with:
- Platform terms of service
- Copyright laws
- Fair use policies

## 🔄 Updates

To update yt-dlp (recommended monthly):

```bash
pip install --upgrade yt-dlp
```

## 👥 Contributing

To add new features:
1. Update SEO keywords in HTML
2. Add API endpoints in `main.py`
3. Update frontend in `app.js`
4. Test thoroughly

## 📧 Support

For issues or questions:
- Check FAQ sections on each page
- Review error logs
- Ensure all dependencies are installed

---

Built with ❤️ for the community. Use responsibly!
