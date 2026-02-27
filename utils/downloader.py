import subprocess
import json
import os
import random
import re
import requests
from config import Config

# User Agents for rotating
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
]

def get_base_args(url, is_playlist=False):
    args = [
        Config.YTDLP_PATH,
        url,
        '--no-warnings',
        '--quiet',
        '--user-agent', random.choice(USER_AGENTS),
        '--socket-timeout', '15',
        '--retries', '3'
    ]
    if not is_playlist:
        args.append('--no-playlist')
    return args


# ============================================================
# METADATA FETCHING — Multi-strategy approach
# ============================================================

def get_metadata(url, platform):
    """Try multiple strategies to get video metadata without any authentication."""
    
    # Strategy 1: OEmbed API (works for TikTok, YouTube, Vimeo without auth)
    meta = _try_oembed(url, platform)
    if meta:
        return meta
    
    # Strategy 2: Noembed.com — a free universal OEmbed proxy (works for Instagram, Facebook too)
    meta = _try_noembed(url)
    if meta:
        return meta
    
    # Strategy 3: Scrape Open Graph tags from the page HTML using mobile user-agent
    meta = _try_og_scrape(url)
    if meta:
        return meta
    
    # Strategy 4: yt-dlp with aggressive flags (last resort, short timeout)
    meta = _try_ytdlp(url, platform)
    if meta:
        return meta
    
    return None


def _try_noembed(url):
    """Use noembed.com — a free universal OEmbed proxy that supports Instagram, Facebook, etc."""
    try:
        resp = requests.get(
            f'https://noembed.com/embed?url={url}',
            headers={'User-Agent': random.choice(USER_AGENTS)},
            timeout=8
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('error'):
                return None
            return {
                'id': url,
                'title': data.get('title', data.get('author_name', 'Video')),
                'duration': 0,
                'thumbnail': data.get('thumbnail_url', ''),
                'uploader': data.get('author_name', data.get('provider_name', 'Unknown')),
                'view_count': 0,
                'formats': _default_formats()
            }
    except Exception as e:
        print(f"Noembed failed: {e}")
    return None


def _try_oembed(url, platform):
    """Use platform OEmbed APIs to fetch metadata. These are public and don't need auth."""
    oembed_endpoints = {
        'instagram': f'https://api.instagram.com/oembed?url={url}&omitscript=true',
        'facebook': f'https://www.facebook.com/plugins/video/oembed.json/?url={url}',
        'tiktok': f'https://www.tiktok.com/oembed?url={url}',
        'youtube': f'https://www.youtube.com/oembed?url={url}&format=json',
        'vimeo': f'https://vimeo.com/api/oembed.json?url={url}',
        'dailymotion': f'https://www.dailymotion.com/services/oembed?url={url}&format=json',
        'twitter': f'https://publish.twitter.com/oembed?url={url}',
        'reddit': None,
        'twitch': None,
    }
    
    endpoint = oembed_endpoints.get(platform)
    if not endpoint:
        return None
    
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        resp = requests.get(endpoint, headers=headers, timeout=8, allow_redirects=True)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'id': url,
                'title': data.get('title', data.get('author_name', 'Video')),
                'duration': 0,
                'thumbnail': data.get('thumbnail_url', ''),
                'uploader': data.get('author_name', 'Unknown'),
                'view_count': 0,
                'formats': _default_formats()
            }
    except Exception as e:
        print(f"OEmbed failed for {platform}: {e}")
    return None


def _try_og_scrape(url):
    """Scrape Open Graph meta tags from the page HTML. Works on most platforms without auth."""
    try:
        # Use mobile user-agent — Instagram/Facebook are more likely to serve OG tags to mobile
        mobile_ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        headers = {
            'User-Agent': mobile_ua,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        html = resp.text[:30000]  # Check first 30KB
        
        title = _extract_og(html, 'og:title') or _extract_tag(html, 'title')
        thumbnail = _extract_og(html, 'og:image')
        description = _extract_og(html, 'og:description') or ''
        site_name = _extract_og(html, 'og:site_name') or 'Unknown'
        
        if title:
            return {
                'id': url,
                'title': title,
                'duration': 0,
                'thumbnail': thumbnail or '',
                'uploader': site_name,
                'view_count': 0,
                'formats': _default_formats()
            }
    except Exception as e:
        print(f"OG scrape failed: {e}")
    return None


def _extract_og(html, prop):
    """Extract an Open Graph meta tag value."""
    pattern = re.compile(
        rf'<meta[^>]*property=["\']?{re.escape(prop)}["\']?[^>]*content=["\']([^"\']+)["\']',
        re.IGNORECASE
    )
    match = pattern.search(html)
    if match:
        return match.group(1)
    # Try reverse order (content before property)
    pattern2 = re.compile(
        rf'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']?{re.escape(prop)}["\']?',
        re.IGNORECASE
    )
    match2 = pattern2.search(html)
    return match2.group(1) if match2 else None


def _extract_tag(html, tag):
    """Extract content of a simple HTML tag like <title>."""
    match = re.search(rf'<{tag}[^>]*>([^<]+)</{tag}>', html, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _try_ytdlp(url, platform):
    """Use yt-dlp as a last resort. Has a short timeout."""
    args = get_base_args(url) + ['--dump-json', '--no-download']
    
    if platform == 'tiktok':
        if 'vm.tiktok.com' not in url and 'vt.tiktok.com' not in url:
            args.extend(['--extractor-args', 'tiktok:api_hostname=api22-normal-c-useast1a.tiktokv.com'])
    
    # Add Instagram-specific flags to try without login
    if platform == 'instagram':
        args.extend(['--extractor-args', 'instagram:api_hostname=i.instagram.com'])
    
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=12)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            return {
                'id': data.get('id'),
                'title': data.get('title'),
                'duration': data.get('duration'),
                'thumbnail': data.get('thumbnail'),
                'uploader': data.get('uploader'),
                'view_count': data.get('view_count'),
                'formats': extract_formats(data.get('formats', []))
            }
    except subprocess.TimeoutExpired:
        print(f"yt-dlp timed out for {platform}")
    except Exception as e:
        print(f"yt-dlp metadata error: {e}")
    return None


def _default_formats():
    """Return standard format options when we can't enumerate specific ones."""
    return [
        {'format_id': 'best', 'ext': 'mp4', 'resolution': '1080p', 'size': 'Auto', 'vcodec': 'h264', 'acodec': 'aac'},
        {'format_id': 'good', 'ext': 'mp4', 'resolution': '720p', 'size': 'Auto', 'vcodec': 'h264', 'acodec': 'aac'},
        {'format_id': 'fast', 'ext': 'mp4', 'resolution': '480p', 'size': 'Auto', 'vcodec': 'h264', 'acodec': 'aac'},
        {'format_id': 'audio', 'ext': 'mp3', 'resolution': 'Audio', 'size': 'Auto', 'vcodec': 'none', 'acodec': 'mp3'}
    ]


def extract_formats(formats):
    available = []
    seen = set()
    for f in formats:
        ext = f.get('ext')
        if ext not in ('mp4', 'webm', 'm4a'):
            continue
            
        resolution = f.get('resolution') or (f"{f.get('height', 'audio')}p" if f.get('height') else 'Unknown')
        if resolution in seen:
            continue
        
        size = f.get('filesize') or f.get('filesize_approx')
        size_mb = f"{round(size / 1024 / 1024, 2)} MB" if size else "Unknown"
        
        available.append({
            'format_id': f.get('format_id'),
            'ext': ext,
            'resolution': resolution,
            'size': size_mb,
            'vcodec': f.get('vcodec'),
            'acodec': f.get('acodec')
        })
        seen.add(resolution)
    return available if available else _default_formats()


def get_playlist_data(url):
    args = get_base_args(url, is_playlist=True) + ['--flat-playlist', '--dump-single-json']
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        
        entries = []
        for e in data.get('entries', []):
            if e:
                thumb = None
                if e.get('thumbnails'):
                    thumb = e['thumbnails'][0].get('url') if isinstance(e['thumbnails'], list) else None
                elif e.get('thumbnail'):
                    thumb = e['thumbnail']
                    
                entries.append({
                    'id': e.get('id'),
                    'title': e.get('title'),
                    'duration': e.get('duration'),
                    'thumbnail': thumb,
                    'url': e.get('url', e.get('webpage_url', ''))
                })
                
        return {
            'title': data.get('title'),
            'uploader': data.get('uploader'),
            'total_videos': len(entries),
            'entries': entries
        }
    except subprocess.TimeoutExpired:
        print("Playlist fetch timed out")
        return None
    except Exception as e:
        print(f"Error fetching playlist: {e}")
        return None


def download_stream(url, format_type='mp4', quality='1080', platform='youtube'):
    args = get_base_args(url)
    
    # Output to stdout
    args.extend(['-o', '-'])
    
    if format_type == 'mp3':
        args.extend(['-x', '--audio-format', 'mp3', '--audio-quality', '192K'])
    else:
        quality_num = ''.join(filter(str.isdigit, quality)) or '1080'
        args.extend(['-f', f'bestvideo[height<={quality_num}]+bestaudio/best[height<={quality_num}]/best'])
        args.extend(['--merge-output-format', format_type])
        
    if platform == 'tiktok':
        args.extend(['--extractor-args', 'tiktok:api_hostname=api22-normal-c-useast1a.tiktokv.com'])
        
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process
