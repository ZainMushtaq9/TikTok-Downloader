"""
Video Downloader Backend - FastAPI + yt-dlp
Production-ready for Railway deployment
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, validator
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
from collections import defaultdict

# ==========================================
# CONFIGURATION
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "8000"))
DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

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
    duration: Optional[int] = None
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
    total: int

class DownloadJob(BaseModel):
    job_id: str
    video_id: str
    status: DownloadStatus

class DownloadResponse(BaseModel):
    jobs: List[DownloadJob]
    message: str

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
    description="Production video downloader API",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# IN-MEMORY STORAGE
# ==========================================
sessions: Dict[str, Dict[str, Any]] = {}
download_queue: asyncio.Queue = asyncio.Queue()
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
    return Platform.UNKNOWN

def get_ydl_opts(format_type: VideoFormat = VideoFormat.BEST, quality: Optional[str] = None) -> dict:
    """Get yt-dlp options with error handling"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
        'ignoreerrors': False,
        'no_check_certificate': True,
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
        height = quality.replace('p', '')
        opts['format'] = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'
    else:
        opts['format'] = 'best'

    return opts

async def extract_info(url: str, extract_flat: bool = False) -> dict:
    """Extract video information using yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': extract_flat,
        'socket_timeout': 30,
        'retries': 3,
        'ignoreerrors': True,
        'no_check_certificate': True,
    }

    try:
        logger.info(f"Extracting info from: {url}")
        
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        info = await asyncio.to_thread(extract)
        
        if info is None:
            raise Exception("Failed to extract video information")
        
        logger.info(f"Successfully extracted info. Type: {info.get('_type', 'video')}")
        return info
        
    except Exception as e:
        logger.error(f"Failed to extract info: {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Failed to extract video info: {str(e)}"
        )

def parse_video_info(entry: dict, platform: Platform, source_url: str) -> VideoInfo:
    """Parse video information from yt-dlp entry"""
    try:
        # Handle both full extraction and flat extraction
        video_id = entry.get('id', str(uuid.uuid4())[:8])
        
        # Get title
        title = entry.get('title') or entry.get('webpage_url_basename', 'Unknown Title')
        
        # Get thumbnail
        thumbnail = ''
        if entry.get('thumbnail'):
            thumbnail = entry['thumbnail']
        elif entry.get('thumbnails') and len(entry['thumbnails']) > 0:
            thumbnail = entry['thumbnails'][-1].get('url', '')
        
        # Get URL
        video_url = entry.get('webpage_url') or entry.get('url') or source_url
        
        # Get duration
        duration = entry.get('duration')
        
        # Get views
        views = entry.get('view_count')
        
        return VideoInfo(
            id=video_id,
            title=title,
            thumbnail=thumbnail,
            duration=duration,
            platform=platform,
            url=video_url,
            views=views
        )
    except Exception as e:
        logger.error(f"Failed to parse video info: {str(e)}")
        raise

async def notify_websocket(session_id: str, message: dict):
    """Send WebSocket notification"""
    connections = websocket_connections.get(session_id, [])
    dead_connections = []
    
    for ws in connections:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.error(f"WebSocket send error: {e}")
            dead_connections.append(ws)
    
    for ws in dead_connections:
        try:
            connections.remove(ws)
        except:
            pass

# ==========================================
# DOWNLOAD WORKER
# ==========================================
async def download_worker():
    """Background worker to process downloads"""
    logger.info("Download worker started")
    
    while True:
        try:
            job = await download_queue.get()
            job_id = job['job_id']
            video = job['video']
            format_type = job['format']
            quality = job['quality']
            session_id = job['session_id']

            logger.info(f"Processing download job {job_id}")
            
            active_downloads[job_id]['status'] = DownloadStatus.DOWNLOADING
            await notify_websocket(session_id, {
                'type': 'progress',
                'job_id': job_id,
                'progress': 0
            })

            try:
                file_path = await download_video(job_id, video, format_type, quality, session_id)
                
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
                logger.error(f"Job {job_id} failed: {str(e)}")
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
            logger.error(f"Worker error: {str(e)}")
            await asyncio.sleep(1)

async def download_video(job_id: str, video: VideoInfo, format_type: VideoFormat, 
                        quality: Optional[str], session_id: str) -> str:
    """Download a single video"""
    safe_title = re.sub(r'[^\w\s-]', '', video.title)[:50]
    output_template = str(DOWNLOAD_DIR / f"{session_id}_{job_id}_{safe_title}.%(ext)s")
    
    ydl_opts = get_ydl_opts(format_type, quality)
    ydl_opts['outtmpl'] = output_template
    ydl_opts['progress_hooks'] = [lambda d: progress_hook(d, job_id, session_id)]

    def download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video.url])
    
    await asyncio.to_thread(download)
    
    files = list(DOWNLOAD_DIR.glob(f"{session_id}_{job_id}_*"))
    if files:
        return f"/downloads/{files[0].name}"
    raise Exception("Download completed but file not found")

def progress_hook(d, job_id: str, session_id: str):
    """Progress callback"""
    if d['status'] == 'downloading':
        try:
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            
            if total > 0:
                progress = int((downloaded / total) * 100)
                active_downloads[job_id]['progress'] = progress
                
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
    for i in range(MAX_CONCURRENT_DOWNLOADS):
        asyncio.create_task(download_worker())
    logger.info(f"Started {MAX_CONCURRENT_DOWNLOADS} download workers on port {PORT}")

@app.get("/")
async def root():
    return {
        "message": "Video Downloader API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "active_downloads": len([d for d in active_downloads.values() if d['status'] == DownloadStatus.DOWNLOADING]),
        "queued": download_queue.qsize(),
        "sessions": len(sessions)
    }

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_url(request: AnalyzeRequest):
    """Analyze URL and extract video metadata"""
    url = request.url
    platform = detect_platform(url)
    
    logger.info(f"Analyzing URL: {url} (Platform: {platform})")
    
    try:
        # First try to extract info
        info = await extract_info(url, extract_flat=True)
        
        session_id = str(uuid.uuid4())
        is_playlist = info.get('_type') in ['playlist', 'multi_video']
        
        if is_playlist:
            logger.info(f"Detected playlist with {len(info.get('entries', []))} entries")
            
            entries = info.get('entries', [])
            videos = []
            
            # Process entries
            for entry in entries[:MAX_PLAYLIST_SIZE]:
                if entry is None:
                    continue
                    
                try:
                    video = parse_video_info(entry, platform, url)
                    videos.append(video)
                except Exception as e:
                    logger.warning(f"Failed to parse entry: {str(e)}")
                    continue
            
            sessions[session_id] = {
                'url': url,
                'platform': platform,
                'is_playlist': True,
                'playlist_title': info.get('title', 'Playlist'),
                'videos': videos,
                'created_at': datetime.now()
            }
            
            logger.info(f"Created session {session_id} with {len(videos)} videos")
            
            return AnalyzeResponse(
                session_id=session_id,
                is_playlist=True,
                total_videos=len(videos),
                playlist_title=info.get('title', 'Playlist')
            )
        else:
            # Single video
            logger.info("Detected single video")
            video = parse_video_info(info, platform, url)
            
            sessions[session_id] = {
                'url': url,
                'platform': platform,
                'is_playlist': False,
                'videos': [video],
                'created_at': datetime.now()
            }
            
            logger.info(f"Created session {session_id} with 1 video")
            
            return AnalyzeResponse(
                session_id=session_id,
                is_playlist=False,
                total_videos=1
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analyze error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to analyze URL: {str(e)}"
        )

@app.get("/api/v1/videos/{session_id}", response_model=VideosResponse)
async def get_videos(session_id: str, page: int = 1, limit: int = RESULTS_PER_PAGE):
    """Get paginated videos for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    videos = session['videos']
    
    start = (page - 1) * limit
    end = start + limit
    page_videos = videos[start:end]
    has_more = end < len(videos)
    
    return VideosResponse(
        videos=page_videos,
        page=page,
        has_more=has_more,
        total=len(videos)
    )

@app.post("/api/v1/download", response_model=DownloadResponse)
async def start_download(request: DownloadRequest):
    """Start download jobs"""
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
        
        job = {
            'job_id': job_id,
            'video_id': video_id,
            'video': video,
            'format': request.format,
            'quality': request.quality,
            'session_id': session_id
        }
        
        await download_queue.put(job)
        
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
    
    return DownloadResponse(
        jobs=jobs,
        message=f"Queued {len(jobs)} download(s)"
    )

@app.get("/api/v1/progress/{job_id}", response_model=ProgressResponse)
async def get_progress(job_id: str):
    """Get download progress"""
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
    """WebSocket for real-time updates"""
    await websocket.accept()
    websocket_connections[session_id].append(websocket)
    logger.info(f"WebSocket connected: {session_id}")
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_connections[session_id].remove(websocket)
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            websocket_connections[session_id].remove(websocket)
        except:
            pass

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

# Railway deployment
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
