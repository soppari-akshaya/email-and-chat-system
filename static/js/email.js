/**
 * ConnectHub Email Workspace Helpers
 */

window.ConnectHubEmail = window.ConnectHubEmail || {
    toggleSelectAll: function (masterCheckbox, itemSelector) {
        const checkboxes = document.querySelectorAll(itemSelector || ".email-checkbox");
        checkboxes.forEach(cb => { cb.checked = masterCheckbox.checked; });
    }
};

