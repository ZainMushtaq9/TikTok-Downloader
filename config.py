import os

# Load .env file if it exists (for local development)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_secret_key_change_in_production')
    
    # Rate limiting
    RATE_LIMIT_PER_HOUR = int(os.environ.get('RATE_LIMIT_PER_HOUR', 30))
    
    # AI settings
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    
    # YT-DLP Path (can be empty to use system yt-dlp)
    YTDLP_PATH = os.environ.get('YTDLP_PATH', 'yt-dlp')
    
    # Turnstile
    TURNSTILE_SECRET = os.environ.get('CLOUDFLARE_TURNSTILE_SECRET', '')

    # ========== ADSENSE CONFIG (Change once, applies everywhere) ==========
    # Set your Google AdSense Publisher ID here. Format: ca-pub-XXXXXXXXXXXXXXXX
    ADSENSE_PUBLISHER_ID = os.environ.get('ADSENSE_PUBLISHER_ID', 'ca-pub-XXXXXXXXXXXXXXXX')
    # Set to True once your AdSense is approved and you want ads to display
    ADSENSE_ENABLED = os.environ.get('ADSENSE_ENABLED', 'false').lower() == 'true'
