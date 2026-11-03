/**
 * ConnectHub Theme Controller (Top Header Only)
 * Manages theme state, persistence in localStorage, and the single top header toggle button.
 */
(function() {
    const THEME_STORAGE_KEY = 'connecthub_theme';

    function getPreferredTheme() {
        const stored = localStorage.getItem(THEME_STORAGE_KEY) || localStorage.getItem('theme');
        if (stored === 'dark' || stored === 'light') {
            return stored;
        }
        return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.setAttribute('data-bs-theme', theme);
        try {
            localStorage.setItem(THEME_STORAGE_KEY, theme);
            localStorage.setItem('theme', theme);
        } catch (e) {
            console.warn('Could not persist theme to localStorage:', e);
        }
        updateThemeUI(theme);
    }

    function updateThemeUI(theme) {
        const isDark = (theme === 'dark');

        const iconDark = document.querySelector('.theme-icon-dark');
        const iconLight = document.querySelector('.theme-icon-light');
        if (iconDark && iconLight) {
            if (isDark) {
                iconDark.classList.add('d-none');
                iconLight.classList.remove('d-none');
            } else {
                iconDark.classList.remove('d-none');
                iconLight.classList.add('d-none');
            }
        }

        const topbarBtn = document.getElementById('themeToggleBtn');
        if (topbarBtn) {
            topbarBtn.setAttribute('title', isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme');
        }

        window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: theme } }));
    }

    window.toggleConnectHubTheme = function() {
        const current = document.documentElement.getAttribute('data-theme') || getPreferredTheme();
        const next = (current === 'dark') ? 'light' : 'dark';
        applyTheme(next);
    };

    window.setConnectHubTheme = function(theme) {
        if (theme === 'dark' || theme === 'light') {
            applyTheme(theme);
        }
    };

    function initUI() {
        const activeTheme = document.documentElement.getAttribute('data-theme') || getPreferredTheme();
        updateThemeUI(activeTheme);

        const topbarToggle = document.getElementById('themeToggleBtn');
        if (topbarToggle && !topbarToggle.hasAttribute('data-bound')) {
            topbarToggle.setAttribute('data-bound', 'true');
            topbarToggle.addEventListener('click', window.toggleConnectHubTheme);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initUI);
    } else {
        initUI();
    }
})();
