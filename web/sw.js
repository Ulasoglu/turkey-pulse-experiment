const CACHE = "sehrin-ne-oldu-v13-province-news-feed";
const SHELL = ["./", "./index.html", "./styles.css", "./mobile-tune.css", "./image-cards.css", "./pulse-experience.css", "./app.js", "./pulse-experience.js", "./feed-data.js", "./feed-exit-reset.js", "./weather-ui.js", "./image-cards.js", "./manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.pathname.endsWith("/data/signals.json") || url.pathname.endsWith("/data/feed.json") || url.hostname === "raw.githubusercontent.com") return;
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  }
});
