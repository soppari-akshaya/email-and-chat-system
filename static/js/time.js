/**
 * ConnectHub Universal Local Time Formatter
 * Automatically converts UTC timestamps into the user's exact local wall-clock time and timezone.
 */
(function() {
    function parseUtcDate(utcStr) {
        if (!utcStr) return null;
        let s = String(utcStr).trim();
        if (!s) return null;

        // If string has format "YYYY-MM-DD HH:MM:SS" (e.g. SQLite raw string), replace space with T
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(s)) {
            s = s.replace(" ", "T");
        }

        // If no timezone specified, treat as UTC
        if (!s.endsWith("Z") && !s.includes("+") && !s.slice(10).includes("-")) {
            s += "Z";
        }

        const d = new Date(s);
        return isNaN(d.getTime()) ? null : d;
    }

    function formatTime12h(d) {
        let hours = d.getHours();
        const minutes = String(d.getMinutes()).padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12 || 12;
        const strHours = String(hours).padStart(2, '0');
        return `${strHours}:${minutes} ${ampm}`;
    }

    function formatMailListTime(utcStr) {
        const d = parseUtcDate(utcStr);
        if (!d) return "";
        const now = new Date();
        const day = String(d.getDate()).padStart(2, '0');
        const month = d.toLocaleDateString('en-US', { month: 'short' });
        const timeStr = formatTime12h(d);
        if (d.getFullYear() === now.getFullYear()) {
            return `${day} ${month}, ${timeStr}`;
        }
        return `${day} ${month} ${d.getFullYear()}, ${timeStr}`;
    }

    function formatMailDetailTime(utcStr) {
        const d = parseUtcDate(utcStr);
        if (!d) return "";
        const weekday = d.toLocaleDateString('en-US', { weekday: 'long' });
        const day = String(d.getDate()).padStart(2, '0');
        const month = d.toLocaleDateString('en-US', { month: 'long' });
        const year = d.getFullYear();
        const timeStr = formatTime12h(d);
        return `${weekday}, ${day} ${month} ${year} at ${timeStr}`;
    }

    function formatMailShortDate(utcStr) {
        const d = parseUtcDate(utcStr);
        if (!d) return "";
        const now = new Date();
        const day = String(d.getDate()).padStart(2, '0');
        const month = d.toLocaleDateString('en-US', { month: 'short' });
        if (d.getFullYear() === now.getFullYear()) {
            return `${day} ${month}`;
        }
        return `${day} ${month} ${d.getFullYear()}`;
    }

    function formatNotifTime(utcStr) {
        const d = parseUtcDate(utcStr);
        if (!d) return "";
        const day = String(d.getDate()).padStart(2, '0');
        const month = d.toLocaleDateString('en-US', { month: 'short' });
        const year = d.getFullYear();
        const timeStr = formatTime12h(d);
        return `${day} ${month} ${year}, ${timeStr}`;
    }

    window.ConnectHubTime = {
        parseUtcDate: parseUtcDate,
        formatTime12h: formatTime12h,
        formatMailListTime: formatMailListTime,
        formatMailDetailTime: formatMailDetailTime,
        formatMailShortDate: formatMailShortDate,
        formatNotifTime: formatNotifTime,
        refreshAll: function() {
            document.querySelectorAll(".mail-time[data-utc]").forEach(el => {
                const utc = el.getAttribute("data-utc");
                if (utc) {
                    const formatted = formatMailListTime(utc);
                    if (formatted) el.textContent = formatted;
                    const d = parseUtcDate(utc);
                    if (d) el.title = d.toLocaleString();
                }
            });

            document.querySelectorAll(".mail-detail-time[data-utc]").forEach(el => {
                const utc = el.getAttribute("data-utc");
                if (utc) {
                    const formatted = formatMailDetailTime(utc);
                    if (formatted) el.textContent = formatted;
                    const d = parseUtcDate(utc);
                    if (d) el.title = d.toLocaleString();
                }
            });

            document.querySelectorAll(".mail-date-short[data-utc]").forEach(el => {
                const utc = el.getAttribute("data-utc");
                if (utc) {
                    const formatted = formatMailShortDate(utc);
                    if (formatted) el.textContent = formatted;
                    const d = parseUtcDate(utc);
                    if (d) el.title = d.toLocaleString();
                }
            });

            document.querySelectorAll(".notif-time[data-utc]").forEach(el => {
                const utc = el.getAttribute("data-utc");
                if (utc) {
                    const formatted = formatNotifTime(utc);
                    if (formatted) el.textContent = formatted;
                    const d = parseUtcDate(utc);
                    if (d) el.title = d.toLocaleString();
                }
            });
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.ConnectHubTime.refreshAll);
    } else {
        window.ConnectHubTime.refreshAll();
    }
})();
