// ConnectHub Service Worker - Real Windows Desktop Background Notifications

self.addEventListener("install", (event) => {
    // Activate immediately
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
    let data = {};
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = {
                title: "ConnectHub Notification",
                body: event.data.text()
            };
        }
    }

    const title = data.title || "ConnectHub Notification";
    const options = {
        body: data.body || "",
        icon: data.icon || "/static/icons/icon-192.png",
        badge: data.badge || "/static/icons/badge-72.png",
        tag: data.tag || "connecthub-" + Date.now(),
        data: data.data || { url: data.url || "/" },
        renotify: data.renotify !== false,
        requireInteraction: data.requireInteraction || false,
        silent: data.silent || false
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    const targetUrl = (event.notification.data && event.notification.data.url)
        ? event.notification.data.url
        : "/";

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
            // Check if there is already a window open
            for (const client of clientList) {
                if ("focus" in client) {
                    client.focus();
                    if ("navigate" in client && targetUrl) {
                        client.navigate(targetUrl);
                    }
                    return;
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});

