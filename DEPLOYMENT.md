# Production Deployment Guide

## Quick Start (Development)

```bash
# 1. Install dependencies
chmod +x start.sh
./start.sh

# 2. Open browser
# Navigate to http://localhost:8000
```

## Production Deployment on Ubuntu Server

### 1. System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-venv ffmpeg nginx

# Create application directory
sudo mkdir -p /var/www/videodownloader
cd /var/www/videodownloader

# Upload files
# Use SCP, FTP, or Git to upload all project files
```

### 2. Python Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Create downloads directory
sudo mkdir -p /var/www/downloads
sudo chown www-data:www-data /var/www/downloads
sudo chmod 775 /var/www/downloads
```

### 3. Configure Application

Edit `main.py` and update:

```python
DOWNLOAD_DIR = Path("/var/www/downloads")
```

### 4. Create Systemd Service

Create `/etc/systemd/system/videodownloader.service`:

```ini
[Unit]
Description=Video Downloader API
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/videodownloader
Environment="PATH=/var/www/videodownloader/venv/bin"
ExecStart=/var/www/videodownloader/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable videodownloader
sudo systemctl start videodownloader
sudo systemctl status videodownloader
```

### 5. Configure Nginx

Create `/etc/nginx/sites-available/videodownloader`:

```nginx
# Rate limiting
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Max upload size
    client_max_body_size 100M;

    # Root directory for static files
    root /var/www/videodownloader;
    index index.html;

    # Static files
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API endpoints
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Downloads
    location /downloads/ {
        alias /var/www/downloads/;
        add_header Content-Disposition 'attachment';
        add_header X-Content-Type-Options nosniff;
    }

    # Health check
    location /api/v1/health {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/videodownloader /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 6. SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### 7. Firewall Setup

```bash
# Enable firewall
sudo ufw enable

# Allow SSH, HTTP, HTTPS
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Check status
sudo ufw status
```

### 8. Monitoring & Logs

```bash
# View application logs
sudo journalctl -u videodownloader -f

# View Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Check disk space (for downloads)
df -h /var/www/downloads
```

### 9. Auto-Cleanup Script

Create `/var/www/videodownloader/cleanup.sh`:

```bash
#!/bin/bash
# Remove downloads older than 1 hour
find /var/www/downloads -type f -mmin +60 -delete
```

Add to crontab:

```bash
sudo crontab -e
# Add line:
*/30 * * * * /var/www/videodownloader/cleanup.sh
```

### 10. Performance Optimization

Edit `main.py` for production:

```python
# Increase workers based on CPU cores
MAX_CONCURRENT_DOWNLOADS = 8  # Adjust based on server capacity

# Larger playlist support
MAX_PLAYLIST_SIZE = 2000
```

### 11. Security Hardening

```bash
# Update yt-dlp regularly
source venv/bin/activate
pip install --upgrade yt-dlp

# Keep system updated
sudo apt update && sudo apt upgrade -y

# Monitor logs for suspicious activity
sudo tail -f /var/log/nginx/access.log | grep -E "POST|download"
```

## Docker Deployment (Alternative)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create downloads directory
RUN mkdir -p /tmp/downloads

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./downloads:/tmp/downloads
    environment:
      - MAX_CONCURRENT_DOWNLOADS=4
    restart: unless-stopped
```

Deploy:

```bash
docker-compose up -d
docker-compose logs -f
```

## Monitoring & Maintenance

### Health Checks

```bash
# API health
curl http://yourdomain.com/api/v1/health

# Response should be:
# {"status":"healthy","active_downloads":0,"queued":0}
```

### Performance Monitoring

Use tools like:
- **Uptime Kuma** - Uptime monitoring
- **Prometheus** + **Grafana** - Metrics
- **New Relic** - APM

### Backup Strategy

```bash
# Backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
tar -czf /backup/videodownloader-$DATE.tar.gz /var/www/videodownloader
find /backup -name "videodownloader-*.tar.gz" -mtime +7 -delete
```

## Scaling

For high traffic:

1. **Horizontal Scaling**: Multiple app servers behind load balancer
2. **Redis Queue**: Replace in-memory queue with Redis
3. **PostgreSQL**: Use real database instead of in-memory storage
4. **CDN**: Serve downloads through CDN
5. **Object Storage**: Use S3/MinIO for downloads

## Troubleshooting

### Server Won't Start

```bash
# Check logs
sudo journalctl -u videodownloader -n 100

# Check if port is in use
sudo netstat -tulpn | grep 8000

# Test manually
cd /var/www/videodownloader
source venv/bin/activate
python3 main.py
```

### Downloads Failing

```bash
# Update yt-dlp
pip install --upgrade yt-dlp

# Check FFmpeg
ffmpeg -version

# Check disk space
df -h

# Check permissions
ls -la /var/www/downloads
```

### High Memory Usage

```bash
# Reduce workers in systemd service
# Edit MAX_CONCURRENT_DOWNLOADS in main.py

# Restart service
sudo systemctl restart videodownloader
```

## Support

For production issues:
1. Check logs first
2. Verify all dependencies are updated
3. Ensure adequate server resources
4. Monitor disk space for downloads

---

**Production Checklist:**
- [ ] SSL certificate installed
- [ ] Firewall configured
- [ ] Auto-cleanup script running
- [ ] Monitoring setup
- [ ] Backup strategy in place
- [ ] Error logging configured
- [ ] Regular yt-dlp updates scheduled
- [ ] Server resources adequate
- [ ] Domain DNS configured
- [ ] Rate limiting tested
