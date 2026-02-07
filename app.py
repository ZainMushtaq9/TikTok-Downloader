"""
Video Downloader - Production FastAPI Backend
Supports YouTube, TikTok, Instagram, Facebook, Twitter, Snapchat, Likee
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl, validator
from typing import List, Optional, Dict, Any
from enum import Enum
import yt_dlp
import asyncio
import uuid
import os
import re
import logging
from datetime import datetime
from pathlib import Path
import json
from collections import defaultdict
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ==========================================
# CONFIGURATION
# ==========================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "4"))
MAX_PLAYLIST_SIZE = 1000
RESULTS_PER_PAGE = 20

# ==========================================
# MODELS
# ==========================================
class Platform(str, Enum):
    YOUTUBE = "YouTube"
    TIKTOK = "TikTok"
    INSTAGRAM = "Instagram"
    FACEBOOK = "Facebook"
    TWITTER = "Twitter"
    SNAPCHAT = "Snapchat"
    LIKEE = "Likee"
    UNKNOWN = "Unknown"

class VideoFormat(str, Enum):
    BEST = "best"
    AUDIO = "audio"

class DownloadStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"

class AnalyzeRequest(BaseModel):
    url: str

    @validator('url')
    def validate_url(cls, v):
        if not v or not v.strip():
            raise ValueError("URL cannot be empty")
        # Basic URL validation
        if not re.match(r'https?://', v):
            raise ValueError("URL must start with http:// or https://")
        return v.strip()

class DownloadRequest(BaseModel):
    session_id: str
    video_ids: List[str]
    format: VideoFormat = VideoFormat.BEST
    quality: Optional[str] = None

class VideoInfo(BaseModel):
    id: str
    title: str
    thumbnail: str
    duration: Optional[int]
    platform: Platform
    url: str
    views: Optional[int] = None

class AnalyzeResponse(BaseModel):
    session_id: str
    is_playlist: bool
    total_videos: int
    playlist_title: Optional[str] = None

class VideosResponse(BaseModel):
    videos: List[VideoInfo]
    page: int
    has_more: bool

class DownloadJob(BaseModel):
    job_id: str
    video_id: str
    status: DownloadStatus

class DownloadResponse(BaseModel):
    jobs: List[DownloadJob]

class ProgressResponse(BaseModel):
    job_id: str
    status: DownloadStatus
    progress: int
    error: Optional[str] = None
    file_path: Optional[str] = None

# ==========================================
# APP INITIALIZATION
# ==========================================
app = FastAPI(
    title="Video Downloader API",
    description="Production-grade video downloader supporting multiple platforms",
    version="1.0.0"
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# IN-MEMORY STORAGE (Use Redis/PostgreSQL in production)
# ==========================================
sessions: Dict[str, Dict[str, Any]] = {}
download_queue = asyncio.Queue()
active_downloads: Dict[str, Dict[str, Any]] = {}
websocket_connections: Dict[str, List[WebSocket]] = defaultdict(list)

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def detect_platform(url: str) -> Platform:
    """Detect platform from URL"""
    url_lower = url.lower()
    
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return Platform.YOUTUBE
    elif 'tiktok.com' in url_lower:
        return Platform.TIKTOK
    elif 'instagram.com' in url_lower:
        return Platform.INSTAGRAM
    elif 'facebook.com' in url_lower or 'fb.watch' in url_lower:
        return Platform.FACEBOOK
    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
        return Platform.TWITTER
    elif 'snapchat.com' in url_lower:
        return Platform.SNAPCHAT
    elif 'likee.com' in url_lower or 'likee.video' in url_lower:
        return Platform.LIKEE
    else:
        return Platform.UNKNOWN

def sanitize_filename(filename: str) -> str:
    """Create SEO-safe filename"""
    # Remove special characters
    filename = re.sub(r'[^\w\s-]', '', filename)
    # Replace spaces with hyphens
    filename = re.sub(r'[-\s]+', '-', filename)
    return filename[:200]  # Limit length

def get_ydl_opts(format_type: VideoFormat = VideoFormat.BEST, quality: Optional[str] = None) -> dict:
    """Get yt-dlp options"""
    opts = {
        'quiet': False,
        'no_warnings': False,
        'extract_flat': False,
        'socket_timeout': 30,
    }

    if format_type == VideoFormat.AUDIO:
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    elif quality:
        # Specific quality
        opts['format'] = f'bestvideo[height<={quality[:-1]}]+bestaudio/best'
    else:
        # Best quality
        opts['format'] = 'bestvideo+bestaudio/best'

    return opts

async def extract_info(url: str, extract_flat: bool = True) -> dict:
    """Extract video information using yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': extract_flat,
        'socket_timeout': 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            return info
    except Exception as e:
        logger.error(f"Failed to extract info: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract video info: {str(e)}")

def parse_video_info(entry: dict, platform: Platform, url: str) -> VideoInfo:
    """Parse video information from yt-dlp entry"""
    video_id = entry.get('id', str(uuid.uuid4())[:8])
    
    return VideoInfo(
        id=video_id,
        title=entry.get('title', 'Unknown Title'),
        thumbnail=entry.get('thumbnail', ''),
        duration=entry.get('duration'),
        platform=platform,
        url=entry.get('webpage_url') or entry.get('url') or url,
        views=entry.get('view_count')
    )

async def notify_websocket(session_id: str, message: dict):
    """Send WebSocket notification to all connected clients"""
    connections = websocket_connections.get(session_id, [])
    dead_connections = []
    
    for ws in connections:
        try:
            await ws.send_json(message)
        except:
            dead_connections.append(ws)
    
    # Remove dead connections
    for ws in dead_connections:
        connections.remove(ws)

# ==========================================
# DOWNLOAD WORKER
# ==========================================
async def download_worker():
    """Background worker to process download queue"""
    while True:
        try:
            job = await download_queue.get()
            job_id = job['job_id']
            video = job['video']
            format_type = job['format']
            quality = job['quality']
            session_id = job['session_id']

            logger.info(f"Starting download job {job_id}")
            
            # Update status
            active_downloads[job_id]['status'] = DownloadStatus.DOWNLOADING
            await notify_websocket(session_id, {
                'type': 'progress',
                'job_id': job_id,
                'progress': 0
            })

            # Download
            try:
                file_path = await download_video(job_id, video, format_type, quality, session_id)
                
                # Mark complete
                active_downloads[job_id].update({
                    'status': DownloadStatus.COMPLETED,
                    'progress': 100,
                    'file_path': file_path
                })
                
                await notify_websocket(session_id, {
                    'type': 'complete',
                    'job_id': job_id,
                    'file_path': file_path
                })
                
                logger.info(f"Completed job {job_id}")

            except Exception as e:
                logger.error(f"Job {job_id} failed: {e}")
                active_downloads[job_id].update({
                    'status': DownloadStatus.FAILED,
                    'error': str(e)
                })
                
                await notify_websocket(session_id, {
                    'type': 'error',
                    'job_id': job_id,
                    'error': str(e)
                })

        except Exception as e:
            logger.error(f"Worker error: {e}")

async def download_video(job_id: str, video: VideoInfo, format_type: VideoFormat, 
                        quality: Optional[str], session_id: str) -> str:
    """Download a single video"""
    output_template = str(DOWNLOAD_DIR / f"{session_id}_{job_id}_%(title)s.%(ext)s")
    
    ydl_opts = get_ydl_opts(format_type, quality)
    ydl_opts['outtmpl'] = output_template
    ydl_opts['progress_hooks'] = [lambda d: progress_hook(d, job_id, session_id)]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        await asyncio.to_thread(ydl.download, [video.url])
    
    # Find downloaded file
    files = list(DOWNLOAD_DIR.glob(f"{session_id}_{job_id}_*"))
    if files:
        return f"/downloads/{files[0].name}"
    raise Exception("Download completed but file not found")

def progress_hook(d, job_id: str, session_id: str):
    """Progress callback for yt-dlp"""
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0%').strip('%')
        try:
            progress = int(float(percent))
            active_downloads[job_id]['progress'] = progress
            
            # Send WebSocket update (non-blocking)
            asyncio.create_task(notify_websocket(session_id, {
                'type': 'progress',
                'job_id': job_id,
                'progress': progress
            }))
        except:
            pass

# ==========================================
# API ENDPOINTS
# ==========================================
@app.on_event("startup")
async def startup_event():
    """Start background workers"""
    for _ in range(MAX_CONCURRENT_DOWNLOADS):
        asyncio.create_task(download_worker())
    logger.info(f"Started {MAX_CONCURRENT_DOWNLOADS} download workers")

@app.get("/")
async def root():
    return {"message": "Video Downloader API", "version": "1.0.0"}

@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "active_downloads": len([d for d in active_downloads.values() if d['status'] == DownloadStatus.DOWNLOADING]),
        "queued": download_queue.qsize()
    }

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
@limiter.limit("10/minute")
async def analyze_url(request: AnalyzeRequest, req: Any = None):
    """Analyze URL and extract video metadata"""
    url = request.url
    platform = detect_platform(url)
    
    logger.info(f"Analyzing URL: {url} (Platform: {platform})")
    
    try:
        # Extract info
        info = await extract_info(url, extract_flat=True)
        
        # Create session
        session_id = str(uuid.uuid4())
        
        # Check if playlist/channel
        is_playlist = '_type' in info and info['_type'] in ['playlist', 'multi_video']
        
        if is_playlist:
            # Playlist or channel
            entries = info.get('entries', [])
            videos = []
            
            for entry in entries[:MAX_PLAYLIST_SIZE]:
                try:
                    video = parse_video_info(entry, platform, url)
                    videos.append(video)
                except Exception as e:
                    logger.warning(f"Failed to parse video: {e}")
                    continue
            
            sessions[session_id] = {
                'url': url,
                'platform': platform,
                'is_playlist': True,
                'playlist_title': info.get('title', 'Playlist'),
                'videos': videos,
                'created_at': datetime.now()
            }
            
            return AnalyzeResponse(
                session_id=session_id,
                is_playlist=True,
                total_videos=len(videos),
                playlist_title=info.get('title', 'Playlist')
            )
        else:
            # Single video
            video = parse_video_info(info, platform, url)
            
            sessions[session_id] = {
                'url': url,
                'platform': platform,
                'is_playlist': False,
                'videos': [video],
                'created_at': datetime.now()
            }
            
            return AnalyzeResponse(
                session_id=session_id,
                is_playlist=False,
                total_videos=1
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analyze error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze URL: {str(e)}")

@app.get("/api/v1/videos/{session_id}", response_model=VideosResponse)
async def get_videos(session_id: str, page: int = 1, limit: int = RESULTS_PER_PAGE):
    """Get paginated videos for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    videos = session['videos']
    
    # Pagination
    start = (page - 1) * limit
    end = start + limit
    page_videos = videos[start:end]
    has_more = end < len(videos)
    
    return VideosResponse(
        videos=page_videos,
        page=page,
        has_more=has_more
    )

@app.post("/api/v1/download", response_model=DownloadResponse)
@limiter.limit("30/minute")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks, req: Any = None):
    """Start download jobs for selected videos"""
    session_id = request.session_id
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    videos = {v.id: v for v in session['videos']}
    
    jobs = []
    
    for video_id in request.video_ids:
        if video_id not in videos:
            logger.warning(f"Video {video_id} not found in session")
            continue
        
        job_id = str(uuid.uuid4())
        video = videos[video_id]
        
        # Create job
        job = {
            'job_id': job_id,
            'video_id': video_id,
            'video': video,
            'format': request.format,
            'quality': request.quality,
            'session_id': session_id
        }
        
        # Add to queue
        await download_queue.put(job)
        
        # Track job
        active_downloads[job_id] = {
            'status': DownloadStatus.QUEUED,
            'progress': 0,
            'video': video,
            'created_at': datetime.now()
        }
        
        jobs.append(DownloadJob(
            job_id=job_id,
            video_id=video_id,
            status=DownloadStatus.QUEUED
        ))
        
        logger.info(f"Queued job {job_id} for video {video_id}")
    
    return DownloadResponse(jobs=jobs)

@app.get("/api/v1/progress/{job_id}", response_model=ProgressResponse)
async def get_progress(job_id: str):
    """Get download progress for a job"""
    if job_id not in active_downloads:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = active_downloads[job_id]
    
    return ProgressResponse(
        job_id=job_id,
        status=job['status'],
        progress=job.get('progress', 0),
        error=job.get('error'),
        file_path=job.get('file_path')
    )

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    websocket_connections[session_id].append(websocket)
    
    logger.info(f"WebSocket connected: {session_id}")
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_connections[session_id].remove(websocket)
        logger.info(f"WebSocket disconnected: {session_id}")

@app.get("/downloads/{filename}")
async def download_file(filename: str):
    """Serve downloaded files"""
    file_path = DOWNLOAD_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )

# ==========================================
# STATIC FILES (for serving frontend)
# ==========================================
@app.on_event("startup")
async def mount_static():
    """Mount static files on startup"""
    static_path = Path(__file__).parent
    if static_path.exists():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
