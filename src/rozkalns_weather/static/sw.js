const CACHE = "rozkalns-weather-v51";
const CACHE_PREFIX = "rozkalns-weather-";
const ASSETS=[
  "/",
  "/static/app.css",
  "/static/accepted_ui.css",
  "/static/vendor/leaflet/leaflet.css",
  "/static/vendor/leaflet/leaflet.js",
  "/static/ui_preferences.js",
  "/static/daily_trend.js",
  "/static/app.js?v=51",
  "/static/navigation_v1.js",
  "/static/model_snapshot_alignment.js",
  "/static/weather_ui.js",
  "/static/consumer_ui.js",
  "/static/observation_age.js",
  "/static/runtime_badge.js",
  "/static/time_semantics.js",
  "/static/manifest.webmanifest",
  "/static/icon.svg",
];
const SHELL_PATHS = new Set(ASSETS.map((asset) => new URL(asset, self.location.origin).pathname));

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
        try {
          const response = await fetch(event.request, { cache: "no-cache" });
          if (response.ok) await cache.put(event.request, response.clone());
          return response;
        } catch (error) {
          const cached = await cache.match(event.request);
          if (cached) return cached;
          throw error;
        }
      })
    );
    return;
  }

  event.respondWith(fetch(event.request));
});