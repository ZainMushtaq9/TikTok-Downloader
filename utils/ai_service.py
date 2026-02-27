import json
import re

# Try to import Gemini, but don't crash if not available
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from config import Config

# Configure Gemini only if key is set
_model = None
if GEMINI_AVAILABLE and Config.GEMINI_API_KEY:
    try:
        genai.configure(api_key=Config.GEMINI_API_KEY)
        _model = genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        print(f"Gemini init failed: {e}")
        _model = None

def generate_summary(title, description):
    if not _model:
        return f"This video is titled '{title}'. Use the format selector below to download."
        
    prompt = f"Summarize this video in exactly 2-3 sentences. Be concise, factual, informative. No filler phrases. Max 60 words.\n\nTitle: {title}\nDescription: {str(description)[:500]}"
    try:
        response = _model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"This video is titled '{title}'. Use the format selector below to download."

def recommend_format(platform, title, duration):
    if not _model:
        return {"format": "MP4", "quality": "1080p", "reason": "Best quality for most devices."}
        
    prompt = f'You recommend the best download format. Return JSON only in this exact format: {{"format":"MP4","quality":"1080p","reason":"one sentence explanation taking less than 15 words."}}\n\nPlatform: {platform}, Title: {title}, Duration: {duration}'
    try:
        response = _model.generate_content(prompt)
        text = response.text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)
    except Exception as e:
        print(f"Gemini Recommendation Error: {e}")
        return {"format": "MP4", "quality": "1080p", "reason": "Standard high quality."}

def extract_urls_from_text(text):
    """Extract video URLs from text. Uses regex always, enhances with AI if available."""
    
    # ALWAYS use regex first — this works without any API key
    url_pattern = re.compile(
        r'https?://(?:www\.)?'
        r'(?:'
        r'(?:youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+|youtube\.com/shorts/[\w-]+|youtube\.com/playlist\?list=[\w-]+)'
        r'|(?:(?:vm|vt)?\.?tiktok\.com/[\w/@.]+)'
        r'|(?:instagram\.com/(?:p|reel|tv)/[\w-]+)'
        r'|(?:(?:www\.)?facebook\.com/[\w./]+)'
        r'|(?:(?:twitter|x)\.com/\w+/status/\d+)'
        r'|(?:(?:www\.)?reddit\.com/r/\w+/comments/[\w/]+)'
        r'|(?:vimeo\.com/\d+)'
        r'|(?:(?:clips\.)?twitch\.tv/[\w/]+)'
        r'|(?:dailymotion\.com/video/[\w-]+|dai\.ly/[\w-]+)'
        r'|(?:snapchat\.com/[\w/@.?=&]+)'
        r')',
        re.IGNORECASE
    )
    
    found_urls = url_pattern.findall(text)
    
    # Also find URLs by splitting on whitespace and checking for http
    for word in text.split():
        word = word.strip(',;!()[]{}<>')
        if word.startswith('http') and word not in found_urls:
            # Check if it matches a known platform
            from utils.url_normalizer import detect_platform
            platform = detect_platform(word)
            if platform != 'unknown':
                found_urls.append(word)
    
    # Deduplicate
    seen = set()
    results = []
    for url in found_urls:
        if url not in seen:
            seen.add(url)
            from utils.url_normalizer import detect_platform
            platform = detect_platform(url)
            results.append({'url': url, 'platform': platform})
    
    # If AI is available and found nothing via regex, try AI as fallback
    if not results and _model:
        prompt = f'Extract all video URLs from the text. Return JSON array only: [{{"url":"...","platform":"youtube"}}]. If none found, return [].\n\nText: {text}'
        try:
            response = _model.generate_content(prompt)
            res_text = response.text
            match = re.search(r'\[.*\]', res_text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return json.loads(res_text)
        except Exception as e:
            print(f"Gemini URL Extraction Error: {e}")
    
    return results
