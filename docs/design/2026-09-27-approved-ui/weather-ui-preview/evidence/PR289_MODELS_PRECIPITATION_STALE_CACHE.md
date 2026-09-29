# PR #289 — Models precipitation stale-cache fallback evidence

Part of umbrella #237 V3 acceptance. Umbrella #237 remains open.

## Bounded acceptance case

This evidence covers the real-shell Galaxy A55 `412×892` Models precipitation location-scoped stale-cache path.

The browser proof:

1. loads `station_10416` with fresh temperature and precipitation data;
2. waits for the production cache key `rozkalns-weather:pwa-cache:v1:hourly-precipitation-48-station_10416` to materialize;
3. switches to `station_05480` and confirms fresh Models surfaces there;
4. revisits `station_10416` while forcing only its `precipitation_1h` refresh to return HTTP 503;
5. requires `modelsPrecipState` to resolve to `stale` with `role="status"` and `aria-live="polite"`;
6. requires the cached precipitation SVG to remain visible for the selected location;
7. requires the independently refreshed temperature surface to remain `fresh` and usable;
8. verifies no horizontal overflow at `412×892`.

Waiting for the concrete location-scoped cache key prevents an already-fresh DOM state from another request/location from satisfying cache priming early.

## Result

The existing production request lifecycle already satisfies this contract. No production JavaScript correction and no PWA cache bump are required; `rozkalns-weather-v31` remains current.

Test-first exact-head verification on `332d688297be5d4927d5f35e0a5871acf45fdd25`:

- Backend tests #431 — SUCCESS.
- Governance gates #436 — SUCCESS.

## Scope boundary

This closes only the bounded Models precipitation stale-cache fallback acceptance case. It does not claim manual production validation, every provider/filter combination, physical-device validation, manual screen-reader behavior, browser-chrome 200% zoom acceptance, or complete cross-view state-matrix coverage.

No LIVE/RPi5/runtime/DB/Cloudflare/private-provider mutation occurred.
