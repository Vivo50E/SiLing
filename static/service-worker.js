const CACHE_NAME = "siling-pwa-v2";
const OFFLINE_ASSETS = [
  "/static/offline.html",
  "/static/icons/orchestrator-192.png",
  "/static/icons/orchestrator-512.png",
  "/static/icons/apple-touch-icon.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(OFFLINE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET" || request.mode !== "navigate") return;

  // This is a live control panel: never serve a cached dashboard or API.
  // Only show a static explanation when its local backend cannot be reached.
  event.respondWith(
    fetch(request).catch(() => caches.match("/static/offline.html"))
  );
});
