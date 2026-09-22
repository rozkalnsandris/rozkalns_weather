# RPi5 public-only runtime handoff — SIMPLE-DEPLOY v1

This handoff describes the **current** public-only Weather runtime boundary after final public acceptance through #176/#177.

## Current ordinary deployment model

Weather is a SIMPLE-DEPLOY consumer/canary. Shared GitHub-side build/publish/promotion policy is owned by `rozkalnsandris/ops-workflows`; trusted generic host reconciliation is owned by `rozkalnsandris/RPi5_main`.

Weather consumer source:

- `.simple-deploy.json`;
- `.github/workflows/simple-deploy.yml`;
- `deploy/docker-compose.public.yml`;
- health/readiness and persistence contracts in this repository.

Accepted shared workflow revision: `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`.

The one-time generic-deployer / Weather target cutover is **completed**. Ordinary already-classified Weather application releases now follow the standing path without a fresh per-release LIVE approval:

```text
guarded merge
-> shared SIMPLE-DEPLOY publishes/promotes exact source
-> generic RPi5 reconciler resolves one immutable digest
-> fixed Weather application service replacement
-> /health + /ready verification
-> deployed receipt
```

Historical Weather-specific broker/operator/`ops-workflows#46` queue/JIT/Composite paths are **legacy/superseded for ordinary application releases**. Their source remains audit/regression evidence only.

## Public acceptance and current-now semantics

Final public acceptance is **COMPLETE** through #176/#177.

Current accepted public behavior includes:

- reviewed Weather release identity deployed and healthy;
- `/health=200` and `/ready=200` at acceptance time;
- canonical public identity `station_05480` / DWD station `05480`;
- `/api/current` sourced from the exact-station DWD 05480 10-minute `DWD_CURRENT` feed;
- provider health for `dwd_observations` bound to the same current-feed source-time identity;
- hourly DWD 05480 observations retained as verification/history truth, not substituted for current-now;
- populated station-scoped hourly and daily forecast surfaces;
- WeatherNext shown as unavailable/pending when private access is absent, never fabricated;
- DWD warnings kept as a distinct official-warning surface.

The current-now split must remain explicit: the 10-minute `DWD_CURRENT` feed serves present conditions, while hourly DWD 05480 truth serves verification/history. Legacy `station_10416` cannot satisfy current-now health.

## Runtime mode and benchmark

Current public runtime uses:

- `WEATHER_RUNTIME_MODE=public-only`;
- `DATABASE_INIT_MODE=require-existing`;
- persistent Docker volume `weather_data`;
- DWD/Bright Sky/Open-Meteo public-provider transports as reviewed by current source contracts;
- canonical measured benchmark `station_05480` / DWD CDC station `05480` (Werl);
- fixed common deterministic benchmark window `2026-08-13..2026-08-26`;
- recurring public ingest enabled separately from application deployment;
- no required private `HOME_LAT` / `HOME_LON`;
- no required private Google Cloud / WeatherNext credentials for public-only readiness.

`station_10416` is legacy/MOSMIX reference compatibility only. Historical 10416 truth/bootstrap evidence remains preserved but is not the current measured benchmark.

WeatherNext 3 remains first-class research scope, but `access_pending` is non-blocking for public-only runtime. WeatherNext values must never be fabricated. DWD remains the official severe-weather warning authority.

## Persistent data boundary

`weather_data` is retained across ordinary application releases. Application replacement must not silently:

- initialize or migrate production schema;
- backfill historical corpus;
- delete/restore/repair SQLite data;
- enable/disable systemd ingest scheduling;
- modify private-provider credentials or home configuration.

Production schema/public corpus initialization and recurring-ingest activation were completed under their own reviewed exact gates. They remain different mutation classes from ordinary app release.

## Current benchmark/corpus semantics

Current measured truth and deterministic model comparison use the same public benchmark identity: `station_05480`.

Canonical current fixed common window:

```text
2026-08-13..2026-08-26
models: icon_d2, ecmwf_ifs, ecmwf_aifs
run hours: 00/06/12/18 UTC
truth: DWD CDC 05480
```

IFS long-horizon coverage is cycle-aware: 00/12 cycles extend farther than 06/18 cycles. Integrity expectations must preserve that distinction rather than treating valid shorter cycles as missing data.

The older `2026-04-02..2026-09-10` bootstrap attempt and its 10416 assumptions are historical rollout evidence only.

## Recurring public ingest

Recurring public ingest is an explicit host capability, independent from ordinary SIMPLE-DEPLOY application replacement.

The reviewed schedule contract uses the Weather public ingest service/timer and enable-last semantics. Current production activation has been completed and verified. Future systemd/timer mutation remains a host-control operation requiring the authority defined by current `RPi5_main` rules; application source merge does not imply it.

Provider failures are isolated. One provider's upstream/transport error must remain visible without erasing healthy provider state or making public readiness depend on fabricated provenance.

## Health/readiness contract

Production acceptance uses privacy-safe endpoints including:

- `/health` — application/local DB liveness summary;
- `/ready` and `/api/readiness` — schema/storage/provider/privacy readiness;
- `/api/health/providers` — provider ingest/freshness/failure-domain provenance;
- `/api/current` — exact-station DWD 05480 current-now observations;
- `/api/warnings` — DWD official warnings;
- `/api/radar` — observed/nowcast safety context.

Public-only Warnings/Radar may use the public benchmark reference when private home is not configured. Exact coordinates are not exposed through GitHub-safe evidence.

## Ordinary release safety boundary

Standing SIMPLE-DEPLOY authority is narrow: fixed consumer, fixed image contract, fixed application replacement and health/readiness verification.

It does **not** authorize:

- production SQLite/corpus/checkpoint writes or migration;
- destructive recovery/restore/delete;
- Docker/systemd/root/path/argv improvisation outside the reviewed generic deployer contract;
- `.env`, credentials, IAM, BigQuery private access or Analytics Hub link changes;
- private-home activation;
- Cloudflare/network/DNS mutation;
- filesystem ownership/permission changes.

Those remain separate exact owner gates where applicable.

## WeatherNext private continuation

The public runtime is no longer blocked by WeatherNext.

- #168 is **completed**: the first-access canary/source contract is aligned to canonical `station_05480`; legacy `station_10416` is not the private first-access target.
- #122 is the next private WeatherNext gate, but it is **not authorized to execute** merely because public acceptance and #168 are complete.
- Before any private Google/BigQuery request, refresh current Weather `main`/CI, trusted RPi5 source/execution binding, runtime-only Google project/dataset binding, schema fingerprint, and one bounded `station_05480` query plan with an explicit bytes cap.
- Private first access remains read-only: no private-home scope, no production SQLite/schema/corpus/checkpoint write, no credential/IAM mutation, and no real WeatherNext value may be fabricated.
- Executing that private read requires a fresh exact owner authorization for the `read_only_private_bigquery` class/target.
- Persisting the first real WeatherNext snapshot remains a separate later production-data mutation gate.

## Historical first-rollout evidence

The following are retained as historical/audit compatibility only and are not current ordinary-release prerequisites:

- `deploy/rpi5-source-binding.json`;
- `deploy/first-public-rollout-preflight.json`;
- historical Weather operator/JIT/Composite contracts;
- old `ops-workflows#46` queue receipts;
- point-in-time pre-LIVE host state from earlier handoffs.

Historical mutable SHA/queue/operator assertions must never be reused as current runtime proof.

## Current source of truth

For a new work cycle:

1. read `AGENTS.md` and current repo contracts;
2. read controller issue #9;
3. refresh current `main` / exact-head CI;
4. obtain minimum-sufficient fresh RPi5 read-only evidence only when runtime state matters.

Do not infer current deployment/runtime state from historical handoff SHA values.

## Warning and privacy invariants

DWD remains authoritative for severe-weather warnings in Germany. WeatherNext remains research output only.

Exact home address/coordinates, credentials, `.env`, private host paths and raw private runtime logs must not be committed to GitHub.
