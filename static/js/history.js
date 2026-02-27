document.addEventListener('DOMContentLoaded', () => {
    const historyStrip = document.getElementById('history-strip');
    const historyContainer = document.getElementById('history-container');

    if (!historyStrip || !historyContainer) return;

    function renderHistory() {
        const history = JSON.parse(localStorage.getItem('dl_history') || '[]');

        if (history.length === 0) {
            historyStrip.classList.add('hidden');
            return;
        }

        historyStrip.classList.remove('hidden');
        historyContainer.innerHTML = '';

        history.forEach(item => {
            const card = document.createElement('div');
            card.className = 'history-card';
            card.style.cssText = `
                min-width: 150px;
                background: var(--bg-card);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 0.5rem;
                cursor: pointer;
            `;

            card.innerHTML = `
                <img src="${item.thumbnail}" alt="Thumb" style="width: 100%; height: 80px; object-fit: cover; border-radius: 4px;">
                <p style="font-size: 0.8rem; margin-top: 0.5rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${item.title}</p>
                <small style="color: var(--text-muted); font-size: 0.7rem;">${item.platform}</small>
            `;

            card.addEventListener('click', () => {
                const urlInput = document.getElementById('url-input');
                if (urlInput) {
                    urlInput.value = item.url;
                    // Trigger input event to start fetch
                    urlInput.dispatchEvent(new Event('input'));
                }
            });

            historyContainer.appendChild(card);
        });
    }

    renderHistory();
    document.addEventListener('historyUpdated', renderHistory);
});
