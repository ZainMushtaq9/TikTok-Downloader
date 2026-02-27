import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Platform regex patterns
PLATFORM_PATTERNS = {
    'youtube': re.compile(r'(?:youtube\.com|youtu\.be)', re.IGNORECASE),
    'tiktok': re.compile(r'(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)', re.IGNORECASE),
    'instagram': re.compile(r'(?:instagram\.com|instagr\.am)', re.IGNORECASE),
    'facebook': re.compile(r'(?:facebook\.com|fb\.watch|web\.facebook\.com|m\.facebook\.com)', re.IGNORECASE),
    'twitter': re.compile(r'(?:twitter\.com|x\.com|t\.co|fxtwitter\.com)', re.IGNORECASE),
    'vimeo': re.compile(r'(?:vimeo\.com|player\.vimeo\.com)', re.IGNORECASE),
    'reddit': re.compile(r'(?:reddit\.com|redd\.it|old\.reddit\.com|v\.redd\.it)', re.IGNORECASE),
    'pinterest': re.compile(r'(?:pinterest\.[a-z.]+|pin\.it)', re.IGNORECASE),
    'linkedin': re.compile(r'linkedin\.com', re.IGNORECASE),
    'twitch': re.compile(r'(?:twitch\.tv|clips\.twitch\.tv|m\.twitch\.tv)', re.IGNORECASE),
    'dailymotion': re.compile(r'(?:dailymotion\.com|dai\.ly)', re.IGNORECASE),
    'likee': re.compile(r'(?:likee\.video|l\.likee\.video)', re.IGNORECASE),
    'vk': re.compile(r'(?:vk\.com|vkvideo\.ru)', re.IGNORECASE),
    'bilibili': re.compile(r'(?:bilibili\.com|b23\.tv)', re.IGNORECASE),
    'snapchat': re.compile(r'(?:snapchat\.com|snap\.com)', re.IGNORECASE),
}

TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
    'igsh', 'igshid', 'ref', 'feature', 'is_from_webapp',
    'share_id', 'locale'
}

def normalize_url(url: str) -> str:
    # 6. Convert http:// to https://
    if url.startswith('http://'):
        url = 'https://' + url[7:]
    elif not url.startswith('http'):
        url = 'https://' + url

    # Parse URL
    parsed = urlparse(url)
    
    # 4. Convert mobile URLs
    netloc = parsed.netloc.lower()
    if netloc == 'm.youtube.com':
        netloc = 'www.youtube.com'
    elif netloc in ['m.facebook.com', 'web.facebook.com']:
        netloc = 'www.facebook.com'
    elif netloc == 'mobile.twitter.com':
        netloc = 'twitter.com'

    # 1 & 2. Strip tracking params
    query = parse_qs(parsed.query)
    clean_query = {k: v for k, v in query.items() if k.lower() not in TRACKING_PARAMS}
    new_query_string = urlencode(clean_query, doseq=True)

    # 5. Strip trailing slashes
    path = parsed.path
    if path.endswith('/') and len(path) > 1:
        path = path[:-1]

    normalized = urlunparse((
        parsed.scheme,
        netloc,
        path,
        parsed.params,
        new_query_string,
        parsed.fragment
    ))
    
    return normalized

def detect_platform(url: str) -> str:
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url):
            return platform
    return 'unknown'

def detect_content_type(url: str, platform: str) -> str:
    if platform == 'youtube':
        if 'list=' in url and 'watch?v=' not in url:
            return 'playlist'
        elif 'watch?v=' in url and 'list=' in url:
            return 'video_in_playlist'
        elif '/shorts/' in url:
            return 'shorts'
        elif re.search(r'@[\w.]+', url) or '/channel/' in url or '/user/' in url or '/c/' in url:
            return 'channel'
        elif 'playlist?list=' in url:
            return 'playlist'
        return 'single_video'
    
    if platform == 'tiktok':
        if '@' in url and '/video/' not in url and '/photo/' not in url:
            return 'profile'
        return 'single_video'
        
    if platform == 'instagram':
        if '/p/' in url:
            return 'post'
        elif '/reel/' in url:
            return 'reel'
        elif '/stories/' in url:
            return 'story'
        elif re.search(r'instagram\.com/[^/]+$', url) or re.search(r'instagram\.com/[^/]+/reels$', url):
            return 'profile'

    if platform == 'facebook':
        if '/videos/' in url or 'watch?v=' in url or '/reel/' in url:
            return 'single_video'
        elif re.search(r'facebook\.com/[^/]+$', url):
            return 'profile'
        elif '/share/r/' in url:
            return 'reel'
        elif '/share/v/' in url:
            return 'single_video'

    if platform == 'snapchat':
        return 'single_video'
            
    return 'single_video'

def analyze_url(raw_url: str):
    url = normalize_url(raw_url)
    platform = detect_platform(url)
    content_type = detect_content_type(url, platform)
    
    return {
        'original_url': raw_url,
        'url': url,
        'platform': platform,
        'content_type': content_type,
        'is_playlist': content_type in ('playlist', 'channel', 'profile'),
        'is_profile': content_type in ('channel', 'profile')
    }
