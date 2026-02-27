document.addEventListener('DOMContentLoaded', () => {
    const downloadBtn = document.getElementById('action-button');
    const urlInput = document.getElementById('url-input');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');

    if (!downloadBtn) return;

    downloadBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        if (!url) return;

        let format = 'mp4';
        let quality = '1080p';

        // Use selected format card if available
        const selected = document.querySelector('.format-card.selected');
        if (selected) {
            quality = selected.querySelector('h4').textContent;
            format = selected.querySelector('p').textContent.split(' ')[0].toLowerCase();
        }

        startDownload(url, format, quality);
    });

    async function startDownload(url, format, quality) {
        // Show progress UI
        document.getElementById('format-panel').classList.add('hidden');
        downloadBtn.classList.add('hidden');
        progressContainer.classList.remove('hidden');

        // We simulate progress for streaming downloads since yt-dlp stdout pipe 
        // doesn't give us easy progress % without chunk parsing
        simulateProgress();

        try {
            // Trigger browser download via GET request since we stream attachment
            const targetUrl = `/api/download?url=${encodeURIComponent(url)}&format=${format}&quality=${quality}`;

            // Create a temporary link to trigger the stream download
            const a = document.createElement('a');
            a.href = targetUrl;
            a.download = ''; // Let server Content-Disposition handle filename
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            // Finish simulation quickly
            finishProgress();

            // Save to history
            saveToHistory({
                url: url,
                title: document.getElementById('meta-title').textContent,
                thumbnail: document.getElementById('meta-thumb').src,
                platform: document.getElementById('platform-badge').textContent.trim()
            });

        } catch (error) {
            progressText.textContent = 'Download Failed: ' + error.message;
            progressText.classList.add('text-danger');
            progressBar.style.background = 'var(--danger)';
        }
    }

    let progressInterval;
    function simulateProgress() {
        let p = 0;
        progressBar.style.width = '0%';
        progressBar.style.background = 'linear-gradient(90deg, var(--primary), var(--secondary))';
        progressText.textContent = 'Preparing Download...';
        progressText.classList.remove('text-danger');

        progressInterval = setInterval(() => {
            if (p < 90) {
                p += Math.random() * 10;
                progressBar.style.width = `${Math.min(90, p)}%`;
                progressText.textContent = `Downloading... ${Math.round(p)}%`;
            }
        }, 500);
    }

    function finishProgress() {
        clearInterval(progressInterval);
        progressBar.style.width = '100%';
        progressBar.style.background = 'var(--success)';
        progressText.textContent = 'Download Complete!';

        setTimeout(() => {
            progressContainer.classList.add('hidden');
            downloadBtn.classList.remove('hidden');
            document.getElementById('format-panel').classList.remove('hidden');
        }, 3000);
    }

    function saveToHistory(item) {
        let history = JSON.parse(localStorage.getItem('dl_history') || '[]');
        item.date = new Date().toISOString();
        history.unshift(item);
        if (history.length > 20) history = history.slice(0, 20);
        localStorage.setItem('dl_history', JSON.stringify(history));

        // Trigger generic event so history.js can pick it up
        document.dispatchEvent(new Event('historyUpdated'));
    }
});
