// VIDEO DOWNLOADER - AUTO QUEUE SYSTEM
const CONFIG = {
    API_BASE_URL: 'https://tiktok-downloader-production-a1f0.up.railway.app/api/v1',
    WS_URL: 'wss://tiktok-downloader-production-a1f0.up.railway.app/ws',
    MAX_VIDEOS_PER_PAGE: 20,
    REQUEST_TIMEOUT: 60000
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
        if (this.selectedVideos.has(videoId)) {
            this.selectedVideos.delete(videoId);
        } else {
            this.selectedVideos.add(videoId);
        }
    }
    selectAll() { this.videos.forEach(video => this.selectedVideos.add(video.id)); }
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
            if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
            return data;
        } catch (error) {
            clearTimeout(timeout);
            if (error.name === 'AbortError') throw new Error('Request timeout');
            throw error;
        }
    }
    static async analyzeURL(url) { return this.request('/analyze', { method: 'POST', body: JSON.stringify({ url }) }); }
    static async getVideos(sessionId, page = 1, limit = CONFIG.MAX_VIDEOS_PER_PAGE) {
        return this.request(`/videos/${sessionId}?page=${page}&limit=${limit}`);
    }
    static async downloadVideos(sessionId, videoIds, format = 'best', quality = null) {
        return this.request('/download', {
            method: 'POST',
            body: JSON.stringify({ session_id: sessionId, video_ids: videoIds, format, quality })
        });
    }
    static async getProgress(jobId) { return this.request(`/progress/${jobId}`); }
}

class WebSocketManager {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
    }
    connect(sessionId) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) return;
        try {
            this.ws = new WebSocket(`${CONFIG.WS_URL}/${sessionId}`);
            this.ws.onopen = () => { this.reconnectAttempts = 0; };
            this.ws.onmessage = (event) => this.handleMessage(JSON.parse(event.data));
        } catch (error) { console.error('WebSocket error:', error); }
    }
    handleMessage(data) {
        if (data.type === 'progress') UI.updateProgress(data.job_id, data.progress);
        else if (data.type === 'complete') UI.markComplete(data.job_id, data.file_path);
        else if (data.type === 'error') UI.markError(data.job_id, data.error);
    }
    disconnect() { if (this.ws) this.ws.close(); }
}

const wsManager = new WebSocketManager();

class UI {
    static showError(message) {
        const errorEl = document.getElementById('urlError');
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.style.display = 'block';
            setTimeout(() => errorEl.style.display = 'none', 5000);
        }
    }
    static setLoading(elementId, isLoading) {
        const btn = document.getElementById(elementId);
        if (!btn) return;
        btn.disabled = isLoading;
        const textEl = btn.querySelector('.btn-text');
        const loaderEl = btn.querySelector('.btn-loader');
        if (textEl) textEl.style.display = isLoading ? 'none' : 'inline';
        if (loaderEl) loaderEl.style.display = isLoading ? 'flex' : 'none';
    }
    static showVideoList() {
        const section = document.getElementById('videoListSection');
        if (section) {
            section.style.display = 'block';
            section.scrollIntoView({ behavior: 'smooth' });
        }
    }
    static updatePlaylistHeader(title, count) {
        const headerEl = document.getElementById('playlistHeader');
        const titleEl = document.getElementById('playlistTitle');
        const infoEl = document.getElementById('playlistInfo');
        if (titleEl) titleEl.textContent = title;
        if (infoEl) infoEl.textContent = `${count} video${count !== 1 ? 's' : ''} found`;
        if (headerEl) headerEl.style.display = 'block';
    }
    static renderVideos(videos) {
        const grid = document.getElementById('videoGrid');
        if (!grid) return;
        videos.forEach(video => grid.appendChild(this.createVideoCard(video)));
    }
    static createVideoCard(video) {
        const card = document.createElement('div');
        card.className = 'video-card';
        card.dataset.videoId = video.id;
        if (state.selectedVideos.has(video.id)) card.classList.add('selected');
        const thumbnail = video.thumbnail || 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="320" height="180"%3E%3Crect fill="%23ddd" width="320" height="180"/%3E%3C/svg%3E';
        card.innerHTML = `
            <div class="video-thumbnail-container">
                <img src="${thumbnail}" alt="${this.escapeHtml(video.title)}" class="video-thumbnail" loading="lazy">
                <input type="checkbox" class="video-checkbox" ${state.selectedVideos.has(video.id) ? 'checked' : ''} data-video-id="${video.id}">
                <div class="video-duration">${this.formatDuration(video.duration)}</div>
            </div>
            <div class="video-info">
                <h3 class="video-title">${this.escapeHtml(video.title)}</h3>
                <div class="video-meta">
                    <span class="video-platform">${video.platform}</span>
                    ${video.views ? `<span>•</span><span>${this.formatViews(video.views)}</span>` : ''}
                </div>
            </div>
        `;
        const checkbox = card.querySelector('.video-checkbox');
        checkbox.addEventListener('change', (e) => { e.stopPropagation(); this.handleVideoToggle(video.id); });
        card.addEventListener('click', (e) => {
            if (e.target !== checkbox) {
                checkbox.checked = !checkbox.checked;
                this.handleVideoToggle(video.id);
            }
        });
        return card;
    }
    static handleVideoToggle(videoId) {
        state.toggleVideo(videoId);
        const card = document.querySelector(`[data-video-id="${videoId}"]`);
        if (!card) return;
        const checkbox = card.querySelector('.video-checkbox');
        if (state.selectedVideos.has(videoId)) {
            card.classList.add('selected');
            if (checkbox) checkbox.checked = true;
        } else {
            card.classList.remove('selected');
            if (checkbox) checkbox.checked = false;
        }
        this.updateSelectedCount();
        this.updateDownloadButton();
    }
    static updateSelectedCount() {
        const countEl = document.getElementById('selectedCount');
        if (countEl) countEl.textContent = `${state.selectedVideos.size} selected`;
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
        const container = document.getElementById('loadMoreContainer');
        if (container) container.style.display = hasMore ? 'block' : 'none';
    }
    static showDownloadQueue() {
        const section = document.getElementById('downloadQueueSection');
        if (section) {
            section.style.display = 'block';
            section.scrollIntoView({ behavior: 'smooth' });
        }
    }
    static addToQueue(jobId, videoTitle, position, total) {
        const list = document.getElementById('downloadQueueList');
        if (!list) return;
        const item = document.createElement('div');
        item.className = 'queue-item';
        item.dataset.jobId = jobId;
        item.innerHTML = `
            <div class="queue-number">#${position}/${total}</div>
            <div class="queue-content">
                <div class="queue-title">${this.escapeHtml(videoTitle)}</div>
                <div class="queue-status">
                    <span class="status-badge queued">⏳ Queued</span>
                    <div class="progress-bar-container">
                        <div class="progress-bar" style="width: 0%"></div>
                    </div>
                    <span class="progress-text">Waiting...</span>
                </div>
            </div>
        `;
        list.appendChild(item);
    }
    static updateProgress(jobId, progress) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;
        const statusBadge = item.querySelector('.status-badge');
        const progressBar = item.querySelector('.progress-bar');
        const progressText = item.querySelector('.progress-text');
        if (statusBadge) {
            statusBadge.className = 'status-badge downloading';
            statusBadge.textContent = '⬇ Downloading';
        }
        if (progressBar) progressBar.style.width = `${progress}%`;
        if (progressText) progressText.textContent = `${progress}%`;
    }
    static markComplete(jobId, filePath) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;
        const statusBadge = item.querySelector('.status-badge');
        const progressBar = item.querySelector('.progress-bar');
        const progressText = item.querySelector('.progress-text');
        if (statusBadge) {
            statusBadge.className = 'status-badge completed';
            statusBadge.textContent = '✓ Downloaded';
        }
        if (progressBar) progressBar.style.width = '100%';
        if (progressText) progressText.textContent = 'Saved to downloads folder';
        // AUTOMATIC DOWNLOAD - File downloads automatically to browser
        if (filePath) {
            const link = document.createElement('a');
            link.href = `https://tiktok-downloader-production-a1f0.up.railway.app${filePath}`;
            link.download = '';
            link.style.display = 'none';
            document.body.appendChild(link);
            setTimeout(() => {
                link.click();
                document.body.removeChild(link);
            }, 200);
        }
    }
    static markError(jobId, error) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;
        const statusBadge = item.querySelector('.status-badge');
        const progressText = item.querySelector('.progress-text');
        if (statusBadge) {
            statusBadge.className = 'status-badge failed';
            statusBadge.textContent = '✗ Failed';
        }
        if (progressText) progressText.textContent = error || 'Download failed';
    }
    static formatDuration(seconds) {
        if (!seconds) return '0:00';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        return h > 0 ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${m}:${String(s).padStart(2,'0')}`;
    }
    static formatViews(views) {
        if (!views) return '';
        if (views >= 1000000) return `${(views / 1000000).toFixed(1)}M views`;
        if (views >= 1000) return `${(views / 1000).toFixed(1)}K views`;
        return `${views} views`;
    }
    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
}

// APP LOGIC
async function handleAnalyze() {
    const urlInput = document.getElementById('urlInput');
    if (!urlInput) return;
    const url = urlInput.value.trim();
    if (!url) {
        UI.showError('Please enter a valid URL');
        return;
    }
    try { new URL(url); } catch { UI.showError('Invalid URL format'); return; }
    UI.setLoading('analyzeBtn', true);
    state.reset();
    UI.clearVideoGrid();
    try {
        const response = await APIClient.analyzeURL(url);
        state.sessionId = response.session_id;
        if (response.is_playlist) {
            UI.updatePlaylistHeader(response.playlist_title, response.total_videos);
        }
        await loadVideos(1);
        UI.showVideoList();
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
    const selectedVideos = state.getSelectedVideos();
    if (selectedVideos.length === 0) {
        UI.showError('Please select at least one video');
        return;
    }
    const formatSelect = document.getElementById('formatSelect');
    const format = formatSelect ? formatSelect.value : 'best';
    const quality = format !== 'best' && format !== 'audio' ? format : null;
    const actualFormat = format === 'audio' ? 'audio' : 'best';
    UI.setLoading('downloadSelectedBtn', true);
    try {
        const videoIds = selectedVideos.map(v => v.id);
        const response = await APIClient.downloadVideos(state.sessionId, videoIds, actualFormat, quality);
        UI.showDownloadQueue();
        response.jobs.forEach((job, index) => {
            const video = selectedVideos.find(v => v.id === job.video_id);
            if (video) {
                UI.addToQueue(job.job_id, video.title, index + 1, response.jobs.length);
                state.downloadJobs.set(job.job_id, video);
                pollProgress(job.job_id);
            }
        });
    } catch (error) {
        UI.showError(error.message || 'Failed to start downloads');
    } finally {
        UI.setLoading('downloadSelectedBtn', false);
    }
}

async function pollProgress(jobId) {
    let attempts = 0;
    const interval = setInterval(async () => {
        if (attempts++ > 600) {
            clearInterval(interval);
            UI.markError(jobId, 'Timeout');
            return;
        }
        try {
            const progress = await APIClient.getProgress(jobId);
            if (progress.status === 'downloading') {
                UI.updateProgress(jobId, progress.progress);
            } else if (progress.status === 'completed') {
                UI.markComplete(jobId, progress.file_path);
                clearInterval(interval);
            } else if (progress.status === 'failed') {
                UI.markError(jobId, progress.error || 'Download failed');
                clearInterval(interval);
            }
        } catch (error) { console.error('Poll error:', error); }
    }, 1000);
}

function handleSelectAll() {
    state.selectAll();
    document.querySelectorAll('.video-card').forEach(card => {
        card.classList.add('selected');
        const checkbox = card.querySelector('.video-checkbox');
        if (checkbox) checkbox.checked = true;
    });
    UI.updateSelectedCount();
    UI.updateDownloadButton();
}

function handleDeselectAll() {
    state.deselectAll();
    document.querySelectorAll('.video-card').forEach(card => {
        card.classList.remove('selected');
        const checkbox = card.querySelector('.video-checkbox');
        if (checkbox) checkbox.checked = false;
    });
    UI.updateSelectedCount();
    UI.updateDownloadButton();
}

function handleLoadMore() { loadVideos(state.currentPage + 1); }

function initThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');
    if (!themeToggle) return;
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.body.setAttribute('data-theme', savedTheme);
    themeToggle.addEventListener('click', () => {
        const currentTheme = document.body.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.body.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const analyzeBtn = document.getElementById('analyzeBtn');
    const downloadBtn = document.getElementById('downloadSelectedBtn');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    const urlInput = document.getElementById('urlInput');
    if (analyzeBtn) analyzeBtn.addEventListener('click', handleAnalyze);
    if (downloadBtn) downloadBtn.addEventListener('click', handleDownload);
    if (selectAllBtn) selectAllBtn.addEventListener('click', handleSelectAll);
    if (deselectAllBtn) deselectAllBtn.addEventListener('click', handleDeselectAll);
    if (loadMoreBtn) loadMoreBtn.addEventListener('click', handleLoadMore);
    if (urlInput) {
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleAnalyze();
        });
    }
    initThemeToggle();
});
