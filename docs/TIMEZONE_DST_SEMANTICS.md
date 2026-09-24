# UTC / Europe-Berlin DST semantics

Canonical forecast, observation and provenance timestamps remain **UTC**. This contract changes display/grouping semantics only; it never rewrites stored corpus timestamps.

## Contract

Machine-readable policy: `contracts/timezone-dst-v1.json`.

- canonical storage/provenance timezone: `UTC`;
- display/calendar timezone: `Europe/Berlin`;
- browser/host timezone must not choose grouping semantics;
- local day/month periods are converted to half-open UTC query intervals `[start_utc, end_utc)`;
- timezone-naive input, invalid offsets and persisted non-UTC/local timestamps are blocked with stable reason codes.

`src/rozkalns_weather/time_semantics.py` is the source-side reference implementation. It keeps the canonical UTC instant in every display identity.

## DST transitions

Spring-forward has no synthetic `02:xx` local hour. For example, on 2026-03-29, `00:30Z` renders as `01:30 +01:00`, while `01:30Z` renders as `03:30 +02:00`.

Autumn fallback contains two distinct local `02:xx` hours. They must never collapse to one chart/table identity: `2026-10-25T00:30Z` is `02:30 +02:00`, while `2026-10-25T01:30Z` is `02:30 +01:00`. PWA time labels therefore include the UTC offset; provenance surfaces retain the canonical UTC timestamp as well.

A Berlin calendar day can be 23, 24 or 25 hours. A Berlin calendar month can likewise differ from `days * 24` hours. Report boundaries must use the conversion helper instead of constructing UTC midnight from a local calendar label.

## PWA rules

`/static/time_semantics.js` is loaded after the main PWA scripts and replaces generic browser-local formatting with explicit `Europe/Berlin` formatting. It:

- rejects non-UTC timestamp strings for canonical forecast/observation display helpers;
- includes `GMT+1`/`GMT+2` (or equivalent short offset) in local clock labels;
- derives daily grouping and the verification month selector from the Berlin calendar;
- triggers a source-level refresh after installing the deterministic formatters so chart/hour-card labels use the DST-safe identity.

No provider value or canonical timestamp is changed.

## Report rules

`berlin_local_day_utc_bounds()` and `berlin_local_month_utc_bounds()` define deterministic report/query boundaries. The resulting UTC bounds are half-open and preserve local calendar intent across DST changes. Fixtures lock spring-forward, autumn fallback, month-boundary and UTC-date-versus-local-date cases.

These helpers prove period semantics only; they do not authorize or perform production corpus migration, repair or timestamp rewriting.
