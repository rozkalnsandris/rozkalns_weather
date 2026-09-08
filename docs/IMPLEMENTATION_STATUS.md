# Implementation status

Status reconciled after `AUDIT-HANDOFF` on 2026-09-08 and extended by Issue #19 and Issue #22 source work.

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

## Public-only RPi5 weather source contract
- `WEATHER_RUNTIME_MODE=public-only` is the first RPi5 runtime class; neither WeatherNext credentials nor private home coordinates are prerequisites.
- WeatherNext absence stays explicit `access_pending` and is never represented by fabricated values.
- `DATABASE_INIT_MODE=require-existing` prevents the reviewed application service from implicitly creating the production SQLite schema.
- `rozkalns-weather init-database` is the explicit schema mutation entrypoint; `rozkalns-weather readiness` is read-only with respect to schema creation and network access.
- `/ready` and `/api/readiness` expose machine-readable schema/storage/provider/privacy state without database paths, credentials or coordinates.
- `deploy/docker-compose.public.yml` fixes application/bootstrap/public-ingest/readiness/corpus-check service identities and runs as non-root with no-new-privileges/cap-drop hardening.
- The `weather` application has no implicit `depends_on` chain to schema/backfill jobs; application replacement cannot silently initialize schema, backfill history, restore or delete corpus.
- `deploy/runtime-descriptor.json` binds the public-safe target/operation/persistent-volume/health contract to `deploy/rollout-readiness.json`.
- `deploy/public-ingest-schedule.json` carries host-consumable systemd unit identities, `*:0/30`, `Persistent=true`, 60-second bounded jitter, overlap semantics and enable-last ordering; actual install/enable remains LIVE-only.
- Historical backfill remains a separate bounded data-write operation; it is never an application startup side effect.
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md` defines the trusted-boundary adapter expectations without claiming cross-repo or runtime authority.

## Issue #19 rollout-readiness package
- `src/rozkalns_weather/rollout.py` validates the fixed source package and emits a sanitized source-only rollout plan.
- `rozkalns-weather rollout-preflight` binds an exact 40-character source SHA form, explicit bounded dates, WMO `10416`, exactly `icon_d2/ecmwf_ifs/ecmwf_aifs`, UTC `00/06/12/18`, maximum 180 inclusive days, recovery decision and ordered checkpoint prefix without network/runtime mutation.
- Source preflight deliberately does **not** claim that a SHA is merged to current `main` or that exact-SHA CI is green; those remain fresh GitHub/LIVE proofs.
- Bootstrap state order is fixed: volume ensure -> explicit schema init -> readiness -> optional read-only public smoke -> bounded DWD truth -> bounded deterministic forecasts -> corpus integrity -> recurring schedule enable.
- Checkpoint/resume accepts only an exact completed prefix; stage skipping/reordering, hidden retry and implicit stage advance are rejected.
- SQLite backup verification uses read-only `PRAGMA integrity_check`, required-table verification and SHA-256 metadata without exposing the path; production backup/restore remains a separate gated mutation class.
- Recovery decision is machine-readable: `verified_backup_available` or `owner_accepts_proceeding_without_prewrite_backup`; neither authorizes restore/delete/cleanup.
- `rollout-evidence-validate` accepts sanitized stdin evidence for exact deployed SHA identity, `/health`, `/ready`, provider-health, schema/storage, provider states, WeatherNext non-fabrication, volume retention and corpus-integrity postconditions, and rejects private paths/log/coordinate/credential fields.
- `deploy/rollout-readiness.json` contains stage-specific fail-closed behavior and explicitly preserves the already-merged `RPi5_main` #408/#409 + #410/#415 interface without enabling trusted execution/host wiring.
- Fixture-driven tests cover contract consistency, bounds/model/run-hour rejection, checkpoint ordering, disposable SQLite backup verification, evidence privacy and CLI behavior without runtime environment.

## Issue #22 WeatherNext first-access readiness package
- `deploy/weathernext-first-access.json` freezes the WeatherNext 3 BigQuery linked-dataset/table roles, six-statistic contract, one-init canary bounds, cost guardrails, privacy fields, state machine and explicit first-snapshot write boundary.
- `src/rozkalns_weather/weathernext_access.py` provides a network-free canary planner plus private-read-only schema/dry-run helpers that can later be invoked only under a separately authorized BigQuery gate.
- The first canary is pinned to logical benchmark location `station_10416`, maximum 24 forecast hours and an explicit per-query `maximum_bytes_billed`; the source contract additionally rejects caps above 1 GiB.
- Schema readiness uses deterministic SHA-256 fingerprints over the expected WeatherNext 3 0.05°/0.1° field contract and detects missing/renamed fields without emitting private project/dataset identity.
- BigQuery dry-run must succeed for both product surfaces before the real bounded canary helper is eligible; `SELECT *` stays forbidden and exact `init_time` partition filtering remains mandatory.
- Canary completeness requires non-empty 0.05° station temperature/dew-point output plus non-empty 0.1° surface output, but sanitized evidence reports only presence/counts rather than real values.
- Provenance validation preserves provider/model/version, init/retrieval/valid/lead/statistic/source/run-class/horizon and 60-minute precipitation semantics.
- Documented dissemination targets are stored as `expected_available_at_utc`; they are no longer fabricated into `upstream_available_at_utc`. The latter remains `null` until upstream provides defensible observed publication evidence.
- Access/schema/dry-run/canary/provenance stages are distinct from `production_sqlite_forecast_snapshot_write`. A validated write envelope proves only eligibility and never performs the write.
- `docs/WEATHERNEXT_FIRST_ACCESS.md` defines privacy-safe evidence and the later exact private gate fields. Fixture-driven tests use fake BigQuery clients and make no network request.

## RPi5_main trusted-boundary source integration
- `RPi5_main` Issue #408 / PR #409 is merged and registers the static `rozkalns-weather.public-runtime-release.v1` operation plus dedicated execution-disabled weather adapter.
- The operation remains `STRICT` and not ordinary `LIVE-ALL` eligible; source registration is not LIVE authority.
- `RPi5_main` Issue #410 / PR #415 is merged and adds the deterministic first-bootstrap composition for application release, volume ensure, explicit schema init, readiness, optional public smoke, bounded DWD truth and deterministic forecast backfill, integrity, and recurring public ingest scheduling.
- Application, schema, corpus-write and schedule mutation classes remain distinct even when a later exact LIVE authorization composes them into one bounded rollout.
- The source contracts do not provide arbitrary shell/path/argv/environment authority and do not include private runtime data.
- Trusted execution/host wiring remains disabled until separately authorized and freshly revalidated; mutable `RPi5_main` executor/runtime state must always be refreshed before any LIVE action.

## Still external/live gated
1. First public-only RPi5 rollout under a separate exact LIVE authorization after fresh source/host/target preflight.
2. Production SQLite schema initialization and historical/public corpus population under separately bounded data-write/LIVE authority, with explicit date/model bounds and recovery decision.
3. Any Docker/systemd/timer activation or host/filesystem/network mutation remains separately gated.
4. WeatherNext allowlist/access approval for private WeatherNext activation.
5. Private runtime `HOME_LAT` / `HOME_LON` if/when private-home forecasts are activated.
6. Google Cloud project/linked dataset/credentials, any real schema/dry-run/canary BigQuery request, and the first real WeatherNext snapshot remain private LIVE/data gates.
7. Analytics Hub linked-dataset creation/deletion or IAM/credential mutation remains a distinct exact owner gate and is not implied by first-access source readiness.
8. Backup/restore and any destructive data recovery remain separately gated; application rollback never implies DB rollback.
9. Meaningful measured rankings and bootstrap intervals require enough real common-sample corpus.

A read-only audit on 2026-09-08 found no deployed weather container, no `weather_data` volume and no weather systemd service/timer on the RPi5 at that time. This is point-in-time runtime evidence, not durable source truth; future LIVE work must refresh it.

Home forecasts are not verified against DWD 10416 as if they were the same physical point. Measured accuracy uses the station benchmark. WeatherNext 3 real values remain absent until private access is explicitly ready; no placeholder values are fabricated.
