# Railway Deployment Guide

## ✅ Your Backend is Already Running!

Your backend is deployed at:
**https://tiktok-downloader-production-a1f0.up.railway.app/**

## 🔧 Files Changed for Railway

### 1. **main.py** (Updated)
- Uses `PORT` environment variable from Railway
- Optimized for Railway deployment
- CORS enabled for all origins

### 2. **app.js** (Updated)
- API_BASE_URL: `https://tiktok-downloader-production-a1f0.up.railway.app/api/v1`
- WS_URL: `wss://tiktok-downloader-production-a1f0.up.railway.app/ws`
- Download links point to your Railway backend

### 3. **New Files Added**
- `Procfile` - Railway startup command
- `railway.json` - Railway configuration

## 🚀 Frontend Deployment Options

### Option 1: Deploy Frontend on Vercel (Recommended)

```bash
# 1. Install Vercel CLI
npm install -g vercel

# 2. In your project folder
vercel

# Follow prompts:
# - Set up project: Yes
# - Link to existing project: No
# - Project name: video-downloader
# - Directory: ./ (current directory)
# - Build command: (leave empty)
# - Output directory: ./ (current directory)
```

Your frontend will be live at: `https://video-downloader-xxx.vercel.app`

### Option 2: Deploy Frontend on Netlify

```bash
# 1. Install Netlify CLI
npm install -g netlify-cli

# 2. In your project folder
netlify deploy

# Follow prompts:
# - Create new site
# - Build command: (leave empty)
# - Publish directory: .
```

### Option 3: Deploy Frontend on Railway (Static Site)

1. Create new project on Railway
2. Select "Deploy from GitHub"
3. Connect your repository
4. Railway will auto-detect static files
5. Set environment variables (none needed for frontend)

### Option 4: GitHub Pages (Free)

```bash
# 1. Push to GitHub
git init
git add .
git commit -m "Video downloader app"
git branch -M main
git remote add origin https://github.com/yourusername/video-downloader.git
git push -u origin main

# 2. Enable GitHub Pages
# Go to: Settings → Pages
# Source: main branch
# Folder: / (root)
```

Your site: `https://yourusername.github.io/video-downloader`

## 📁 Files You Need to Deploy

### Frontend Files (deploy these):
- `index.html`
- `youtube.html`
- `tiktok.html`
- `instagram.html`
- `styles.css`
- **`app.js`** ← MUST use the updated version
- Any other HTML pages you created

### Backend Files (already on Railway):
- `main.py` ← Already deployed
- `requirements.txt` ← Already deployed

## 🔍 Testing Your Setup

### 1. Test Backend API

```bash
# Health check
curl https://tiktok-downloader-production-a1f0.up.railway.app/api/v1/health

# Should return:
# {"status":"healthy","active_downloads":0,"queued":0}
```

### 2. Test Frontend Locally

```bash
# Open index.html in browser
# Or use Python server:
python -m http.server 8080

# Then open: http://localhost:8080
```

### 3. Verify Connection

1. Open your deployed frontend
2. Paste a YouTube URL
3. Check browser console (F12)
4. Should see: "API connection established to Railway backend"

## ⚙️ Environment Variables (Railway Backend)

Already set on your Railway project:
- `PORT` - Auto-set by Railway
- `MAX_CONCURRENT_DOWNLOADS` - 4 (default)

To add more:
1. Go to Railway dashboard
2. Select your project
3. Variables tab
4. Add variables

## 🐛 Troubleshooting

### "Cannot connect to server"

**Check**: Is Railway backend running?
- Visit: https://tiktok-downloader-production-a1f0.up.railway.app/
- Should show: `{"message":"Video Downloader API","version":"1.0.0"}`

**Fix**: 
1. Check Railway logs
2. Ensure all dependencies in `requirements.txt`
3. Verify Python version (3.9+)

### CORS Errors

**Fix**: Already handled in updated `main.py`
```python
allow_origins=["*"]  # Allows all origins
```

### WebSocket not connecting

**Fix**: Railway auto-supports WebSockets
- Ensure using `wss://` not `ws://`
- Check firewall settings

### Downloads not working

**Check**:
1. ffmpeg installed on Railway (should auto-install)
2. `/tmp/downloads` directory accessible
3. Railway disk space available

## 📊 Railway Dashboard

Monitor your backend:
- Logs: Real-time application logs
- Metrics: CPU, Memory usage
- Deployments: View deployment history

Access: https://railway.app/dashboard

## 💰 Railway Pricing

- **Free Tier**: $5/month credit
- **Pro Plan**: $20/month for more resources

Your app should fit in free tier for light usage.

## 🔄 Updating Your App

### Update Backend (Railway):

```bash
# Railway auto-deploys from GitHub
# Just push to your connected repo:
git add main.py
git commit -m "Update backend"
git push

# Or redeploy manually:
# Railway Dashboard → Deployments → Deploy
```

### Update Frontend:

Depends on hosting platform:
- **Vercel**: `vercel --prod`
- **Netlify**: `netlify deploy --prod`
- **GitHub Pages**: `git push`

## 📝 Quick Checklist

Before going live:
- [ ] Backend running on Railway ✅ (Already done!)
- [ ] Frontend files have updated `app.js`
- [ ] Test analyze endpoint
- [ ] Test download endpoint
- [ ] Test WebSocket connection
- [ ] Mobile responsive check
- [ ] Cross-browser test

## 🎉 You're Ready!

Your backend is live at:
**https://tiktok-downloader-production-a1f0.up.railway.app/**

Just deploy your frontend with the updated files and you're done!

---

**Need help?**
- Railway Docs: https://docs.railway.app/
- Check Railway logs for errors
- Test API endpoints with Postman
