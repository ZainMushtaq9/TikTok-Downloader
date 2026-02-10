// VIDEO DOWNLOADER - Mobile Responsive + 5s Delay Queue
const CONFIG = {
    API_BASE_URL: 'https://tiktok-downloader-production-a1f0.up.railway.app/api/v1',
    WS_URL: 'wss://tiktok-downloader-production-a1f0.up.railway.app/ws',
    MAX_VIDEOS_PER_PAGE: 20,
    REQUEST_TIMEOUT: 60000,
    DOWNLOAD_DELAY: 5
};

class AppState {
    constructor() {
        this.sessionId = null;
        this.videos = [];
        this.selectedVideos = new Set();
        this.currentPage = 1;
        this.downloadJobs = new Map();
    }
    reset() {
        this.sessionId = null;
        this.videos = [];
        this.selectedVideos.clear();
        this.currentPage = 1;
    }
    addVideos(videos) { this.videos.push(...videos); }
    toggleVideo(videoId) {
        this.selectedVideos.has(videoId) ? this.selectedVideos.delete(videoId) : this.selectedVideos.add(videoId);
    }
    selectAll() { this.videos.forEach(v => this.selectedVideos.add(v.id)); }
    deselectAll() { this.selectedVideos.clear(); }
    getSelectedVideos() { return this.videos.filter(v => this.selectedVideos.has(v.id)); }
}

const state = new AppState();

class APIClient {
    static async request(endpoint, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT);
        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
                ...options,
                signal: controller.signal,
                headers: { 'Content-Type': 'application/json', ...options.headers }
            });
            clearTimeout(timeout);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || `Error ${response.status}`);
            return data;
        } catch (error) {
            clearTimeout(timeout);
            if (error.name === 'AbortError') throw new Error('Request timeout');
            throw error;
        }
    }
    static analyzeURL(url) { return this.request('/analyze', { method: 'POST', body: JSON.stringify({ url }) }); }
    static getVideos(sessionId, page = 1) { return this.request(`/videos/${sessionId}?page=${page}&limit=${CONFIG.MAX_VIDEOS_PER_PAGE}`); }
    static downloadVideos(sessionId, videoIds, format = 'best', quality = null) {
        return this.request('/download', { method: 'POST', body: JSON.stringify({ session_id: sessionId, video_ids: videoIds, format, quality }) });
    }
    static getProgress(jobId) { return this.request(`/progress/${jobId}`); }
}

class WebSocketManager {
    constructor() { this.ws = null; }
    connect(sessionId) {
        if (this.ws?.readyState === WebSocket.OPEN) return;
        try {
            this.ws = new WebSocket(`${CONFIG.WS_URL}/${sessionId}`);
            this.ws.onmessage = (e) => this.handleMessage(JSON.parse(e.data));
        } catch (e) { console.error('WebSocket error:', e); }
    }
    handleMessage(data) {
        if (data.type === 'progress') UI.updateProgress(data.job_id, data.progress);
        else if (data.type === 'complete') UI.markComplete(data.job_id, data.file_path);
        else if (data.type === 'error') UI.markError(data.job_id, data.error);
    }
    disconnect() { this.ws?.close(); }
}

const wsManager = new WebSocketManager();

class UI {
    static showError(msg) {
        const el = document.getElementById('urlError');
        if (el) {
            el.textContent = msg;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }
    }
    static setLoading(id, loading) {
        const btn = document.getElementById(id);
        if (!btn) return;
        btn.disabled = loading;
        const text = btn.querySelector('.btn-text');
        const loader = btn.querySelector('.btn-loader');
        if (text) text.style.display = loading ? 'none' : 'inline';
        if (loader) loader.style.display = loading ? 'inline-block' : 'none';
    }
    static show(id) {
        const el = document.getElementById(id);
        if (el) {
            el.style.display = 'block';
            setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
        }
    }
    static updatePlaylistHeader(title, count) {
        const header = document.getElementById('playlistHeader');
        const titleEl = document.getElementById('playlistTitle');
        const info = document.getElementById('playlistInfo');
        if (titleEl) titleEl.textContent = title;
        if (info) info.textContent = `${count} video${count !== 1 ? 's' : ''} found`;
        if (header) header.style.display = 'block';
    }
    static renderVideos(videos) {
        const grid = document.getElementById('videoGrid');
        if (!grid) return;
        videos.forEach(v => grid.appendChild(this.createVideoCard(v)));
    }
    static createVideoCard(video) {
        const card = document.createElement('div');
        card.className = 'video-card';
        card.dataset.videoId = video.id;
        if (state.selectedVideos.has(video.id)) card.classList.add('selected');
        const thumb = video.thumbnail || 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="320" height="180"%3E%3Crect fill="%23ddd" width="320" height="180"/%3E%3C/svg%3E';
        card.innerHTML = `
            <div class="video-thumbnail-container">
                <img src="${thumb}" alt="${this.escape(video.title)}" class="video-thumbnail" loading="lazy">
                <input type="checkbox" class="video-checkbox" ${state.selectedVideos.has(video.id) ? 'checked' : ''}>
                <div class="video-duration">${this.formatDuration(video.duration)}</div>
            </div>
            <div class="video-info">
                <h3 class="video-title">${this.escape(video.title)}</h3>
                <div class="video-meta">
                    <span class="video-platform">${video.platform}</span>
                    ${video.views ? `<span>•</span><span>${this.formatViews(video.views)}</span>` : ''}
                </div>
            </div>
        `;
        const checkbox = card.querySelector('.video-checkbox');
        checkbox.addEventListener('change', (e) => { e.stopPropagation(); this.toggleVideo(video.id); });
        card.addEventListener('click', (e) => { if (e.target !== checkbox) { checkbox.checked = !checkbox.checked; this.toggleVideo(video.id); } });
        return card;
    }
    static toggleVideo(videoId) {
        state.toggleVideo(videoId);
        const card = document.querySelector(`[data-video-id="${videoId}"]`);
        if (!card) return;
        const checkbox = card.querySelector('.video-checkbox');
        if (state.selectedVideos.has(videoId)) {
            card.classList.add('selected');
            checkbox.checked = true;
        } else {
            card.classList.remove('selected');
            checkbox.checked = false;
        }
        this.updateSelectedCount();
        this.updateDownloadButton();
    }
    static updateSelectedCount() {
        const el = document.getElementById('selectedCount');
        if (el) el.textContent = `${state.selectedVideos.size} selected`;
    }
    static updateDownloadButton() {
        const btn = document.getElementById('downloadSelectedBtn');
        if (btn) btn.disabled = state.selectedVideos.size === 0;
    }
    static clearVideoGrid() {
        const grid = document.getElementById('videoGrid');
        if (grid) grid.innerHTML = '';
    }
    static showLoadMore(hasMore) {
        const el = document.getElementById('loadMoreContainer');
        if (el) el.style.display = hasMore ? 'block' : 'none';
    }
    static addToQueue(jobId, title, pos, total) {
        const list = document.getElementById('downloadQueueList');
        if (!list) return;
        const item = document.createElement('div');
        item.className = 'queue-item';
        item.dataset.jobId = jobId;
        const delay = pos === 1 ? 'Starting now' : `Starts in ${(pos - 1) * CONFIG.DOWNLOAD_DELAY}s`;
        item.innerHTML = `
            <div class="queue-number">#${pos}/${total}</div>
            <div class="queue-content">
                <div class="queue-title">${this.escape(title)}</div>
                <div class="queue-status">
                    <span class="status-badge queued">⏳ Queued</span>
                    <div class="progress-bar-container"><div class="progress-bar" style="width:0%"></div></div>
                    <span class="progress-text">${delay}</span>
                </div>
            </div>
        `;
        list.appendChild(item);
    }
    static updateProgress(jobId, progress) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;
        const badge = item.querySelector('.status-badge');
        const bar = item.querySelector('.progress-bar');
        const text = item.querySelector('.progress-text');
        if (badge) {
            badge.className = 'status-badge downloading';
            badge.textContent = '⬇ Downloading';
        }
        if (bar) bar.style.width = `${progress}%`;
        if (text) text.textContent = `${progress}%`;
    }
    static markComplete(jobId, filePath) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;
        const badge = item.querySelector('.status-badge');
        const bar = item.querySelector('.progress-bar');
        const text = item.querySelector('.progress-text');
        if (badge) {
            badge.className = 'status-badge completed';
            badge.textContent = '✓ Completed';
        }
        if (bar) bar.style.width = '100%';
        if (text) text.textContent = 'Downloaded';
        if (filePath) {
            // Properly encode the URL to handle special characters
            const baseUrl = 'https://tiktok-downloader-production-a1f0.up.railway.app';
            const encodedPath = filePath.split('/').map(part => encodeURIComponent(part)).join('/');
            const link = document.createElement('a');
            link.href = baseUrl + encodedPath;
            link.download = '';
            link.style.display = 'none';
            document.body.appendChild(link);
            setTimeout(() => { link.click(); document.body.removeChild(link); }, 100);
        }
    }
    static markError(jobId, error) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;
        const badge = item.querySelector('.status-badge');
        const text = item.querySelector('.progress-text');
        if (badge) {
            badge.className = 'status-badge failed';
            badge.textContent = '✗ Failed';
        }
        if (text) text.textContent = error || 'Failed';
    }
    static formatDuration(s) {
        if (!s) return '0:00';
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const sec = Math.floor(s % 60);
        return h > 0 ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}` : `${m}:${String(sec).padStart(2,'0')}`;
    }
    static formatViews(v) {
        if (!v) return '';
        if (v >= 1000000) return `${(v/1000000).toFixed(1)}M`;
        if (v >= 1000) return `${(v/1000).toFixed(1)}K`;
        return v;
    }
    static escape(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
}

async function handleAnalyze() {
    const input = document.getElementById('urlInput');
    if (!input) return;
    const url = input.value.trim();
    if (!url) return UI.showError('Please enter a URL');
    try { new URL(url); } catch { return UI.showError('Invalid URL'); }
    
    UI.setLoading('analyzeBtn', true);
    state.reset();
    UI.clearVideoGrid();
    
    try {
        const response = await APIClient.analyzeURL(url);
        state.sessionId = response.session_id;
        if (response.is_playlist) UI.updatePlaylistHeader(response.playlist_title, response.total_videos);
        await loadVideos(1);
        UI.show('videoListSection');
        wsManager.connect(state.sessionId);
    } catch (error) {
        UI.showError(error.message || 'Failed to analyze URL');
    } finally {
        UI.setLoading('analyzeBtn', false);
    }
}

async function loadVideos(page) {
    try {
        const response = await APIClient.getVideos(state.sessionId, page);
        state.addVideos(response.videos);
        UI.renderVideos(response.videos);
        UI.showLoadMore(response.has_more);
        if (response.has_more) state.currentPage = page;
    } catch (error) {
        UI.showError('Failed to load videos');
    }
}

async function handleDownload() {
    const selected = state.getSelectedVideos();
    if (selected.length === 0) return UI.showError('Select at least one video');
    
    const formatSelect = document.getElementById('formatSelect');
    const format = formatSelect?.value || 'best';
    const quality = (format !== 'best' && format !== 'audio') ? format : null;
    const actualFormat = format === 'audio' ? 'audio' : 'best';
    
    UI.setLoading('downloadSelectedBtn', true);
    
    try {
        const videoIds = selected.map(v => v.id);
        const response = await APIClient.downloadVideos(state.sessionId, videoIds, actualFormat, quality);
        
        UI.show('downloadQueueSection');
        
        // Show estimated time
        if (response.estimated_time > 0) {
            const minutes = Math.floor(response.estimated_time / 60);
            const seconds = response.estimated_time % 60;
            const timeStr = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
            const subtitle = document.querySelector('.section-subtitle');
            if (subtitle) {
                subtitle.textContent = `${response.total_jobs} videos queued. Estimated time: ${timeStr} (5s delay between each)`;
            }
        }
        
        response.jobs.forEach((job, i) => {
            const video = selected.find(v => v.id === job.video_id);
            if (video) {
                UI.addToQueue(job.job_id, video.title, job.position, response.total_jobs);
                pollProgress(job.job_id);
            }
        });
    } catch (error) {
        UI.showError(error.message || 'Download failed');
    } finally {
        UI.setLoading('downloadSelectedBtn', false);
    }
}

async function pollProgress(jobId) {
    let attempts = 0;
    const interval = setInterval(async () => {
        if (attempts++ > 600) {
            clearInterval(interval);
            return UI.markError(jobId, 'Timeout');
        }
        try {
            const progress = await APIClient.getProgress(jobId);
            if (progress.status === 'downloading') UI.updateProgress(jobId, progress.progress);
            else if (progress.status === 'completed') { UI.markComplete(jobId, progress.file_path); clearInterval(interval); }
            else if (progress.status === 'failed') { UI.markError(jobId, progress.error); clearInterval(interval); }
        } catch (e) { console.error('Poll error:', e); }
    }, 1000);
}

function handleSelectAll() {
    state.selectAll();
    document.querySelectorAll('.video-card').forEach(card => {
        card.classList.add('selected');
        card.querySelector('.video-checkbox').checked = true;
    });
    UI.updateSelectedCount();
    UI.updateDownloadButton();
}

function handleDeselectAll() {
    state.deselectAll();
    document.querySelectorAll('.video-card').forEach(card => {
        card.classList.remove('selected');
        card.querySelector('.video-checkbox').checked = false;
    });
    UI.updateSelectedCount();
    UI.updateDownloadButton();
}

function handleLoadMore() { loadVideos(state.currentPage + 1); }

function initTheme() {
    const toggle = document.getElementById('themeToggle');
    if (!toggle) return;
    const theme = localStorage.getItem('theme') || 'dark';
    document.body.setAttribute('data-theme', theme);
    toggle.addEventListener('click', () => {
        const current = document.body.getAttribute('data-theme');
        const newTheme = current === 'dark' ? 'light' : 'dark';
        document.body.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
    });
}

function initMobileMenu() {
    const toggle = document.getElementById('mobileMenuToggle');
    const nav = document.querySelector('.nav');
    if (toggle && nav) {
        toggle.addEventListener('click', () => {
            nav.classList.toggle('active');
            toggle.classList.toggle('active');
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('analyzeBtn')?.addEventListener('click', handleAnalyze);
    document.getElementById('downloadSelectedBtn')?.addEventListener('click', handleDownload);
    document.getElementById('selectAllBtn')?.addEventListener('click', handleSelectAll);
    document.getElementById('deselectAllBtn')?.addEventListener('click', handleDeselectAll);
    document.getElementById('loadMoreBtn')?.addEventListener('click', handleLoadMore);
    document.getElementById('urlInput')?.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleAnalyze(); });
    initTheme();
    initMobileMenu();
});
