"""
Video Downloader Backend - FastAPI + yt-dlp
With 5-second delay between downloads
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "8000"))
DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

MAX_CONCURRENT_DOWNLOADS = 1  # SINGLE WORKER - Sequential downloads only
DOWNLOAD_DELAY_SECONDS = 5  # 5 second delay between each download
MAX_PLAYLIST_SIZE = 500
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
    position: int

class DownloadResponse(BaseModel):
    jobs: List[DownloadJob]
    total_jobs: int
    estimated_time: int

class ProgressResponse(BaseModel):
    job_id: str
    status: DownloadStatus
    progress: int
    error: Optional[str] = None
    file_path: Optional[str] = None

app = FastAPI(title="Video Downloader API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: Dict[str, Dict[str, Any]] = {}
download_queue: asyncio.Queue = asyncio.Queue()
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
    elif 'likee' in url_lower:
        return Platform.LIKEE
    return Platform.UNKNOWN

def get_ydl_opts(format_type: VideoFormat = VideoFormat.BEST, quality: Optional[str] = None) -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'socket_timeout': 30,
        'retries': 5,
        'fragment_retries': 5,
        'ignoreerrors': False,
        'nocheckcertificate': True,
        'no_check_certificate': True,
        'extractor_args': {'youtube': {'skip': ['hls', 'dash']}},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'cookiesfrombrowser': ('chrome',),  # Use Chrome cookies to bypass bot detection
    }
    if format_type == VideoFormat.AUDIO:
        opts['format'] = 'bestaudio/best'
    elif quality and quality != 'best':
        opts['format'] = f'bestvideo[height<={quality.replace("p","")}]+bestaudio/best'
    else:
        opts['format'] = 'best'
    return opts

async def extract_info(url: str, extract_flat: bool = False) -> dict:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': extract_flat,
        'socket_timeout': 30,
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    # Special handling for TikTok
    if 'tiktok.com' in url.lower():
        ydl_opts['http_headers'] = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.tiktok.com/',
        }
    
    try:
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        info = await asyncio.to_thread(extract)
        if info is None:
            raise Exception("Failed to extract video information")
        return info
    except Exception as e:
        logger.error(f"Extract error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract: {str(e)}")

def parse_video_info(entry: dict, platform: Platform, source_url: str) -> VideoInfo:
    video_id = entry.get('id', str(uuid.uuid4())[:8])
    title = entry.get('title') or 'Unknown Title'
    thumbnail = entry.get('thumbnail', '')
    if not thumbnail and entry.get('thumbnails'):
        thumbnail = entry['thumbnails'][-1].get('url', '')
    return VideoInfo(
        id=video_id,
        title=title[:100],
        thumbnail=thumbnail,
        duration=entry.get('duration'),
        platform=platform,
        url=entry.get('webpage_url') or entry.get('url') or source_url,
        views=entry.get('view_count')
    )

async def notify_websocket(session_id: str, message: dict):
    connections = websocket_connections.get(session_id, [])
    for ws in connections[:]:
        try:
            await ws.send_json(message)
        except:
            try:
                connections.remove(ws)
            except:
                pass

async def download_worker():
    """Worker with 5-second delay between downloads - PROCESSES ALL VIDEOS"""
    logger.info("Download worker started with 5s delay")
    while True:
        try:
            job = await download_queue.get()
            job_id = job['job_id']
            video = job['video']
            format_type = job['format']
            quality = job['quality']
            session_id = job['session_id']
            position = job['position']
            
            # Wait 5 seconds before starting (except for first video)
            if position > 1:
                logger.info(f"Waiting 5 seconds before job {job_id} (position {position})")
                for i in range(5):
                    await asyncio.sleep(1)
                    # Update waiting status
                    await notify_websocket(session_id, {
                        'type': 'waiting',
                        'job_id': job_id,
                        'seconds_remaining': 5 - i
                    })
            
            logger.info(f"Starting job {job_id} (position {position})")
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
                logger.info(f"✅ Completed job {job_id} (position {position})")
            except Exception as e:
                logger.error(f"❌ Job {job_id} failed: {e}")
                active_downloads[job_id].update({
                    'status': DownloadStatus.FAILED,
                    'error': str(e)
                })
                await notify_websocket(session_id, {
                    'type': 'error',
                    'job_id': job_id,
                    'error': str(e)
                })
            
            # Mark task as done
            download_queue.task_done()
            
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(1)

async def download_video(job_id: str, video: VideoInfo, format_type: VideoFormat, quality: Optional[str], session_id: str) -> str:
    # Clean title properly - remove emojis, hashtags, and special characters
    import unicodedata
    
    original_title = video.title
    
    # Remove emojis and non-ASCII characters
    cleaned_title = ''.join(char for char in original_title if ord(char) < 128)
    
    # Remove hashtags
    cleaned_title = re.sub(r'#\w+', '', cleaned_title)
    
    # Remove multiple spaces
    cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
    
    # Remove filesystem-invalid characters
    safe_title = re.sub(r'[<>:"/\\|?*]', '', cleaned_title)
    
    # Remove dots at the end (problematic for some filesystems)
    safe_title = safe_title.rstrip('.')
    
    # Limit length
    safe_title = safe_title[:80].strip()
    
    # Fallback if title becomes empty
    if not safe_title or safe_title.isspace():
        safe_title = f"video_{job_id}"
    
    output_template = str(DOWNLOAD_DIR / f"{safe_title}.%(ext)s")
    
    ydl_opts = get_ydl_opts(format_type, quality)
    ydl_opts['outtmpl'] = output_template
    ydl_opts['progress_hooks'] = [lambda d: progress_hook(d, job_id, session_id)]
    
    def download():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video.url])
        except Exception as e:
            # If cookiesfrombrowser fails, retry without it
            if 'cookies' in str(e).lower() or 'bot' in str(e).lower():
                logger.warning(f"Cookie error, retrying without cookies: {e}")
                opts_no_cookies = ydl_opts.copy()
                opts_no_cookies.pop('cookiesfrombrowser', None)
                with yt_dlp.YoutubeDL(opts_no_cookies) as ydl:
                    ydl.download([video.url])
            else:
                raise
    
    await asyncio.to_thread(download)
    
    # Find the downloaded file (may have different extension)
    files = list(DOWNLOAD_DIR.glob(f"{safe_title}.*"))
    if files:
        return f"/downloads/{files[0].name}"
    raise Exception("File not found after download")

def progress_hook(d, job_id: str, session_id: str):
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

@app.on_event("startup")
async def startup_event():
    for _ in range(MAX_CONCURRENT_DOWNLOADS):
        asyncio.create_task(download_worker())
    logger.info(f"Started {MAX_CONCURRENT_DOWNLOADS} workers with 5s delay on port {PORT}")

@app.get("/")
async def root():
    return {"message": "Video Downloader API", "version": "4.0.0", "status": "running", "delay": f"{DOWNLOAD_DELAY_SECONDS}s"}

@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "active_downloads": len([d for d in active_downloads.values() if d['status'] == DownloadStatus.DOWNLOADING]),
        "queued": download_queue.qsize()
    }

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_url(request: AnalyzeRequest):
    url = request.url
    platform = detect_platform(url)
    logger.info(f"Analyzing: {url} ({platform})")
    
    try:
        info = await extract_info(url, extract_flat=True)
        session_id = str(uuid.uuid4())
        is_playlist = info.get('_type') in ['playlist', 'multi_video']
        
        if is_playlist:
            entries = info.get('entries', [])
            videos = []
            for entry in entries[:MAX_PLAYLIST_SIZE]:
                if entry:
                    try:
                        video = parse_video_info(entry, platform, url)
                        videos.append(video)
                    except:
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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/videos/{session_id}", response_model=VideosResponse)
async def get_videos(session_id: str, page: int = 1, limit: int = RESULTS_PER_PAGE):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    videos = session['videos']
    start = (page - 1) * limit
    end = start + limit
    
    return VideosResponse(
        videos=videos[start:end],
        page=page,
        has_more=end < len(videos),
        total=len(videos)
    )

@app.post("/api/v1/download", response_model=DownloadResponse)
async def start_download(request: DownloadRequest):
    session_id = request.session_id
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    videos = {v.id: v for v in session['videos']}
    jobs = []
    position = 1
    
    for video_id in request.video_ids:
        if video_id not in videos:
            continue
        
        job_id = str(uuid.uuid4())
        video = videos[video_id]
        
        job = {
            'job_id': job_id,
            'video_id': video_id,
            'video': video,
            'format': request.format,
            'quality': request.quality,
            'session_id': session_id,
            'position': position
        }
        
        await download_queue.put(job)
        
        active_downloads[job_id] = {
            'status': DownloadStatus.QUEUED,
            'progress': 0,
            'video': video,
            'position': position,
            'created_at': datetime.now()
        }
        
        jobs.append(DownloadJob(
            job_id=job_id,
            video_id=video_id,
            status=DownloadStatus.QUEUED,
            position=position
        ))
        
        position += 1
        logger.info(f"Queued job {job_id} at position {position-1}")
    
    total_jobs = len(jobs)
    estimated_time = (total_jobs - 1) * DOWNLOAD_DELAY_SECONDS if total_jobs > 1 else 0
    
    return DownloadResponse(
        jobs=jobs,
        total_jobs=total_jobs,
        estimated_time=estimated_time
    )

@app.get("/api/v1/progress/{job_id}", response_model=ProgressResponse)
async def get_progress(job_id: str):
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
    await websocket.accept()
    websocket_connections[session_id].append(websocket)
    logger.info(f"WebSocket connected: {session_id}")
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        try:
            websocket_connections[session_id].remove(websocket)
        except:
            pass
        logger.info(f"WebSocket disconnected: {session_id}")

@app.get("/downloads/{filename}")
async def download_file(filename: str):
    # Decode URL-encoded filename
    from urllib.parse import unquote
    decoded_filename = unquote(filename)
    
    file_path = DOWNLOAD_DIR / decoded_filename
    
    # If file doesn't exist, try to find it with pattern matching
    if not file_path.exists():
        # Try to find similar files (in case of encoding issues)
        matching_files = list(DOWNLOAD_DIR.glob(f"*{decoded_filename.split('.')[0][:20]}*"))
        if matching_files:
            file_path = matching_files[0]
        else:
            raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path, 
        filename=file_path.name, 
        media_type='application/octet-stream',
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"'
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
