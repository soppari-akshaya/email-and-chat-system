// ConnectHub Windows Desktop Notifications & Web Push Manager

(function () {
    "use strict";

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        const input = document.querySelector('input[name="csrf_token"]');
        if (input && input.value) return input.value;
        return "";
    }

    function urlBase64ToUint8Array(base64String) {
        const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, "+")
            .replace(/_/g, "/");

        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    // Register Service Worker
    let swRegistration = null;
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js", { scope: "/" })
                .then((registration) => {
                    swRegistration = registration;
                    if ("Notification" in window && Notification.permission === "granted") {
                        syncPushSubscription(registration);
                    }
                })
                .catch((err) => {
                    console.warn("ServiceWorker registration error:", err);
                });
        });
    }

    async function syncPushSubscription(registration) {
        if (!registration || !("pushManager" in registration)) return;
        try {
            const res = await fetch("/notifications/vapid-public-key");
            const data = await res.json();
            if (!data.publicKey) return;

            const existingSub = await registration.pushManager.getSubscription();
            if (existingSub) {
                await sendSubscriptionToServer(existingSub);
                return;
            }

            const convertedVapidKey = urlBase64ToUint8Array(data.publicKey);
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: convertedVapidKey
            });
            await sendSubscriptionToServer(subscription);
        } catch (e) {
            console.warn("Push subscription sync notice:", e);
        }
    }

    async function sendSubscriptionToServer(subscription) {
        const subData = subscription.toJSON();
        try {
            await fetch("/notifications/subscribe", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken()
                },
                body: JSON.stringify(subData)
            });
        } catch (e) {
            console.warn("Failed to send push subscription to server:", e);
        }
    }

    async function requestNotificationPermission() {
        if (!("Notification" in window)) {
            alert("This browser does not support desktop notifications.");
            return "denied";
        }

        try {
            const permission = await Notification.requestPermission();
            updatePermissionUI(permission);

            if (permission === "granted") {
                if (swRegistration) {
                    await syncPushSubscription(swRegistration);
                }
                showDesktopNotification({
                    title: "ConnectHub Notifications Active",
                    body: "You will now receive real-time Windows desktop notifications for new emails and messages.",
                    url: "/dashboard"
                });
            }
            return permission;
        } catch (e) {
            console.error("Error requesting notification permission:", e);
            return "denied";
        }
    }

    function showDesktopNotification(options) {
        if (!("Notification" in window)) return;
        if (Notification.permission !== "granted") return;

        const title = options.title || "ConnectHub Notification";
        const body = options.body || "";
        const icon = options.icon || "/static/icons/icon-192.png";
        const badge = options.badge || "/static/icons/badge-72.png";
        const url = options.url || "/";
        const tag = options.tag || ("ch-" + Date.now());

        // Check if user is currently looking at this active conversation
        if (options.conversationId && typeof conversationId !== "undefined" && conversationId === options.conversationId && !document.hidden) {
            return;
        }

        if (swRegistration && "showNotification" in swRegistration) {
            swRegistration.showNotification(title, {
                body: body,
                icon: icon,
                badge: badge,
                tag: tag,
                data: { url: url },
                renotify: true
            });
        } else {
            try {
                const notif = new Notification(title, {
                    body: body,
                    icon: icon,
                    tag: tag,
                    data: { url: url }
                });
                notif.onclick = function (event) {
                    event.preventDefault();
                    window.focus();
                    if (url) window.location.href = url;
                    notif.close();
                };
            } catch (err) {
                console.warn("Notification error:", err);
            }
        }
    }

    async function testDesktopNotification() {
        if (!("Notification" in window)) {
            alert("This browser does not support desktop notifications.");
            return;
        }

        if (Notification.permission === "default") {
            const res = await requestNotificationPermission();
            if (res !== "granted") return;
        } else if (Notification.permission === "denied") {
            alert("Desktop notifications are blocked in your browser settings. Please click the lock/settings icon in the browser address bar to allow notifications for this site.");
            return;
        }

        showDesktopNotification({
            title: "ConnectHub Test Notification",
            body: "Windows desktop notifications are functioning properly on your system!",
            url: "/dashboard",
            tag: "test-" + Date.now()
        });

        // Trigger backend test route as well
        try {
            await fetch("/notifications/test-desktop", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken()
                }
            });
        } catch (e) {
            console.warn("Backend test push error:", e);
        }
    }

    function updatePermissionUI(permission) {
        const promptBanner = document.getElementById("desktopNotifBanner");
        if (promptBanner) {
            if (permission === "default") {
                promptBanner.classList.remove("d-none");
            } else {
                promptBanner.classList.add("d-none");
            }
        }

        const statusBadge = document.getElementById("notifPermissionStatus");
        if (statusBadge) {
            if (permission === "granted") {
                statusBadge.className = "badge bg-success-subtle text-success border border-success-subtle px-3 py-2";
                statusBadge.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> Notifications Enabled (Active)`;
            } else if (permission === "denied") {
                statusBadge.className = "badge bg-danger-subtle text-danger border border-danger-subtle px-3 py-2";
                statusBadge.innerHTML = `<i class="bi bi-x-circle-fill me-1"></i> Blocked by Browser Settings`;
            } else {
                statusBadge.className = "badge bg-warning-subtle text-warning border border-warning-subtle px-3 py-2";
                statusBadge.innerHTML = `<i class="bi bi-exclamation-circle-fill me-1"></i> Permission Required`;
            }
        }
    }

    // Check permission on load
    window.addEventListener("DOMContentLoaded", () => {
        if ("Notification" in window) {
            updatePermissionUI(Notification.permission);
        }
    });

    // Expose global ConnectHubNotifications API
    window.ConnectHubNotifications = {
        requestPermission: requestNotificationPermission,
        show: showDesktopNotification,
        test: testDesktopNotification,
        updateUI: updatePermissionUI
    };
})();

