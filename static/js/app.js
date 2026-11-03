/**
 * ConnectHub Application Client Utilities
 */

window.ConnectHub = window.ConnectHub || {};

ConnectHub.getCsrfToken = function () {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const input = document.querySelector('input[name="csrf_token"]');
    if (input && input.value) return input.value;
    return "";
};

