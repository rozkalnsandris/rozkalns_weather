# PR #291 — Daily stale-cache fallback evidence

Part of umbrella #237 V3 acceptance. Umbrella #237 remains open.

## Bounded acceptance case

This evidence covers the real-shell Galaxy A55 `412×892` daily forecast location-scoped stale-cache path.

The browser proof:

1. loads `station_10416` with a fresh daily forecast;
2. waits for the production cache key `rozkalns-weather:pwa-cache:v1:daily-14-station_10416` to materialize;
3. records stable cached daily semantics: day `aria-label` values, provider label and hero high/low;
4. switches to `station_05480` and confirms a fresh daily surface there;
5. revisits `station_10416` while forcing only its `/api/daily` refresh to return HTTP 503;
6. requires `dailyState` to resolve to `stale` with `role="status"` and `aria-live="polite"`, including visible cache/not-current semantics;
7. requires the cached daily day labels, provider attribution and hero high/low to remain available instead of being replaced by the hard-error presentation;
8. requires independently refreshed hourly temperature and precipitation surfaces to remain `fresh` and usable;
9. verifies no horizontal overflow at `412×892`.

The final proof compares stable user-facing semantics rather than the complete `inner_text()` serialization of `#dailyGrid`. The initial test-first run demonstrated that Chromium can serialize whitespace and collapsed `<details>` content differently after a semantically equivalent rerender, so full text equality was an unnecessarily brittle assertion.

## Result

The existing production request lifecycle already satisfies this contract. No production JavaScript correction and no PWA cache bump are required; `rozkalns-weather-v31` remains current.

The initial test-first head `4668e76d67fdb2136bb3527706bd067bb2dfbcdf` produced one new-test assertion failure while 866 other tests passed. The assertion was corrected without changing production behavior.

Corrected exact-head verification on `009fa117a058fabe17c44f13ea4684aa81bdb426`:

- Backend tests #437 — SUCCESS.
- Governance gates #442 — SUCCESS.

## Scope boundary

This closes only the bounded daily location-scoped stale-cache fallback acceptance case. It does not claim manual production validation, every provider/filter combination, physical-device validation, manual screen-reader behavior, browser-chrome 200% zoom acceptance, or complete cross-view state-matrix coverage.

No LIVE/RPi5/runtime/DB/Cloudflare/private-provider mutation occurred.
