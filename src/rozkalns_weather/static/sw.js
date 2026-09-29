const CACHE = "rozkalns-weather-v30";
const CACHE_PREFIX = "rozkalns-weather-";
const ASSETS=[
  "/",
  "/static/app.css",
  "/static/accepted_ui.css",
  "/static/ui_preferences.js",
  "/static/daily_trend.js",
  "/static/app.js",
  "/static/navigation_v1.js",
  "/static/model_snapshot_alignment.js",
  "/static/weather_ui.js",
  "/static/consumer_ui.js",
  "/static/observation_age.js",
  "/static/forecast_loading.js",
  "/static/request_lifecycle.js",
  "/static/pwa_lifecycle.js",
  "/static/radar_timeline.js",
  "/static/status_v1.js",
  "/static/runtime_badge.js",
  "/static/accuracy_v3.js",
  "/static/provenance_v1.js",
  "/static/time_semantics.js",
  "/static/manifest.webmanifest",
  "/static/icon.svg",
];
const SHELL_PATHS = new Set(ASSETS);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
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

function isShellRequest(request) {
  const url = new URL(request.url);
  return url.origin === self.location.origin && SHELL_PATHS.has(url.pathname);
}

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  if (isShellRequest(event.request)) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const cached = await cache.match(event.request, { ignoreSearch: true });
        if (cached) return cached;
        return fetch(event.request);
      })
    );
    return;
  }

  event.respondWith(fetch(event.request));
});
