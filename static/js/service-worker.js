const CACHE_NAME = "rafiki-static-v1";
const SHELL_ASSETS = [
    "/static/offline.html",
    "/static/css/style.css?v=20260927-pwa-1",
    "/static/js/app.js",
    "/static/js/pwa.js",
    "/static/manifest.webmanifest",
    "/static/images/pwa-icon-180.png",
    "/static/images/pwa-icon-192.png",
    "/static/images/pwa-icon-512.png"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(SHELL_ASSETS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys
                    .filter((key) => key.startsWith("rafiki-static-") && key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") {
        return;
    }

    const requestUrl = new URL(request.url);
    if (requestUrl.origin !== self.location.origin) {
        return;
    }

    if (requestUrl.pathname.startsWith("/static/")) {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    if (response.ok) {
                        event.waitUntil(
                            caches.open(CACHE_NAME)
                                .then((cache) => cache.put(request, response.clone()))
                                .catch(() => {})
                        );
                    }
                    return response;
                })
                .catch(() => caches.match(request).then((cached) => cached || Response.error()))
        );
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(() => caches.match("/static/offline.html"))
        );
    }
});