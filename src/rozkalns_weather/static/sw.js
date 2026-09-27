const CACHE = "rozkalns-weather-v11";
const CACHE_PREFIX = "rozkalns-weather-";
const ASSETS=[
  "/",
  "/static/app.css",
  "/static/accepted_ui.css",
  "/static/ui_preferences.js",
  "/static/daily_trend.js",
  "/static/app.js",
  "/static/weather_ui.js",
  "/static/consumer_ui.js",
  "/static/runtime_badge.js",
  "/static/accuracy_v3.js",
  "/static/provenance_v1.js",
  "/static/time_semantics.js",
  "/static/manifest.webmanifest",
  "/static/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) => Promise.all(
      names
        .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE)
        .map((name) => caches.delete(name))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});

