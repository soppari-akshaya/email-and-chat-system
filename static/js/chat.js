/**
 * ConnectHub Real-Time Chat Helpers
 */

window.ConnectHubChat = window.ConnectHubChat || {
    formatTime: function (utcStr) {
        if (!utcStr) return "";
        let s = String(utcStr).trim();
        if (!s.endsWith("Z") && !s.includes("+")) s += "Z";
        const d = new Date(s);
        if (isNaN(d.getTime())) return "";
        let hours = d.getHours();
        const mins = String(d.getMinutes()).padStart(2, "0");
        const ampm = hours >= 12 ? "PM" : "AM";
        hours = hours % 12 || 12;
        return `${String(hours).padStart(2, "0")}:${mins} ${ampm}`;
    }
};

