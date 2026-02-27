document.addEventListener('DOMContentLoaded', () => {
    // Theme setup
    const themeToggle = document.getElementById('theme-toggle');
    const root = document.documentElement;
    const isDark = localStorage.getItem('theme') !== 'light';

    if (!isDark) {
        root.setAttribute('data-theme', 'light');
        themeToggle.innerHTML = '<i class="fa-solid fa-moon"></i>';
    }

    themeToggle.addEventListener('click', () => {
        const currentTheme = root.getAttribute('data-theme');
        if (currentTheme === 'light') {
            root.removeAttribute('data-theme');
            localStorage.setItem('theme', 'dark');
            themeToggle.innerHTML = '<i class="fa-solid fa-sun"></i>';
        } else {
            root.setAttribute('data-theme', 'light');
            localStorage.setItem('theme', 'light');
            themeToggle.innerHTML = '<i class="fa-solid fa-moon"></i>';
        }
    });

    // Homepage logic
    const urlInput = document.getElementById('url-input');
    if (!urlInput) return;

    // Placeholder cycling
    const placeholders = [
        'Paste YouTube link...',
        'Paste TikTok link...',
        'Paste Instagram Reel...',
        'Paste Twitter video...',
        'Paste Facebook video...'
    ];
    let placeholderIndex = 0;
    setInterval(() => {
        if (document.activeElement !== urlInput && !urlInput.value) {
            placeholderIndex = (placeholderIndex + 1) % placeholders.length;
            urlInput.placeholder = placeholders[placeholderIndex];
        }
    }, 3000);

    // Auto-detect URL
    let typingTimer;
    urlInput.addEventListener('input', () => {
        clearTimeout(typingTimer);
        const url = urlInput.value.trim();

        if (url.length > 5 && url.includes('.')) {
            typingTimer = setTimeout(() => {
                detectAndFetchMetadata(url);
            }, 500);
        }
    });

    async function detectAndFetchMetadata(url) {
        const badgeContainer = document.getElementById('platform-badge');
        const aiCard = document.getElementById('ai-card');
        const formatGrid = document.getElementById('format-grid');

        // Show loading state
        badgeContainer.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Resolving link...';
        badgeContainer.classList.remove('hidden');

        try {
            // Fetch metadata
            const response = await fetch('/api/metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to analyze URL');
            }

            const data = await response.json();

            // Update UI
            badgeContainer.innerHTML = `<i class="fa-brands fa-${data.platform.toLowerCase()}"></i> ${data.platform} Detected`;

            // Render AI Card
            document.getElementById('meta-thumb').src = data.thumbnail || '/static/images/placeholder.jpg';
            document.getElementById('meta-title').textContent = data.title || 'Unknown Title';
            document.getElementById('meta-uploader').textContent = data.uploader || 'Unknown';
            document.getElementById('ai-summary-text').textContent = data.aiSummary || 'AI Summary unavailable.';

            aiCard.classList.remove('hidden');

            // Render Formats
            renderFormats(data.formats, data.recommendation);
            document.getElementById('format-panel').classList.remove('hidden');
            document.getElementById('action-button').classList.remove('hidden');

            // Scroll to card
            aiCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        } catch (error) {
            badgeContainer.innerHTML = `<i class="fa-solid fa-circle-exclamation text-danger"></i> ${error.message}`;
            badgeContainer.className = 'text-danger';
            aiCard.classList.add('hidden');
            document.getElementById('format-panel').classList.add('hidden');
            document.getElementById('action-button').classList.add('hidden');
        }
    }

    function renderFormats(formats, recommendation) {
        const grid = document.getElementById('format-grid');
        grid.innerHTML = '';

        if (!formats || formats.length === 0) {
            grid.innerHTML = '<p class="text-muted">No formats directly available. Best available will be downloaded.</p>';
            return;
        }

        // Add standard recommended ones if raw formats is too messy
        const recommendedRes = recommendation ? recommendation.quality : '1080p';

        formats.forEach(f => {
            const isRecommended = f.resolution === recommendedRes || f.resolution.includes(recommendedRes.replace('p', ''));
            const card = document.createElement('div');
            card.className = `format-card ${isRecommended ? 'recommended selected' : ''}`;
            card.innerHTML = `
                <h4>${f.resolution}</h4>
                <p>${f.ext.toUpperCase()} • ${f.size}</p>
            `;

            if (isRecommended) {
                window.selectedFormat = f;
            }

            card.addEventListener('click', () => {
                document.querySelectorAll('.format-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                window.selectedFormat = f;
            });

            grid.appendChild(card);
        });

        // Ensure at least one is selected
        if (!window.selectedFormat && formats.length > 0) {
            window.selectedFormat = formats[0];
            grid.firstChild.classList.add('selected');
        }
    }
});
