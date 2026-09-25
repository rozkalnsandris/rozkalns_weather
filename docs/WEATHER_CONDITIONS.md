# Weather condition and day/night contract

`weather-condition-v1` is the source contract for the Overview condition icons and meteorological day/night theme.

## Upstream fields

Open-Meteo Single Runs is queried with the existing exact model/run identity plus two additive hourly fields:

- `weather_code` — WMO numeric weather code;
- `is_day` — `1` for daylight and `0` for night.

Canonical upstream references:

- https://open-meteo.com/en/docs/single-runs-api
- https://open-meteo.com/en/docs

Both values are stored as normal immutable `ForecastValue` rows, so provider, model, init, retrieval, valid time and lead metadata stay attached to the same forecast run. Existing corpus rows are not rewritten.

## Normalized condition vocabulary

The project-owned SVG layer uses these normalized identities:

`clear`, `mostly_clear`, `partly_cloudy`, `overcast`, `fog`, `drizzle`,
`freezing_precipitation`, `rain`, `heavy_rain`, `snow`, `thunderstorm`,
`thunderstorm_hail`, `unknown`.

WMO mapping follows the Open-Meteo documented WMO interpretation. Raw WMO code remains available in corpus/API data. Freezing precipitation, snow, thunderstorm and hail are never collapsed into generic rain labels.

## Backward-compatible fallback

`weather-condition-fallback-v1` is used only when the same forecast run has no `weather_code`.

For the same provider + init/retrieval identity + valid time:

1. precipitation `>= 2.0 mm/h` -> `heavy_rain`;
2. precipitation `>= 0.2 mm/h` -> `rain`;
3. precipitation `>= 0.05 mm/h` -> `drizzle`;
4. otherwise cloud cover:
   - `< 20%` -> `clear`;
   - `< 45%` -> `mostly_clear`;
   - `< 80%` -> `partly_cloudy`;
   - `>= 80%` -> `overcast`;
5. insufficient evidence -> `unknown`.

This fallback cannot produce fog, snow, freezing precipitation, thunderstorm or hail. Those identities require an explicit supported WMO code.

The current DWD observation hero uses the same safe precipitation/cloud vocabulary. Observation inputs are aligned to one observed timestamp before deriving the visible condition.

## Day/night selection

Day/night is meteorological display state, not the browser/OS appearance preference.

Selection order:

1. same-provider, same-run, same-valid-time stored `is_day`;
2. sunrise/sunset evidence if a future source contract adds it;
3. last-resort `Europe/Berlin` local-hour fallback (`07:00 <= local hour < 19:00` => day);
4. otherwise `unknown`.

The fixed-hour fallback is deliberately labelled `timezone-hour-fallback-v1`; it is not provider truth. A future sunrise/sunset source can be inserted ahead of it without changing stored timestamps.

## Daily summary

`/api/daily` keeps its existing temperature/precipitation fields and adds condition metadata.

Daily condition selection is deterministic and is never the arbitrary first/last hour. For evidence from the exact same provider/init/retrieval run as the base daily row, the most severe normalized condition is selected using this stable order:

`thunderstorm_hail` > `thunderstorm` > `freezing_precipitation` > `snow` >
`heavy_rain` > `rain` > `drizzle` > `fog` > `overcast` >
`partly_cloudy` > `mostly_clear` > `clear` > `unknown`.

A direct WMO-derived row wins a tie over fallback evidence; for otherwise equivalent condition evidence, a provider-backed daylight row wins over night/unknown for the daily presentation. The selected row's daylight identity is retained for the daily icon.

These condition summaries are forecast presentation data. They are not DWD official warnings.

## SVG and accessibility

The SVG family is original project source in `static/weather_ui.js`; no third-party icon pack is imported.

- Hero icon is decorative because the equivalent condition label is visible next to it: `aria-hidden="true"` and `focusable="false"`.
- Hourly/daily icons carry `role="img"` and `aria-label`.
- Color/theme is never the only carrier of condition meaning.

References:

- https://developer.mozilla.org/en-US/docs/Web/SVG/Guides/SVG_in_HTML
- https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/img_role
- https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-hidden

## PWA cache

Static asset cache names are versioned. On service-worker `activate`, obsolete caches with the Rozkalns Weather cache prefix are removed before the new worker takes control.

References:

- https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers
- https://developer.mozilla.org/en-US/docs/Web/API/CacheStorage/delete

## Visual acceptance fixture

`tests/fixtures/weather_visual_states.html` is a network-independent fixture for the canonical visual-verification tooling.

Required capture viewports:

- desktop: `1440x900`;
- Galaxy A55 class: `412x892`.

The fixture contains clear day, partly-cloudy day, rainy day, clear night, thunderstorm and unknown states. Runtime/deployed screenshots remain read-only evidence and do not grant deployment or host mutation authority.
