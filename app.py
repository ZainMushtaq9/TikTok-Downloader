from flask import Flask, request, jsonify, Response, render_template, send_from_directory
from config import Config
from utils.url_normalizer import analyze_url
from utils.downloader import get_metadata, get_playlist_data, download_stream
from utils.ai_service import generate_summary, recommend_format, extract_urls_from_text
from utils.rate_limiter import check_rate_limit
from utils.health_checker import get_platform_health
import os
import time

app = Flask(__name__)
app.config.from_object(Config)

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

@app.before_request
def rate_limit_check():
    # Only limit API download endpoints
    if request.path == '/api/download':
        ip = get_client_ip()
        allowed, retry_after = check_rate_limit(ip, app.config['RATE_LIMIT_PER_HOUR'])
        if not allowed:
            return jsonify({
                'error': 'Rate limit exceeded', 
                'code': '429', 
                'retry_after': retry_after
            }), 429

# Inject AdSense config into all templates automatically
@app.context_processor
def inject_adsense():
    return {
        'adsense_enabled': Config.ADSENSE_ENABLED,
        'adsense_pub_id': Config.ADSENSE_PUBLISHER_ID
    }

# --- Page Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/playlist-downloader')
def playlist_downloader():
    return render_template('playlist.html')

@app.route('/profile-downloader')
def profile_downloader():
    return render_template('profile.html')

@app.route('/youtube-to-mp3')
def youtube_mp3():
    return render_template('youtube-to-mp3.html')

@app.route('/transcript-downloader')
def transcript():
    return render_template('transcript.html')

@app.route('/batch-downloader')
def batch_downloader():
    return render_template('batch.html')

@app.route('/watermark-remover')
def watermark():
    return render_template('watermark.html')

@app.route('/thumbnail-downloader')
def thumbnail():
    return render_template('thumbnail.html')

@app.route('/gif-downloader')
def gif_downloader():
    return render_template('gif.html')

# SEO & Legal Pages
@app.route('/privacy')
def privacy(): return render_template('privacy.html')
@app.route('/terms')
def terms(): return render_template('terms.html')
@app.route('/dmca')
def dmca(): return render_template('dmca.html')
@app.route('/about')
def about(): return render_template('about.html')
@app.route('/contact')
def contact(): return render_template('contact.html')

# Catch-all for SEO tool pages (like /youtube-video-downloader)
@app.route('/<platform>-video-downloader')
def platform_tool(platform):
    return render_template('index.html', prefill_platform=platform)

# Static files mapping
@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory(app.root_path, 'sitemap.xml', mimetype='text/xml')

@app.route('/robots.txt')
def robots():
    return send_from_directory(app.root_path, 'robots.txt', mimetype='text/plain')


# --- API Routes ---
@app.route('/api/detect', methods=['POST'])
def api_detect():
    data = request.json
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400
        
    analysis = analyze_url(url)
    return jsonify(analysis)

@app.route('/api/metadata', methods=['POST'])
def api_metadata():
    data = request.json
    if not data:
        return jsonify({'error': 'Invalid request body'}), 400

    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400

    try:
        analysis = analyze_url(url)
        
        if analysis['platform'] == 'unknown':
            return jsonify({'error': 'Unsupported platform', 'platform': 'unknown'}), 400
        
        # Use threading to enforce a HARD 10-second timeout on metadata fetching
        # This ensures the frontend NEVER hangs, even if Instagram/Facebook block us
        import threading
        result_holder = [None]
        
        def fetch_meta():
            result_holder[0] = get_metadata(analysis['url'], analysis['platform'])
        
        thread = threading.Thread(target=fetch_meta)
        thread.start()
        thread.join(timeout=10)  # Wait max 10 seconds
        
        meta = result_holder[0]
        
        platform_name = analysis['platform'].capitalize()
        
        if not meta:
            # Return fallback that still shows the format selector
            return jsonify({
                'title': f'{platform_name} Video',
                'uploader': platform_name,
                'thumbnail': '',
                'duration': 0,
                'formats': [
                    {'format_id': 'best', 'ext': 'mp4', 'resolution': '1080p', 'size': 'Auto', 'vcodec': 'h264', 'acodec': 'aac'},
                    {'format_id': 'good', 'ext': 'mp4', 'resolution': '720p', 'size': 'Auto', 'vcodec': 'h264', 'acodec': 'aac'},
                    {'format_id': 'fast', 'ext': 'mp4', 'resolution': '480p', 'size': 'Auto', 'vcodec': 'h264', 'acodec': 'aac'},
                    {'format_id': 'audio', 'ext': 'mp3', 'resolution': 'Audio', 'size': 'Auto', 'vcodec': 'none', 'acodec': 'mp3'}
                ],
                'aiSummary': f'{platform_name} video detected. Select quality and download below.',
                'recommendation': {'format': 'MP4', 'quality': '1080p', 'reason': 'Best quality for most devices.'},
                'platform': analysis['platform']
            })
            
        # Generate AI summary (won't crash even without API key)
        ai_summary = generate_summary(meta.get('title', ''), "")
        
        # Generate format recommendation
        duration = meta.get('duration', 0)
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
        recommendation = recommend_format(analysis['platform'], meta.get('title', ''), duration_str)
        
        return jsonify({
            **meta,
            'aiSummary': ai_summary,
            'recommendation': recommendation,
            'platform': analysis['platform']
        })
    except Exception as e:
        print(f"Metadata API error: {e}")
        return jsonify({'error': str(e), 'platform': 'unknown'}), 500

@app.route('/api/download', methods=['POST', 'GET'])
def api_download():
    # Support GET for direct browser downloads, POST for XHR
    if request.method == 'POST':
        data = request.json
        url = data.get('url') if data else None
        format_type = data.get('format', 'mp4') if data else 'mp4'
        quality = data.get('quality', '1080') if data else '1080'
    else:
        url = request.args.get('url')
        format_type = request.args.get('format', 'mp4')
        quality = request.args.get('quality', '1080')
        
    if not url:
        return jsonify({'error': 'URL required'}), 400
        
    try:
        analysis = analyze_url(url)
        platform = analysis['platform']
        
        # Spawn yt-dlp
        process = download_stream(analysis['url'], format_type, quality, platform)
        
        ext = format_type if format_type in ['mp4', 'mp3', 'webm', 'm4a'] else 'mp4'
        filename = f"xainvex_{int(time.time())}.{ext}"
        
        # Stream the output directly to the client
        def generate():
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                yield chunk
            process.wait()
                
        return Response(
            generate(),
            mimetype=f'video/{ext}' if ext != 'mp3' else 'audio/mpeg',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/playlist/fetch', methods=['POST'])
def api_playlist_fetch():
    data = request.json
    if not data:
        return jsonify({'error': 'Invalid request body'}), 400
    
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400
    
    try:
        analysis = analyze_url(url)
        playlist_data = get_playlist_data(analysis['url'])
        if not playlist_data:
            return jsonify({'error': 'Failed to fetch playlist/profile. The content may be private or the platform may require authentication.'}), 400
            
        return jsonify(playlist_data)
    except Exception as e:
        print(f"Playlist fetch error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai/extract-urls', methods=['POST'])
def api_extract_urls():
    data = request.json
    if not data:
        return jsonify({'error': 'Invalid request body'}), 400
    
    text = data.get('text', '')
    if not text.strip():
        return jsonify({'urls': []}), 200
    
    urls = extract_urls_from_text(text)
    return jsonify({'urls': urls})

@app.route('/api/health')
def api_health():
    return jsonify({'platforms': get_platform_health()})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
