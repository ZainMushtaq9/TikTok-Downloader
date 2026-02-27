document.addEventListener('DOMContentLoaded', () => {
    const fetchBtn = document.getElementById('fetch-profile-btn');
    const input = document.getElementById('profile-input');
    const status = document.getElementById('profile-status');
    const header = document.getElementById('profile-header');
    const controls = document.getElementById('profile-controls');
    const grid = document.getElementById('profile-grid');
    const stickyBar = document.getElementById('sticky-bar');

    if (!fetchBtn) return;

    let profileData = null;
    let selectedSet = new Set();

    // We reuse the playlist fetch endpoint since flat-playlist works for profiles too in yt-dlp
    fetchBtn.addEventListener('click', async () => {
        let url = input.value.trim();
        if (!url) return;

        // Very basic normalization if user typed @username
        if (url.startsWith('@')) {
            // Assume tiktok by default if just @username is typed
            url = `https://www.tiktok.com/${url}`;
            input.value = url;
        }

        status.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Analyzing profile...';
        status.classList.remove('hidden');
        status.className = '';

        header.classList.add('hidden');
        controls.classList.add('hidden');
        grid.classList.add('hidden');
        grid.innerHTML = '';

        try {
            const res = await fetch('/api/playlist/fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            if (!res.ok) throw new Error('Profile fetch failed or profile is private.');

            profileData = await res.json();

            status.classList.add('hidden');

            // Populate header
            document.getElementById('prof-name').innerHTML = `${profileData.uploader || 'Creator'} <i class="fa-solid fa-circle-check text-primary" style="font-size: 1rem;"></i>`;
            document.getElementById('prof-platform').textContent = new URL(url).hostname.replace('www.', '');
            document.getElementById('prof-count').textContent = profileData.total_videos || 0;

            // Use first video banner as avatar fallback if non provided from yt-dlp
            const firstThumb = profileData.entries[0] ? profileData.entries[0].thumbnail : '/static/images/placeholder.jpg';
            document.getElementById('prof-avatar').src = firstThumb;

            renderGrid(profileData.entries);

            header.classList.remove('hidden');
            controls.classList.remove('hidden');
            grid.classList.remove('hidden');

        } catch (e) {
            status.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${e.message}`;
            status.classList.add('text-danger');
        }
    });

    function renderGrid(entries) {
        selectedSet.clear();
        updateStickyBar();

        // Sort entries by most recent or whatever ordering yt-dlp gave
        entries.slice(0, 100).forEach((video, index) => { // Limit to 100 for safety in free tier
            if (!video.id) return;

            const card = document.createElement('div');
            card.style.cssText = `
                position: relative;
                aspect-ratio: 9/16;
                border-radius: 12px;
                overflow: hidden;
                cursor: pointer;
                background: var(--bg-card);
                border: 2px solid transparent;
                transition: transform 0.2s, border-color 0.2s;
            `;

            const thumb = video.thumbnail || '/static/images/placeholder.jpg';

            card.innerHTML = `
                <img src="${thumb}" style="width: 100%; height: 100%; object-fit: cover; opacity: 0.8;">
                <div style="position: absolute; bottom: 0; left: 0; right: 0; padding: 2rem 1rem 0.5rem; background: linear-gradient(transparent, rgba(0,0,0,0.9)); color: white;">
                    <div style="font-weight: 500; font-size: 0.85rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${video.title || 'Video'}</div>
                    <div style="font-size: 0.75rem; color: #aaa; margin-top: 0.25rem;">
                        <i class="fa-regular fa-clock"></i> ${video.duration ? Math.floor(video.duration / 60) + ':' + String(Math.floor(video.duration % 60)).padStart(2, '0') : ''}
                    </div>
                </div>
                <div class="check-overlay" style="position: absolute; top: 0.5rem; right: 0.5rem; width: 24px; height: 24px; border-radius: 50%; background: rgba(0,0,0,0.5); border: 2px solid white; display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s, background 0.2s, border-color 0.2s;">
                    <i class="fa-solid fa-check" style="color: transparent; font-size: 0.75rem;"></i>
                </div>
                <div id="prof-badge-${index}" style="position: absolute; top: 0.5rem; left: 0.5rem; padding: 0.2rem 0.5rem; background: rgba(0,0,0,0.6); color: white; border-radius: 4px; font-size: 0.7rem; display: none;"></div>
            `;

            card.addEventListener('click', () => {
                const overlay = card.querySelector('.check-overlay');
                const icon = overlay.querySelector('i');

                if (selectedSet.has(index)) {
                    selectedSet.delete(index);
                    card.style.borderColor = 'transparent';
                    card.style.transform = 'scale(1)';
                    overlay.style.opacity = '0';
                    overlay.style.background = 'rgba(0,0,0,0.5)';
                    overlay.style.borderColor = 'white';
                    icon.style.color = 'transparent';
                } else {
                    selectedSet.add(index);
                    card.style.borderColor = 'var(--primary)';
                    card.style.transform = 'scale(0.98)';
                    overlay.style.opacity = '1';
                    overlay.style.background = 'var(--primary)';
                    overlay.style.borderColor = 'var(--primary)';
                    icon.style.color = 'white';
                }
                updateStickyBar();
            });

            // Hover effect
            card.addEventListener('mouseenter', () => {
                if (!selectedSet.has(index)) card.querySelector('.check-overlay').style.opacity = '1';
            });
            card.addEventListener('mouseleave', () => {
                if (!selectedSet.has(index)) card.querySelector('.check-overlay').style.opacity = '0';
            });

            grid.appendChild(card);
        });
    }

    function updateStickyBar() {
        document.getElementById('sticky-count').textContent = selectedSet.size;

        if (selectedSet.size > 0) {
            stickyBar.classList.remove('hidden');
            // Slight delay for reflow
            setTimeout(() => {
                stickyBar.style.transform = 'translateY(0)';
            }, 10);
        } else {
            stickyBar.style.transform = 'translateY(100%)';
            setTimeout(() => {
                stickyBar.classList.add('hidden');
            }, 300);
        }
    }

    document.getElementById('sticky-close').addEventListener('click', () => {
        document.getElementById('prof-deselect-all').click();
    });

    document.getElementById('prof-select-all').addEventListener('click', () => {
        Array.from(grid.children).forEach((card, idx) => {
            if (!selectedSet.has(idx)) card.click();
        });
    });

    document.getElementById('prof-deselect-all').addEventListener('click', () => {
        Array.from(grid.children).forEach((card, idx) => {
            if (selectedSet.has(idx)) card.click();
        });
    });

    // Download logic triggered from sticky bar
    document.getElementById('prof-download-btn').addEventListener('click', async () => {
        const formatSelect = document.getElementById('prof-format').value.split(',');
        const format = formatSelect[0];
        const quality = formatSelect[1];

        const selectionArr = Array.from(selectedSet).sort((a, b) => a - b);
        document.getElementById('sticky-count').textContent = `Downloading ${selectionArr.length}...`;
        document.getElementById('prof-download-btn').disabled = true;

        for (let idx of selectionArr) {
            const entry = profileData.entries[idx];
            const badge = document.getElementById(`prof-badge-${idx}`);
            badge.style.display = 'block';
            badge.style.background = 'var(--warning)';
            badge.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

            try {
                // Determine base URL depending on platform
                let fullUrl = entry.url || `https://tiktok.com/@${profileData.uploader}/video/${entry.id}`;
                if (input.value.includes('instagram')) fullUrl = `https://instagram.com/p/${entry.id}`;
                if (input.value.includes('youtube')) fullUrl = `https://youtube.com/watch?v=${entry.id}`;

                const a = document.createElement('a');
                a.href = `/api/download?url=${encodeURIComponent(fullUrl)}&format=${format}&quality=${quality}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);

                await new Promise(r => setTimeout(r, 4000));

                badge.style.background = 'var(--success)';
                badge.innerHTML = '<i class="fa-solid fa-check"></i>';
            } catch (e) {
                badge.style.background = 'var(--danger)';
                badge.innerHTML = '<i class="fa-solid fa-xmark"></i>';
            }
        }

        setTimeout(() => {
            document.getElementById('prof-deselect-all').click();
            document.getElementById('prof-download-btn').disabled = false;
            document.getElementById('prof-download-btn').textContent = 'Download Items';
        }, 3000);
    });
});
