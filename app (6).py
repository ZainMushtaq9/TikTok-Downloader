"""
Video Downloader Backend v5.0 - COMPLETE REWRITE
All platforms working: YouTube, TikTok, Instagram, Facebook, Twitter, Likee
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", "8000"))
DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

MAX_CONCURRENT_DOWNLOADS = 1
DOWNLOAD_DELAY_SECONDS = 5
MAX_PLAYLIST_SIZE = 100

class Platform(str, Enum):
    YOUTUBE = "YouTube"
    TIKTOK = "TikTok"
    INSTAGRAM = "Instagram"
    FACEBOOK = "Facebook"
    TWITTER = "Twitter"
    LIKEE = "Likee"

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

app = FastAPI(title="Video Downloader", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {}
download_queue = asyncio.Queue()
active_downloads = {}
websocket_connections = defaultdict(list)

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
    elif 'likee' in url_lower:
        return Platform.LIKEE
    return Platform.YOUTUBE

def get_ydl_opts(platform: Platform, for_download: bool = False) -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'socket_timeout': 60,
        'retries': 10,
        'fragment_retries': 10,
        'nocheckcertificate': True,
    }
    
    if not for_download:
        opts['extract_flat'] = 'in_playlist'
    
    if platform == Platform.YOUTUBE:
        opts['format'] = 'best'
    elif platform == Platform.INSTAGRAM:
        opts['http_headers'] = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 12_3 like Mac OS X) AppleWebKit/605.1.15'}
    elif platform == Platform.TIKTOK:
        opts['http_headers'] = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.tiktok.com/'}
    else:
        opts['format'] = 'best'
    
    return opts

def clean_filename(title: str, job_id: str) -> str:
    cleaned = ''.join(c for c in title if ord(c) < 128)
    cleaned = re.sub(r'#\w+', '', cleaned)
    cleaned = re.sub(r'[<>:"/\\|?*]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().rstrip('.')[:60]
    return cleaned if cleaned and len(cleaned) >= 3 else f"video_{job_id[:8]}"

async def extract_info(url: str, platform: Platform) -> dict:
    ydl_opts = get_ydl_opts(platform, for_download=False)
    try:
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        info = await asyncio.to_thread(extract)
        if not info:
            raise Exception("Failed to extract")
        return info
    except Exception as e:
        logger.error(f"Extract error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract: {str(e)}")

def parse_video(entry: dict, platform: Platform, url: str) -> VideoInfo:
    return VideoInfo(
        id=entry.get('id', str(uuid.uuid4())[:8]),
        title=(entry.get('title') or 'Unknown')[:100],
        thumbnail=entry.get('thumbnail', ''),
        duration=entry.get('duration'),
        platform=platform,
        url=entry.get('webpage_url') or entry.get('url') or url,
        views=entry.get('view_count')
    )

async def notify_ws(session_id: str, message: dict):
    for ws in websocket_connections.get(session_id, [])[:]:
        try:
            await ws.send_json(message)
        except:
            try:
                websocket_connections[session_id].remove(ws)
            except:
                pass

async def download_worker():
    logger.info("Worker started")
    while True:
        try:
            job = await download_queue.get()
            job_id, video, fmt, qual, sid, pos = job['job_id'], job['video'], job['format'], job['quality'], job['session_id'], job['position']
            
            if pos > 1:
                for i in range(5):
                    await asyncio.sleep(1)
                    await notify_ws(sid, {'type': 'waiting', 'job_id': job_id, 'seconds_remaining': 5-i})
            
            logger.info(f"▶ Download {pos}: {video.title}")
            active_downloads[job_id]['status'] = DownloadStatus.DOWNLOADING
            await notify_ws(sid, {'type': 'progress', 'job_id': job_id, 'progress': 0})
            
            try:
                file_path = await download_video(job_id, video, fmt, qual, sid)
                active_downloads[job_id].update({'status': DownloadStatus.COMPLETED, 'progress': 100, 'file_path': file_path})
                await notify_ws(sid, {'type': 'complete', 'job_id': job_id, 'file_path': file_path})
                logger.info(f"✅ Complete: {video.title}")
            except Exception as e:
                logger.error(f"❌ Failed: {e}")
                active_downloads[job_id].update({'status': DownloadStatus.FAILED, 'error': str(e)})
                await notify_ws(sid, {'type': 'error', 'job_id': job_id, 'error': str(e)})
            
            download_queue.task_done()
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(1)

async def download_video(job_id: str, video: VideoInfo, fmt: VideoFormat, qual: Optional[str], sid: str) -> str:
    safe_title = clean_filename(video.title, job_id)
    output = str(DOWNLOAD_DIR / f"{safe_title}.%(ext)s")
    
    opts = get_ydl_opts(video.platform, for_download=True)
    opts['outtmpl'] = output
    opts['progress_hooks'] = [lambda d: progress_hook(d, job_id, sid)]
    
    if fmt == VideoFormat.AUDIO:
        opts['format'] = 'bestaudio/best'
    elif qual and qual != 'best':
        opts['format'] = f'bestvideo[height<={qual.replace("p","")}]+bestaudio/best'
    
    def download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([video.url])
    
    await asyncio.to_thread(download)
    
    files = list(DOWNLOAD_DIR.glob(f"{safe_title}.*"))
    if files:
        return f"/downloads/{files[0].name}"
    raise Exception("File not found")

def progress_hook(d, job_id: str, sid: str):
    if d['status'] == 'downloading':
        try:
            prog = min(int((d.get('downloaded_bytes', 0) / (d.get('total_bytes') or d.get('total_bytes_estimate', 1))) * 100), 99)
            active_downloads[job_id]['progress'] = prog
            asyncio.create_task(notify_ws(sid, {'type': 'progress', 'job_id': job_id, 'progress': prog}))
        except:
            pass

@app.on_event("startup")
async def startup():
    asyncio.create_task(download_worker())
    logger.info(f"✅ Started on port {PORT}")

@app.get("/")
async def root():
    return {"status": "running", "version": "5.0"}

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    platform = detect_platform(req.url)
    logger.info(f"Analyze: {req.url} ({platform})")
    
    info = await extract_info(req.url, platform)
    sid = str(uuid.uuid4())
    is_pl = info.get('_type') in ['playlist', 'multi_video']
    
    if is_pl:
        videos = [parse_video(e, platform, req.url) for e in info.get('entries', [])[:MAX_PLAYLIST_SIZE] if e and isinstance(e, dict)]
        if not videos:
            raise HTTPException(400, "No videos found")
        sessions[sid] = {'platform': platform, 'is_playlist': True, 'playlist_title': info.get('title', 'Playlist'), 'videos': videos}
        return AnalyzeResponse(session_id=sid, is_playlist=True, total_videos=len(videos), playlist_title=info.get('title'))
    else:
        video = parse_video(info, platform, req.url)
        sessions[sid] = {'platform': platform, 'is_playlist': False, 'videos': [video]}
        return AnalyzeResponse(session_id=sid, is_playlist=False, total_videos=1)

@app.get("/api/v1/videos/{session_id}", response_model=VideosResponse)
async def get_videos(session_id: str, page: int = 1, limit: int = 20):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    videos = sessions[session_id]['videos']
    start, end = (page-1)*limit, page*limit
    return VideosResponse(videos=videos[start:end], page=page, has_more=end<len(videos), total=len(videos))

@app.post("/api/v1/download", response_model=DownloadResponse)
async def download(req: DownloadRequest):
    if req.session_id not in sessions:
        raise HTTPException(404, "Session not found")
    
    videos = {v.id: v for v in sessions[req.session_id]['videos']}
    jobs = []
    
    for pos, vid_id in enumerate(req.video_ids, 1):
        if vid_id not in videos:
            continue
        
        job_id = str(uuid.uuid4())
        await download_queue.put({
            'job_id': job_id, 'video': videos[vid_id], 'format': req.format,
            'quality': req.quality, 'session_id': req.session_id, 'position': pos
        })
        
        active_downloads[job_id] = {'status': DownloadStatus.QUEUED, 'progress': 0, 'position': pos}
        jobs.append(DownloadJob(job_id=job_id, video_id=vid_id, status=DownloadStatus.QUEUED, position=pos))
    
    return DownloadResponse(jobs=jobs, total_jobs=len(jobs), estimated_time=(len(jobs)-1)*5 if len(jobs)>1 else 0)

@app.get("/api/v1/progress/{job_id}", response_model=ProgressResponse)
async def progress(job_id: str):
    if job_id not in active_downloads:
        raise HTTPException(404, "Job not found")
    j = active_downloads[job_id]
    return ProgressResponse(job_id=job_id, status=j['status'], progress=j.get('progress', 0), error=j.get('error'), file_path=j.get('file_path'))

@app.websocket("/ws/{session_id}")
async def ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    websocket_connections[session_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        try:
            websocket_connections[session_id].remove(websocket)
        except:
            pass

@app.get("/downloads/{filename:path}")
async def dl_file(filename: str):
    path = DOWNLOAD_DIR / unquote(filename)
    if not path.exists():
        files = list(DOWNLOAD_DIR.glob(f"*{unquote(filename).split('.')[0][:20]}*"))
        path = files[0] if files else None
    if not path or not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=path.name, media_type='application/octet-stream')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
