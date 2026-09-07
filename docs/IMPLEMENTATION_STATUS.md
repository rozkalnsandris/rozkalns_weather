# Implementation status

Status during the Issue #15 AUTO-RUN FULL v2 source lane.

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

## Public benchmark v3
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

## Issue #15 public-only RPi5 source contract
- `WEATHER_RUNTIME_MODE=public-only` is the first RPi5 runtime class; neither WeatherNext credentials nor private home coordinates are prerequisites.
- WeatherNext absence stays explicit `access_pending` and is never represented by fabricated values.
- `DATABASE_INIT_MODE=require-existing` prevents the reviewed application service from implicitly creating the production SQLite schema.
- `rozkalns-weather init-database` is the explicit schema mutation entrypoint; `rozkalns-weather readiness` is read-only with respect to schema creation and network access.
- `/ready` and `/api/readiness` expose machine-readable schema/storage/provider/privacy state without database paths, credentials or coordinates.
- `deploy/docker-compose.public.yml` fixes application/bootstrap/public-ingest/readiness service identities and runs as non-root with no-new-privileges/cap-drop hardening.
- `deploy/runtime-descriptor.json` defines the public-safe target alias, operation ID candidate, persistent volume semantics, health contract and future RPi5 mutation/exclusion envelope.
- `deploy/public-ingest-schedule.json` keeps public ingest cadence separate from WeatherNext and requires explicit bootstrap ordering.
- Historical backfill remains a separate bounded data-write operation; it is never an application startup side effect.
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md` defines the later `RPi5_main` adapter expectations without claiming cross-repo or runtime authority.
- Fixture-driven rollout tests cover public-only startup, WeatherNext-pending behavior, no implicit DB creation, provider failure visibility, descriptor privacy and bootstrap/schedule semantics.

## Still external/live or cross-repository gated
1. WeatherNext allowlist/access approval.
2. Private runtime `HOME_LAT` / `HOME_LON` if/when home forecasts are activated.
3. Google Cloud project/linked dataset/credentials and first real WeatherNext snapshot.
4. A separate `RPi5_main` source issue must review/register the static weather deploy adapter; current weather Issue #15 does not mutate that repository.
5. RPi5 application deployment, Docker/systemd/timer activation and any host/filesystem/network changes require separate exact LIVE authority.
6. Production SQLite schema initialization and historical/public corpus population are explicit data-write/LIVE gates.
7. Backup/restore and any destructive data recovery are separately gated; application rollback never implies DB rollback.
8. Meaningful measured rankings and bootstrap intervals require enough real common-sample corpus.

Home forecasts are not verified against DWD 10416 as if they were the same physical point. Measured accuracy uses the station benchmark. WeatherNext 3 real values remain absent until private access is explicitly ready; no placeholder values are fabricated.
