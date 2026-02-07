// ==========================================
// CONFIGURATION
// ==========================================
const CONFIG = {
    API_BASE_URL: 'https://tiktok-downloader-production-a1f0.up.railway.app/api/v1',
    WS_URL: 'wss://tiktok-downloader-production-a1f0.up.railway.app/ws',
    MAX_VIDEOS_PER_PAGE: 20,
    RECONNECT_INTERVAL: 3000,
    REQUEST_TIMEOUT: 60000
};

// ==========================================
// STATE
// ==========================================
class AppState {
    constructor() {
        this.sessionId = null;
        this.videos = [];
        this.selectedVideos = new Set();
        this.currentPage = 1;
        this.totalVideos = 0;
        this.isLoading = false;
        this.downloadJobs = new Map();
    }

    reset() {
        this.sessionId = null;
        this.videos = [];
        this.selectedVideos.clear();
        this.currentPage = 1;
        this.totalVideos = 0;
        this.isLoading = false;
    }

    addVideos(videos) {
        this.videos.push(...videos);
    }

    toggleVideo(videoId) {
        if (this.selectedVideos.has(videoId)) {
            this.selectedVideos.delete(videoId);
        } else {
            this.selectedVideos.add(videoId);
        }
    }

    selectAll() {
        this.videos.forEach(video => this.selectedVideos.add(video.id));
    }

    deselectAll() {
        this.selectedVideos.clear();
    }

    getSelectedVideos() {
        return this.videos.filter(v => this.selectedVideos.has(v.id));
    }
}

const state = new AppState();

// ==========================================
// API CLIENT
// ==========================================
class APIClient {
    static async request(endpoint, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT);

        try {
            console.log(`API Request: ${endpoint}`);
            
            const response = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
                ...options,
                signal: controller.signal,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            clearTimeout(timeout);

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || `HTTP ${response.status}`);
            }

            console.log(`API Response:`, data);
            return data;
            
        } catch (error) {
            clearTimeout(timeout);
            console.error(`API Error:`, error);
            
            if (error.name === 'AbortError') {
                throw new Error('Request timeout - please try again');
            }
            throw error;
        }
    }

    static async analyzeURL(url) {
        return this.request('/analyze', {
            method: 'POST',
            body: JSON.stringify({ url })
        });
    }

    static async getVideos(sessionId, page = 1, limit = CONFIG.MAX_VIDEOS_PER_PAGE) {
        return this.request(`/videos/${sessionId}?page=${page}&limit=${limit}`);
    }

    static async downloadVideos(sessionId, videoIds, format = 'best', quality = null) {
        return this.request('/download', {
            method: 'POST',
            body: JSON.stringify({
                session_id: sessionId,
                video_ids: videoIds,
                format,
                quality
            })
        });
    }

    static async getProgress(jobId) {
        return this.request(`/progress/${jobId}`);
    }

    static async health() {
        return this.request('/health');
    }
}

// ==========================================
// WEBSOCKET MANAGER
// ==========================================
class WebSocketManager {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    connect(sessionId) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            return;
        }

        try {
            console.log(`Connecting WebSocket for session: ${sessionId}`);
            this.ws = new WebSocket(`${CONFIG.WS_URL}/${sessionId}`);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.reconnectAttempts = 0;
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('WebSocket message:', data);
                this.handleMessage(data);
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.attemptReconnect(sessionId);
            };
        } catch (error) {
            console.error('WebSocket connection error:', error);
        }
    }

    attemptReconnect(sessionId) {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
                console.log(`Reconnecting... Attempt ${this.reconnectAttempts}`);
                this.connect(sessionId);
            }, CONFIG.RECONNECT_INTERVAL);
        }
    }

    handleMessage(data) {
        if (data.type === 'progress') {
            UI.updateProgress(data.job_id, data.progress);
        } else if (data.type === 'complete') {
            UI.markComplete(data.job_id, data.file_path);
        } else if (data.type === 'error') {
            UI.markError(data.job_id, data.error);
        }
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

const wsManager = new WebSocketManager();

// ==========================================
// UI CONTROLLER
// ==========================================
class UI {
    static showError(message) {
        const errorEl = document.getElementById('urlError');
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.style.display = 'block';
            setTimeout(() => {
                errorEl.style.display = 'none';
            }, 5000);
        }
    }

    static setLoading(elementId, isLoading) {
        const btn = document.getElementById(elementId);
        if (!btn) return;
        
        const textEl = btn.querySelector('.btn-text');
        const loaderEl = btn.querySelector('.btn-loader');
        
        if (isLoading) {
            btn.disabled = true;
            if (textEl) textEl.style.display = 'none';
            if (loaderEl) loaderEl.style.display = 'flex';
        } else {
            btn.disabled = false;
            if (textEl) textEl.style.display = 'inline';
            if (loaderEl) loaderEl.style.display = 'none';
        }
    }

    static showVideoList() {
        const section = document.getElementById('videoListSection');
        if (section) {
            section.style.display = 'block';
            section.scrollIntoView({ behavior: 'smooth' });
        }
    }

    static hideVideoList() {
        const section = document.getElementById('videoListSection');
        if (section) {
            section.style.display = 'none';
        }
    }

    static updatePlaylistHeader(title, count) {
        const headerEl = document.getElementById('playlistHeader');
        const titleEl = document.getElementById('playlistTitle');
        const infoEl = document.getElementById('playlistInfo');
        
        if (titleEl) titleEl.textContent = title;
        if (infoEl) infoEl.textContent = `${count} video${count !== 1 ? 's' : ''}`;
        if (headerEl) headerEl.style.display = 'block';
    }

    static renderVideos(videos) {
        const grid = document.getElementById('videoGrid');
        if (!grid) return;
        
        videos.forEach(video => {
            const card = this.createVideoCard(video);
            grid.appendChild(card);
        });
    }

    static createVideoCard(video) {
        const card = document.createElement('div');
        card.className = 'video-card';
        card.dataset.videoId = video.id;

        const isSelected = state.selectedVideos.has(video.id);
        if (isSelected) {
            card.classList.add('selected');
        }

        const thumbnail = video.thumbnail || 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="320" height="180"%3E%3Crect fill="%23ddd" width="320" height="180"/%3E%3C/svg%3E';

        card.innerHTML = `
            <div class="video-thumbnail-container">
                <img src="${thumbnail}" alt="${this.escapeHtml(video.title)}" class="video-thumbnail" loading="lazy" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22320%22 height=%22180%22%3E%3Crect fill=%22%23ddd%22 width=%22320%22 height=%22180%22/%3E%3C/svg%3E'">
                <input type="checkbox" class="video-checkbox" ${isSelected ? 'checked' : ''} data-video-id="${video.id}">
                <div class="video-duration">${this.formatDuration(video.duration)}</div>
            </div>
            <div class="video-info">
                <h3 class="video-title">${this.escapeHtml(video.title)}</h3>
                <div class="video-meta">
                    <span class="video-platform">${video.platform}</span>
                    ${video.views ? `<span>•</span><span>${this.formatViews(video.views)} views</span>` : ''}
                </div>
            </div>
        `;

        const checkbox = card.querySelector('.video-checkbox');
        checkbox.addEventListener('change', (e) => {
            e.stopPropagation();
            this.handleVideoToggle(video.id);
        });

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
        if (countEl) {
            const count = state.selectedVideos.size;
            countEl.textContent = `${count} selected`;
        }
    }

    static updateDownloadButton() {
        const btn = document.getElementById('downloadSelectedBtn');
        if (btn) {
            btn.disabled = state.selectedVideos.size === 0;
        }
    }

    static clearVideoGrid() {
        const grid = document.getElementById('videoGrid');
        if (grid) {
            grid.innerHTML = '';
        }
    }

    static showLoadMore(hasMore) {
        const container = document.getElementById('loadMoreContainer');
        if (container) {
            container.style.display = hasMore ? 'block' : 'none';
        }
    }

    static showProgressSection() {
        const section = document.getElementById('progressSection');
        if (section) {
            section.style.display = 'block';
        }
    }

    static addProgressItem(jobId, videoTitle) {
        const list = document.getElementById('progressList');
        if (!list) return;
        
        const item = document.createElement('div');
        item.className = 'progress-item';
        item.dataset.jobId = jobId;
        item.innerHTML = `
            <div class="progress-item-header">
                <div class="progress-item-title">${this.escapeHtml(videoTitle)}</div>
                <div class="progress-status queued">Queued</div>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar" style="width: 0%"></div>
            </div>
        `;
        
        list.prepend(item);
    }

    static updateProgress(jobId, progress) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;

        const statusEl = item.querySelector('.progress-status');
        const barEl = item.querySelector('.progress-bar');
        
        if (statusEl) {
            statusEl.className = 'progress-status downloading';
            statusEl.textContent = `${progress}%`;
        }
        if (barEl) {
            barEl.style.width = `${progress}%`;
        }
    }

    static markComplete(jobId, filePath) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;

        const statusEl = item.querySelector('.progress-status');
        const barEl = item.querySelector('.progress-bar');
        
        if (statusEl) {
            statusEl.className = 'progress-status completed';
            statusEl.textContent = 'Completed';
        }
        if (barEl) {
            barEl.style.width = '100%';
        }

        if (filePath) {
            const header = item.querySelector('.progress-item-header');
            const downloadLink = document.createElement('a');
            downloadLink.href = `https://tiktok-downloader-production-a1f0.up.railway.app${filePath}`;
            downloadLink.download = '';
            downloadLink.textContent = '⬇ Download';
            downloadLink.className = 'btn-control';
            downloadLink.target = '_blank';
            downloadLink.style.marginLeft = '10px';
            header.appendChild(downloadLink);
        }
    }

    static markError(jobId, error) {
        const item = document.querySelector(`[data-job-id="${jobId}"]`);
        if (!item) return;

        const statusEl = item.querySelector('.progress-status');
        if (statusEl) {
            statusEl.className = 'progress-status failed';
            statusEl.textContent = 'Failed';
        }
        
        const errorMsg = document.createElement('p');
        errorMsg.textContent = error;
        errorMsg.style.color = '#ff4444';
        errorMsg.style.fontSize = '0.875rem';
        errorMsg.style.marginTop = '10px';
        item.appendChild(errorMsg);
    }

    static formatDuration(seconds) {
        if (!seconds) return '0:00';
        
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }

    static formatViews(views) {
        if (!views) return '';
        if (views >= 1000000) {
            return `${(views / 1000000).toFixed(1)}M`;
        }
        if (views >= 1000) {
            return `${(views / 1000).toFixed(1)}K`;
        }
        return views.toString();
    }

    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
}

// ==========================================
// APP LOGIC
// ==========================================
async function handleAnalyze() {
    const urlInput = document.getElementById('urlInput');
    if (!urlInput) return;
    
    const url = urlInput.value.trim();
    
    if (!url) {
        UI.showError('Please enter a valid URL');
        return;
    }

    try {
        new URL(url);
    } catch {
        UI.showError('Invalid URL format');
        return;
    }

    UI.setLoading('analyzeBtn', true);
    state.reset();
    UI.clearVideoGrid();
    UI.hideVideoList();

    try {
        const response = await APIClient.analyzeURL(url);
        
        state.sessionId = response.session_id;
        state.totalVideos = response.total_videos;

        if (response.is_playlist) {
            UI.updatePlaylistHeader(response.playlist_title, response.total_videos);
        }

        await loadVideos(1);
        
        UI.showVideoList();
        wsManager.connect(state.sessionId);

    } catch (error) {
        UI.showError(error.message || 'Failed to analyze URL. Please try again.');
        console.error('Analyze error:', error);
    } finally {
        UI.setLoading('analyzeBtn', false);
    }
}

async function loadVideos(page) {
    if (state.isLoading) return;
    
    state.isLoading = true;

    try {
        const response = await APIClient.getVideos(state.sessionId, page);
        
        state.addVideos(response.videos);
        UI.renderVideos(response.videos);
        
        UI.showLoadMore(response.has_more);
        
        if (response.has_more) {
            state.currentPage = page;
        }

    } catch (error) {
        UI.showError('Failed to load videos');
        console.error('Load videos error:', error);
    } finally {
        state.isLoading = false;
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
        const response = await APIClient.downloadVideos(
            state.sessionId,
            videoIds,
            actualFormat,
            quality
        );

        UI.showProgressSection();

        response.jobs.forEach(job => {
            const video = selectedVideos.find(v => v.id === job.video_id);
            if (video) {
                UI.addProgressItem(job.job_id, video.title);
                state.downloadJobs.set(job.job_id, video);
            }
        });

        response.jobs.forEach(job => {
            pollProgress(job.job_id);
        });

    } catch (error) {
        UI.showError(error.message || 'Failed to start download');
        console.error('Download error:', error);
    } finally {
        UI.setLoading('downloadSelectedBtn', false);
    }
}

async function pollProgress(jobId) {
    let attempts = 0;
    const maxAttempts = 600;

    const interval = setInterval(async () => {
        attempts++;
        
        if (attempts > maxAttempts) {
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
        } catch (error) {
            console.error('Poll progress error:', error);
        }
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

function handleLoadMore() {
    loadVideos(state.currentPage + 1);
}

function handleClearCompleted() {
    document.querySelectorAll('.progress-status.completed').forEach(status => {
        const item = status.closest('.progress-item');
        if (item) item.remove();
    });
}

// ==========================================
// EVENT LISTENERS
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    const analyzeBtn = document.getElementById('analyzeBtn');
    const downloadBtn = document.getElementById('downloadSelectedBtn');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    const clearBtn = document.getElementById('clearCompletedBtn');
    const urlInput = document.getElementById('urlInput');
    
    if (analyzeBtn) analyzeBtn.addEventListener('click', handleAnalyze);
    if (downloadBtn) downloadBtn.addEventListener('click', handleDownload);
    if (selectAllBtn) selectAllBtn.addEventListener('click', handleSelectAll);
    if (deselectAllBtn) deselectAllBtn.addEventListener('click', handleDeselectAll);
    if (loadMoreBtn) loadMoreBtn.addEventListener('click', handleLoadMore);
    if (clearBtn) clearBtn.addEventListener('click', handleClearCompleted);
    
    if (urlInput) {
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                handleAnalyze();
            }
        });
    }

    // Health check
    APIClient.health().then(() => {
        console.log('✅ API connection established');
    }).catch((error) => {
        console.error('❌ API connection failed:', error);
        UI.showError('Cannot connect to server. Please try again later.');
    });
});

window.addEventListener('beforeunload', () => {
    wsManager.disconnect();
});
