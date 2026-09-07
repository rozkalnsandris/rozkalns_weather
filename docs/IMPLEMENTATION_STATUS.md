# Implementation status

Status during the Issue #12 AUTO-RUN FULL v2 source lane.

## Source-complete
- FastAPI + SQLite immutable forecast corpus.
- Location-aware forecast identity: `station_10416` and private runtime-only `home`.
- DWD MOSMIX-L 10416 and DWD observation truth.
- ICON-D2 / ECMWF IFS HRES / AIFS Single Runs with explicit run provenance and Open-Meteo availability metadata contract.
- Provider runner with bounded read retry, failure isolation, single-cycle file lock, idempotent content hashing and revision tracking.
- Corpus integrity/stats/SQLite backup commands.
- WeatherNext BigQuery schema/query validator, 0.05° station-head + 0.1° surface, six summary statistics and hourly cycle handling.
- WeatherNext readiness diagnostics.
- Temperature MAE/RMSE/bias, lead buckets, model versions and p10–p90 coverage.
- Precipitation amount/probability separation, Brier/reliability foundation.
- Monthly WeatherNext station-skill report with common timestamps per lead bucket and small-sample warning.
- PWA/API surfaces for station truth, home forecasts, accuracy and DWD warning/radar separation.
- Docker/systemd deploy preparation only.

## Issue #12 public benchmark v3 source
- Bounded/resumable exact-run archive backfill module with explicit model/date/run-hour ranges, dry-run, rate limit and atomic checkpoint/resume.
- Archive boundaries are explicit: ICON-D2/AIFS common availability starts 2026-04-02; IFS may retain older history only as a separate non-common series.
- Historical exact runs preserve explicit `run=` init provenance and do not fabricate upstream availability metadata when the historical surface does not expose it.
- Historical DWD truth path is pinned to WMO `10416`; Bright Sky is transport only and rows without explicit 10416 source identity are rejected.
- Backfill reconciliation reports missing/unexpected runs and immutable revisions; idempotent inserts reuse existing identical snapshots.
- Public ensemble adapters exist for ICON-D2-EPS, IFS ENS 0.25° and AIFS ENS 0.25° with control/member identities and explicit three-day individual-member retention boundary.
- WeatherNext 2 exists only as `legacy_ai_context`; the Open-Meteo transport surface is marked non-eligible for strict run-to-run ranking without defensible exact init provenance.
- Genuine ensemble verification primitives include CRPS, empirical quantiles, interval coverage/width, WIS-style scoring, member-fraction precipitation probability, Brier and reliability.
- Common-sample leaderboard keeps comparison mode, lead bucket and model version separate, reports explicit `n`, and emits bootstrap MAE CI only for `n >= 30`.
- Matched event verification covers temperature extremes, precipitation and wind/gust event contingency summaries.
- Accuracy v3 UI surfaces deterministic/ensemble/legacy provider classes, deterministic lead-bucket sample/confidence and genuine precipitation calibration separately.
- Fixture-driven tests cover backfill dry-run/resume/idempotency, exact-run provenance, pinned truth station, ensemble member retention/provenance, genuine probabilistic metrics, common-sample fairness/CI and event summaries.

## Still external/live or data-population gated
1. WeatherNext allowlist/access approval.
2. Private runtime `HOME_LAT` / `HOME_LON`.
3. Google Cloud project/linked dataset/credentials.
4. First real WeatherNext snapshot.
5. RPi5 deployment and optional Cloudflare Access.
6. Production/public corpus population itself remains a data-write/LIVE gate; source code does not authorize execution against production storage.
7. Meaningful measured rankings and bootstrap intervals require enough real common-sample corpus.

Home forecasts are not verified against DWD 10416 as if they were the same physical point. Measured accuracy uses the station benchmark. WeatherNext 3 real values remain absent until private access is explicitly ready; no placeholder values are fabricated.
