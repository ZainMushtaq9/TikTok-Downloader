"""
Video Downloader - FastAPI Backend for Railway.app
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "8000"))
DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "4"))
MAX_PLAYLIST_SIZE = 1000
RESULTS_PER_PAGE = 20

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

app = FastAPI(title="Video Downloader API", version="1.0.0")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: Dict[str, Dict[str, Any]] = {}
download_queue = asyncio.Queue()
active_downloads: Dict[str, Dict[str, Any]] = {}
websocket_connections: Dict[str, List[WebSocket]] = defaultdict(list)

def detect_platform(url: str) -> Platform:
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
    opts = {'quiet': False, 'no_warnings': False, 'extract_flat': False, 'socket_timeout': 30}
    if format_type == VideoFormat.AUDIO:
        opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]})
    elif quality:
        opts['format'] = f'bestvideo[height<={quality[:-1]}]+bestaudio/best'
    else:
        opts['format'] = 'bestvideo+bestaudio/best'
    return opts

async def extract_info(url: str, extract_flat: bool = True) -> dict:
    ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': extract_flat, 'socket_timeout': 30}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            return info
    except Exception as e:
        logger.error(f"Failed to extract info: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract video info: {str(e)}")

def parse_video_info(entry: dict, platform: Platform, url: str) -> VideoInfo:
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
    connections = websocket_connections.get(session_id, [])
    dead_connections = []
    for ws in connections:
        try:
            await ws.send_json(message)
        except:
            dead_connections.append(ws)
    for ws in dead_connections:
        connections.remove(ws)

async def download_worker():
    while True:
        try:
            job = await download_queue.get()
            job_id = job['job_id']
            video = job['video']
            format_type = job['format']
            quality = job['quality']
            session_id = job['session_id']
            logger.info(f"Starting download job {job_id}")
            active_downloads[job_id]['status'] = DownloadStatus.DOWNLOADING
            await notify_websocket(session_id, {'type': 'progress', 'job_id': job_id, 'progress': 0})
            try:
                file_path = await download_video(job_id, video, format_type, quality, session_id)
                active_downloads[job_id].update({'status': DownloadStatus.COMPLETED, 'progress': 100, 'file_path': file_path})
                await notify_websocket(session_id, {'type': 'complete', 'job_id': job_id, 'file_path': file_path})
                logger.info(f"Completed job {job_id}")
            except Exception as e:
                logger.error(f"Job {job_id} failed: {e}")
                active_downloads[job_id].update({'status': DownloadStatus.FAILED, 'error': str(e)})
                await notify_websocket(session_id, {'type': 'error', 'job_id': job_id, 'error': str(e)})
        except Exception as e:
            logger.error(f"Worker error: {e}")

async def download_video(job_id: str, video: VideoInfo, format_type: VideoFormat, quality: Optional[str], session_id: str) -> str:
    output_template = str(DOWNLOAD_DIR / f"{session_id}_{job_id}_%(title)s.%(ext)s")
    ydl_opts = get_ydl_opts(format_type, quality)
    ydl_opts['outtmpl'] = output_template
    ydl_opts['progress_hooks'] = [lambda d: progress_hook(d, job_id, session_id)]
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        await asyncio.to_thread(ydl.download, [video.url])
    files = list(DOWNLOAD_DIR.glob(f"{session_id}_{job_id}_*"))
    if files:
        return f"/downloads/{files[0].name}"
    raise Exception("Download completed but file not found")

def progress_hook(d, job_id: str, session_id: str):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0%').strip('%')
        try:
            progress = int(float(percent))
            active_downloads[job_id]['progress'] = progress
            asyncio.create_task(notify_websocket(session_id, {'type': 'progress', 'job_id': job_id, 'progress': progress}))
        except:
            pass

@app.on_event("startup")
async def startup_event():
    for _ in range(MAX_CONCURRENT_DOWNLOADS):
        asyncio.create_task(download_worker())
    logger.info(f"Started {MAX_CONCURRENT_DOWNLOADS} download workers on port {PORT}")

@app.get("/")
async def root():
    return {"message": "Video Downloader API", "version": "1.0.0", "status": "running"}

@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "active_downloads": len([d for d in active_downloads.values() if d['status'] == DownloadStatus.DOWNLOADING]), "queued": download_queue.qsize()}

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
@limiter.limit("10/minute")
async def analyze_url(request: AnalyzeRequest, req: Request):
    url = request.url
    platform = detect_platform(url)
    logger.info(f"Analyzing URL: {url} (Platform: {platform})")
    try:
        info = await extract_info(url, extract_flat=True)
        session_id = str(uuid.uuid4())
        is_playlist = '_type' in info and info['_type'] in ['playlist', 'multi_video']
        if is_playlist:
            entries = info.get('entries', [])
            videos = []
            for entry in entries[:MAX_PLAYLIST_SIZE]:
                try:
                    video = parse_video_info(entry, platform, url)
                    videos.append(video)
                except Exception as e:
                    logger.warning(f"Failed to parse video: {e}")
            sessions[session_id] = {'url': url, 'platform': platform, 'is_playlist': True, 'playlist_title': info.get('title', 'Playlist'), 'videos': videos, 'created_at': datetime.now()}
            return AnalyzeResponse(session_id=session_id, is_playlist=True, total_videos=len(videos), playlist_title=info.get('title', 'Playlist'))
        else:
            video = parse_video_info(info, platform, url)
            sessions[session_id] = {'url': url, 'platform': platform, 'is_playlist': False, 'videos': [video], 'created_at': datetime.now()}
            return AnalyzeResponse(session_id=session_id, is_playlist=False, total_videos=1)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analyze error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze URL: {str(e)}")

@app.get("/api/v1/videos/{session_id}", response_model=VideosResponse)
async def get_videos(session_id: str, page: int = 1, limit: int = RESULTS_PER_PAGE):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[session_id]
    videos = session['videos']
    start = (page - 1) * limit
    end = start + limit
    page_videos = videos[start:end]
    has_more = end < len(videos)
    return VideosResponse(videos=page_videos, page=page, has_more=has_more)

@app.post("/api/v1/download", response_model=DownloadResponse)
@limiter.limit("30/minute")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks, req: Request):
    session_id = request.session_id
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[session_id]
    videos = {v.id: v for v in session['videos']}
    jobs = []
    for video_id in request.video_ids:
        if video_id not in videos:
            continue
        job_id = str(uuid.uuid4())
        video = videos[video_id]
        job = {'job_id': job_id, 'video_id': video_id, 'video': video, 'format': request.format, 'quality': request.quality, 'session_id': session_id}
        await download_queue.put(job)
        active_downloads[job_id] = {'status': DownloadStatus.QUEUED, 'progress': 0, 'video': video, 'created_at': datetime.now()}
        jobs.append(DownloadJob(job_id=job_id, video_id=video_id, status=DownloadStatus.QUEUED))
        logger.info(f"Queued job {job_id}")
    return DownloadResponse(jobs=jobs)

@app.get("/api/v1/progress/{job_id}", response_model=ProgressResponse)
async def get_progress(job_id: str):
    if job_id not in active_downloads:
        raise HTTPException(status_code=404, detail="Job not found")
    job = active_downloads[job_id]
    return ProgressResponse(job_id=job_id, status=job['status'], progress=job.get('progress', 0), error=job.get('error'), file_path=job.get('file_path'))

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    websocket_connections[session_id].append(websocket)
    logger.info(f"WebSocket connected: {session_id}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_connections[session_id].remove(websocket)
        logger.info(f"WebSocket disconnected: {session_id}")

@app.get("/downloads/{filename}")
async def download_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=filename, media_type='application/octet-stream')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
