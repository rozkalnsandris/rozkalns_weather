# PWA degraded, stale and offline UX

Issue #49 defines client-side degraded-state behavior for the private PWA without changing production runtime or service-worker deployment.

## State contract

The PWA exposes explicit `fresh`, `stale`, `error`, and `offline` states for station truth, hourly forecasts, precipitation, daily forecasts, provider health, warnings, and radar. Cached API payloads are stored only by the application layer and always carry `cached_at_utc`; cached content is never presented as current.

Provider-health remains source-specific. One degraded provider does not blank healthy providers, and each forecast surface keeps retrieval/provenance timestamps visible.

## DWD warning authority

DWD official warnings remain visually and semantically separate from forecast/model output. If the browser is offline or a cached warning payload is used, the UI explicitly states that the displayed warning data is not current official warning status.

## Service worker

The existing service worker keeps a small shell asset cache only. It does not add API endpoints to its install cache and does not write fetched API responses into CacheStorage. API fallback is handled by the application layer so stale/offline weather data always receives explicit timestamp/state labeling.

## Accessibility and mobile behavior

Dynamic state regions use `role="status"`, `aria-live="polite"`, and `aria-atomic="true"`; alert-level failures can be promoted to assertive announcements. Mobile CSS collapses provider cards to one column and keeps degraded-state banners visible.

No source change in this package deploys the service worker, mutates runtime/network state, changes Cloudflare, or stores private coordinates.
