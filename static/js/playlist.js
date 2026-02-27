document.addEventListener('DOMContentLoaded', () => {
    const fetchBtn = document.getElementById('fetch-playlist-btn');
    const input = document.getElementById('playlist-input');
    const status = document.getElementById('playlist-status');
    const card = document.getElementById('playlist-card');
    const queue = document.getElementById('pl-queue');
    const downloadBtn = document.getElementById('pl-download-selected');

    if (!fetchBtn) return;

    let playlistData = null;
    let selectedItems = new Set();

    fetchBtn.addEventListener('click', async () => {
        const url = input.value.trim();
        if (!url) return;

        status.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Fetching playlist...';
        status.classList.remove('hidden');
        status.className = '';
        card.classList.add('hidden');

        try {
            const res = await fetch('/api/playlist/fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            if (!res.ok) throw new Error('Playlist fetch failed');

            playlistData = await res.json();

            status.classList.add('hidden');
            document.getElementById('pl-title').textContent = playlistData.title;
            document.getElementById('pl-uploader').textContent = playlistData.uploader;
            document.getElementById('pl-count').textContent = playlistData.total_videos;

            renderQueue(playlistData.entries);
            card.classList.remove('hidden');

        } catch (e) {
            status.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${e.message}`;
            status.classList.add('text-danger');
        }
    });

    function renderQueue(entries) {
        queue.innerHTML = '';
        selectedItems.clear();
        updateDownloadBtn();

        entries.forEach((video, index) => {
            if (!video.id) return;

            const div = document.createElement('div');
            div.className = 'queue-item';
            div.style.cssText = `
                display: flex; gap: 1rem; align-items: center; padding: 0.5rem; 
                background: var(--bg-input); border-radius: 8px; border: 1px solid transparent;
                transition: border-color 0.2s; cursor: pointer;
            `;

            // Checkbox
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.style.width = '18px'; cb.style.height = '18px';
            cb.addEventListener('change', (e) => {
                if (e.target.checked) {
                    selectedItems.add(index);
                    div.style.borderColor = 'var(--primary)';
                } else {
                    selectedItems.delete(index);
                    div.style.borderColor = 'transparent';
                }
                updateDownloadBtn();
            });

            // Thumbnail
            const img = document.createElement('img');
            img.src = video.thumbnail || '/static/images/placeholder.jpg';
            img.style.cssText = 'width: 80px; height: 45px; object-fit: cover; border-radius: 4px;';

            // Text
            const textContent = document.createElement('div');
            textContent.style.flex = 1;
            textContent.innerHTML = `
                <div style="font-weight: 500; font-size: 0.95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${video.title || 'Unknown Video'}</div>
                <div style="font-size: 0.8rem; color: var(--text-muted);">${video.duration ? Math.floor(video.duration / 60) + ':' + String(Math.floor(video.duration % 60)).padStart(2, '0') : ''}</div>
            `;

            // Status Badge
            const badge = document.createElement('div');
            badge.id = `badge-${index}`;
            badge.className = 'status-badge';
            badge.style.cssText = 'padding: 0.2rem 0.5rem; border-radius: 99px; font-size: 0.75rem; background: var(--bg-card);';
            badge.textContent = 'Queued';

            div.appendChild(cb);
            div.appendChild(img);
            div.appendChild(textContent);
            div.appendChild(badge);

            // Toggle selection on click anywhere in row
            div.addEventListener('click', (e) => {
                if (e.target !== cb) {
                    cb.checked = !cb.checked;
                    cb.dispatchEvent(new Event('change'));
                }
            });

            queue.appendChild(div);
        });
    }

    function updateDownloadBtn() {
        downloadBtn.disabled = selectedItems.size === 0;
        downloadBtn.innerHTML = `<i class="fa-solid fa-download"></i> Download Selected (${selectedItems.size})`;
    }

    document.getElementById('pl-select-all').addEventListener('click', () => {
        queue.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            if (!cb.checked) { cb.checked = true; cb.dispatchEvent(new Event('change')); }
        });
    });

    document.getElementById('pl-deselect-all').addEventListener('click', () => {
        queue.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            if (cb.checked) { cb.checked = false; cb.dispatchEvent(new Event('change')); }
        });
    });

    // Simplistic sequential download processor (no zip implementation in free tier JS for simplicity)
    downloadBtn.addEventListener('click', async () => {
        const formatSelect = document.getElementById('pl-format').value.split(',');
        const format = formatSelect[0];
        const quality = formatSelect[1];

        const selectionArr = Array.from(selectedItems).sort((a, b) => a - b);

        for (let idx of selectionArr) {
            const entry = playlistData.entries[idx];
            const badge = document.getElementById(`badge-${idx}`);
            badge.style.background = 'var(--warning)';
            badge.style.color = '#fff';
            badge.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Downloading...';

            try {
                // Determine base URL depending on platform
                // Because yt-dlp flat playlist usually returns fragments or full URLs depending on platform
                let fullUrl = entry.url || `https://youtube.com/watch?v=${entry.id}`;
                if (input.value.includes('vimeo')) fullUrl = `https://vimeo.com/${entry.id}`;

                // Directly trigger download endpoint inside an iframe/a-tag to save
                const a = document.createElement('a');
                a.href = `/api/download?url=${encodeURIComponent(fullUrl)}&format=${format}&quality=${quality}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);

                // Wait a few seconds between triggering downloads to not spam
                await new Promise(r => setTimeout(r, 4000));

                badge.style.background = 'var(--success)';
                badge.innerHTML = '<i class="fa-solid fa-check"></i> Done';
            } catch (e) {
                badge.style.background = 'var(--danger)';
                badge.innerHTML = '<i class="fa-solid fa-xmark"></i> Failed';
            }
        }
    });
});
