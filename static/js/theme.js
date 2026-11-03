/**
 * ConnectHub Dark/Light Theme Controller
 * Manages theme state, persistence in localStorage, DOM synchronization, and UI toggles.
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

        // Topbar toggle icons
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

        // Topbar button title
        const topbarBtn = document.getElementById('themeToggleBtn');
        if (topbarBtn) {
            topbarBtn.setAttribute('title', isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme');
        }

        // Dropdown label
        const dropdownLabel = document.getElementById('dropdownThemeLabel');
        if (dropdownLabel) {
            dropdownLabel.textContent = isDark ? 'Dark Mode' : 'Light Mode';
        }

        // Sidebar toggle icon
        const sidebarIcon = document.querySelector('.theme-icon-sidebar');
        if (sidebarIcon) {
            sidebarIcon.className = isDark ? 'bi bi-sun-fill fs-6 text-warning theme-icon-sidebar' : 'bi bi-moon-stars fs-6 theme-icon-sidebar';
        }

        // Dashboard banner button
        const bannerIcon = document.getElementById('bannerThemeIcon');
        const bannerText = document.getElementById('bannerThemeText');
        if (bannerIcon && bannerText) {
            bannerIcon.className = isDark ? 'bi bi-sun-fill text-warning' : 'bi bi-moon-stars-fill';
            bannerText.textContent = isDark ? 'Light' : 'Dark';
        }

        // Dispatch custom event for any listening components
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

    // Sync UI elements as soon as DOM is ready
    function initUI() {
        const activeTheme = document.documentElement.getAttribute('data-theme') || getPreferredTheme();
        updateThemeUI(activeTheme);

        const topbarToggle = document.getElementById('themeToggleBtn');
        if (topbarToggle && !topbarToggle.hasAttribute('data-bound')) {
            topbarToggle.setAttribute('data-bound', 'true');
            topbarToggle.addEventListener('click', window.toggleConnectHubTheme);
        }

        const dropdownToggle = document.getElementById('dropdownThemeToggle');
        if (dropdownToggle && !dropdownToggle.hasAttribute('data-bound')) {
            dropdownToggle.setAttribute('data-bound', 'true');
            dropdownToggle.addEventListener('click', function(e) {
                e.preventDefault();
                window.toggleConnectHubTheme();
            });
        }

        const sidebarToggle = document.getElementById('sidebarThemeToggle');
        if (sidebarToggle && !sidebarToggle.hasAttribute('data-bound')) {
            sidebarToggle.setAttribute('data-bound', 'true');
            sidebarToggle.addEventListener('click', window.toggleConnectHubTheme);
        }

        const bannerToggle = document.getElementById('bannerThemeToggle');
        if (bannerToggle && !bannerToggle.hasAttribute('data-bound')) {
            bannerToggle.setAttribute('data-bound', 'true');
            bannerToggle.addEventListener('click', window.toggleConnectHubTheme);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initUI);
    } else {
        initUI();
    }
})();
