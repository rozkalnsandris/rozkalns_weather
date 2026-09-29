# Mobile prototype validation — 2026-09-28

Part of #237. Local HTTP prototype inspected in the Codex built-in browser, using the accepted design with the navigation fix from #254. This is prototype evidence, not production acceptance or physical-device emulation.

## Observed results

| Check | Scope | Result |
| --- | --- | --- |
| Bottom content and navigation clearance | All five views, both themes, 384 px, reduced height | Final text and controls reachable above navigation |
| Expanded disclosures | All seven disclosures, both themes, 384 px | Enter opens them; full text reachable by scrolling |
| Expanded bottom views | All five views, both themes, 412 px, reduced height | No observed text clipping or permanently obscured content |
| Forward Tab traversal | All five views, both themes, 384 px, default state | Controls, disclosures and five navigation links reached; focus exits frame |
| Disabled Overview control | Both themes | 14 dienas skipped; Atjaunot leads to navigation |
| Navigation activation | Models → Radar and Overview → Models | Both theme frames switch; shell focus restored to destination button |
| Radar keyboard adjustment | Both themes | ArrowRight advances slider; dark-frame accessible value verified as 14.15 · prognoze · demonstrācija |

Models' expanded source text initially extends below the viewport; scrolling exposes the complete paragraph. This is normal scrolling, not permanently hidden content.

Forward sequences: Models has three metric buttons, time select, disclosure and navigation; Radar has latest, slider, previous/play/next, disclosure and navigation; Accuracy has three metrics, lead-time select, two disclosures and navigation; Status has scenario select, two disclosures and navigation. Overview traverses source disclosure, retry and navigation. These checks do not cover every alternative data state or every interaction.

Screenshots were inspected in-session; no persisted screenshot artifacts are included. No additional defect was identified in this bounded pass.

## Automated 200% text-enlargement follow-up

PR #276 adds a real-shell Chromium regression proof at the Galaxy A55 `412×892` viewport using the browser engine's `Emulation.setEmulatedOSTextScale` with `scale=2.0`. The test traverses Overview, Models, Radar, Accuracy and Status and fails if the document gains horizontal overflow or the fixed bottom navigation or its controls clip their text.

This is an automated OS text-scale/reflow proof. It is not a claim that browser-chrome `Ctrl+Plus` zoom was exercised, and it does not replace a screen-reader or physical-device pass.

## Automated accessibility-tree follow-up

PR #278 adds a real-shell Chromium Accessibility Tree proxy at the Galaxy A55 `412×892` viewport using the Chrome DevTools Protocol accessibility domain. The proof checks that the application exposes the `main` and named primary-navigation landmarks, the five primary navigation controls, polite `status` live regions, navigation focus transfer, and a controlled Radar lazy-module failure as an assertive `alert` in the browser accessibility tree.

This validates browser/AX semantics used by assistive technology, not a complete screen-reader user-session. It does not claim manual NVDA, TalkBack, VoiceOver, speech-order, rotor, gesture, Braille-display or physical-device validation.

## Degraded-state interaction follow-up

PR #277 adds a real-shell Accuracy acceptance matrix covering `loading → fresh → preliminary/stale → request error` and cohort-filter behavior at `412×892`. A failed verification request now clears and disables the previous cohort selector instead of leaving old cohort evidence interactive.

This closes the bounded Accuracy filter/state case only; it does not by itself prove every state/filter combination across every view or production runtime integration.

## Automated Radar degraded-state follow-up

PR #279 adds a real-shell Radar acceptance matrix at the Galaxy A55 `412×892` viewport covering `fresh → stale-cache → hard request error`. The proof requires cached observed/nowcast frames and their timestamps to remain visible only while the surface is explicitly stale, while a hard request error must clear the prior frame list, expose an assertive error state, retain the safety text that unavailable radar does not mean precipitation is absent, and leave the refresh control usable.

This closes the bounded Radar metadata degraded-state case only. It does not claim raster/map rendering validation, manual production interaction, or complete state/filter coverage across every view.

## Automated Models degraded-location follow-up

PR #280 adds a real-shell Models acceptance matrix at the Galaxy A55 `412×892` viewport for a user location change where the new location's temperature request fails while precipitation remains fresh. The proof requires the Models location labels to move to the newly selected location, the temperature surface to expose an assertive error, and all temperature-derived visuals from the previous location — chart, uncertainty text, model snapshot and spread — to be cleared instead of remaining visible under the new location heading. The sibling precipitation surface must remain fresh and usable.

The same PR bumps the cache-first PWA shell to `rozkalns-weather-v26` so the corrected `forecast_loading.js` is not stranded behind the previous service-worker cache, and its browser lifecycle proof verifies the atomic `v25 → v26` worker update. This closes only the bounded Models location/partial-failure case; it does not claim every provider/filter combination or production runtime validation.

## Automated Status degraded-state follow-up

PR #281 adds a real-shell Status acceptance matrix at the Galaxy A55 `412×892` viewport covering `fresh → loading → stale → offline → hard request error`. It verifies that the WeatherNext Status card-level `data-state` remains synchronized with the accessible live-region state during refresh and offline transitions, while forecast availability and verification readiness continue to be reported separately and no WeatherNext value is inferred from another provider.

The correction also advances the cache-first PWA shell to `rozkalns-weather-v27`, with the atomic lifecycle proof rebased from `v26 → v27`, so the corrected `status_v1.js` cannot remain stranded behind the prior worker cache. The hard-error case explicitly clears only the test's Status fallback cache before a controlled 503; normal cached request failures remain stale/offline fallback evidence rather than being mislabeled as hard errors. This closes only the bounded Status state-consistency case and does not claim manual production, physical-device or complete cross-view state-matrix validation.

## Automated Overview degraded-location follow-up

PR #282 adds a real-shell Overview acceptance matrix at the Galaxy A55 `412×892` viewport for a forecast-location change where the new location's temperature request fails while precipitation and daily data remain available. The proof requires the temperature state to become an assertive error, all combined next-hours evidence from the previous location — hourly cards, chart, provider summary and detail — to be cleared, and the independently successful precipitation state to remain visible as a polite `status` for the newly selected location.

The recovery proof is bound to the actual `station_10416` `precipitation_1h` response before it accepts the refreshed Overview precipitation semantics, preventing a previous-location `fresh` state from satisfying the test early. The source path independently restores Overview temperature/precipitation state visibility before combined rendering can deduplicate equivalent fresh states. The same PR advances the cache-first PWA shell to `rozkalns-weather-v28`, with the lifecycle proof rebased from `v27 → v28`, so the corrected forecast-loading behavior is not stranded behind the prior service-worker cache.

This closes only the bounded Overview location/partial-failure case. It does not claim manual production validation, every provider/filter combination, or complete cross-view state-matrix coverage.

## Automated daily degraded-location follow-up

PR #283 adds a real-shell daily forecast acceptance matrix at the Galaxy A55 `412×892` viewport for a forecast-location change where the newly selected location's `/api/daily` request fails while sibling hourly temperature and precipitation continue to load successfully. The proof is bound to the controlled `station_10416` daily request and requires `dailyState` to expose an assertive error, the previous location's daily grid to be replaced by the explicit unavailable state, and the hero high/low values to reset to `H —° · L —°` rather than remain stale under the new location selection.

The same proof requires the hourly cards and combined hourly chart to remain usable and the page to retain mobile-width reflow, demonstrating that the daily failure remains isolated from successful sibling forecast surfaces. The existing production failure path already satisfied this contract, so PR #283 adds regression evidence only and does not change `forecast_loading.js` or advance the `rozkalns-weather-v28` PWA cache.

This closes only the bounded daily location/hard-failure case. It does not claim manual production validation, every provider/filter combination, or complete cross-view state-matrix coverage.

## Automated current-observation hard-error follow-up

PR #284 adds a real-shell current-observation acceptance matrix at the Galaxy A55 `412×892` viewport for a previously fresh DWD observation followed by a controlled hard `/api/current` 503 with the current fallback cache deliberately absent. The proof requires `currentState` to expose an assertive error, clears the observation-derived hero temperature, condition, icon, observation-time text and source text, clears humidity/wind/pressure/rain/cloud/gust detail values, and requires hourly and daily forecast siblings to remain usable.

The source correction centralizes fail-closed current-observation cleanup in `observation_age.js`, including the health-blocked watchdog path, while preserving normal cached `stale`/`offline` last-known observation evidence when an actual cached payload and timestamp remain available. The cache-first PWA shell advances from `rozkalns-weather-v28` to `rozkalns-weather-v29`, and the atomic lifecycle proof is rebased from `v28 → v29` so the corrected lifecycle module cannot remain stranded behind the prior worker cache.

This closes only the bounded current-observation hard-error cleanup case. It does not claim manual production validation, physical-device validation, manual screen-reader behavior, browser-chrome zoom acceptance, or complete cross-view state-matrix coverage.

## Automated current-observation provider-health degradation follow-up

PR #285 adds a real-shell current-observation acceptance proof at the Galaxy A55 `412×892` viewport for the distinct case where `/api/current` still returns a genuine fresh DWD observation while `dwd_observations` provider health reports `error`. The proof constructs an explicit network-sourced current result, renders it with the degraded provider-health state, and captures both immediate and settled DOM snapshots so the assertion is bound to the actual rendered lifecycle rather than an internal message string or a cache/fallback race.

The accepted UI must expose `currentState` as `data-state="error"`, `role="alert"`, `aria-live="assertive"` with the canonical compact text `ERROR · DWD observation provider degraded`, while retaining the available observation-derived temperature, condition, feels/source presentation, humidity, pressure and condition icon. Forecast sibling surfaces remain fresh. This separates provider-health degradation from the #284 hard-unavailable contract: only explicit `DWD current observation unavailable` semantics trigger fail-closed observation cleanup.

The source correction narrows the `observation_age.js` cleanup observer to that explicit unavailable semantic, preserving valid observation evidence during provider-health degradation while keeping the existing hard-unavailable watchdog/fetch-error cleanup intact. The cache-first PWA shell advances from `rozkalns-weather-v29` to `rozkalns-weather-v30`, with the atomic lifecycle proof rebased accordingly. An exact-head CI rerun after an unrelated headless hidden-rendering flake completed successfully without any code change, so that flake is not part of this bounded acceptance result.

This closes only the bounded current-observation provider-health degradation case. It does not claim manual production validation, physical-device validation, manual screen-reader behavior, browser-chrome zoom acceptance, or complete cross-view state-matrix coverage.

## Automated current-observation stale-cache fallback follow-up

PR #286 adds a real-shell current-observation acceptance proof at the Galaxy A55 `412×892` viewport for a previously fresh DWD observation followed by a controlled `/api/current` refresh failure while the production current cache remains available. The initial successful request populates the real cache path; the controlled 503 must then resolve through the cache-aware request lifecycle instead of becoming a hard-unavailable state.

The proof requires `currentState` to become `stale` with polite `status` semantics and canonical `STALE · DWD observation is not current` text, while retaining the cached observation-derived temperature, condition, source, humidity, wind, pressure, precipitation, cloud, gust and condition icon. Hourly and daily forecast sibling surfaces must remain fresh and usable, and the mobile shell must not gain horizontal overflow. This complements #284, where the cache is deliberately absent and the same request failure must fail closed, and #285, where the live observation remains available but provider health itself is degraded.

The existing production cache/fallback path already satisfies this contract, so PR #286 adds regression evidence only. It does not change current-observation source behavior or advance the `rozkalns-weather-v30` PWA cache.

This closes only the bounded current-observation stale-cache fallback case. It does not claim a physical offline-browser pass, manual production validation, physical-device validation, manual screen-reader behavior, browser-chrome zoom acceptance, or complete cross-view state-matrix coverage.

## Automated Models precipitation degraded-location follow-up

PR #287 adds the reciprocal real-shell Models partial-failure acceptance case at the Galaxy A55 `412×892` viewport. Starting from fresh temperature and precipitation charts, the proof changes the forecast location to `station_10416` while forcing only that location's `precipitation_1h` request to return 503. The temperature surface must remain fresh and usable for the new location, while `modelsPrecipState` must become an assertive error and the previous location's precipitation SVG must be removed instead of remaining visible below the new location label.

The source correction adds a precipitation-specific fail-closed visual cleanup in `forecast_loading.js`: only `#modelsPrecip` is replaced by an explicit `Precipitation forecast unavailable for this location.` presentation on a hard precipitation failure, while the independently successful temperature chart is preserved. The combined Overview hourly surface still clears because it requires both temperature and precipitation inputs. The cache-first PWA shell advances from `rozkalns-weather-v30` to `rozkalns-weather-v31`, and the source/sibling/offline lifecycle contracts are rebased to prove the atomic `v30 → v31` update.

This closes only the bounded reciprocal Models precipitation location/partial-failure case. It does not claim manual production validation, every provider/filter combination, physical-device validation, manual screen-reader behavior, browser-chrome zoom acceptance, or complete cross-view state-matrix coverage.

## Remaining acceptance work

- Manual browser-chrome 200% `Ctrl+Plus` zoom remains unproven because the earlier built-in browser shortcut did not change its zoom state; a narrow viewport or CSS scaling is still not a substitute for that manual browser-zoom check.
- Manual screen-reader validation (NVDA/TalkBack/VoiceOver as applicable), including real announcement order and interaction behavior.
- Physical Galaxy A55/S25+ validation.
- Remaining loading/error/stale/filter combinations outside the bounded Accuracy, Radar, Models, Status, Overview, daily and current-observation matrices and production integration checks.

The accepted design remains the implementation basis. Full V3 and #237 acceptance stay open. Production runtime, providers and deployment are unchanged by these source-level acceptance passes.
