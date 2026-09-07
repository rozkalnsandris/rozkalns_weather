# RPi5 public-only runtime handoff

This document is a **source contract**, not LIVE authorization. It prepares the weather application for a later trusted deployment through `rozkalnsandris/RPi5_main` while WeatherNext 3 private access is pending.

## First runtime mode

The first RPi5 candidate uses:

- `WEATHER_RUNTIME_MODE=public-only`;
- `DATABASE_INIT_MODE=require-existing`;
- DWD/Bright Sky/Open-Meteo public providers;
- DWD WMO 10416 as the measured station benchmark;
- no required `HOME_LAT` / `HOME_LON`;
- no required Google Cloud or WeatherNext credentials.

WeatherNext 3 remains first-class research functionality in source, but in this runtime class its absence is explicit `access_pending` and **does not make the public runtime unready**. No WeatherNext values are fabricated.

## Fixed package surface

Canonical production-candidate files:

- `Dockerfile` — non-root application image, UID 10001, internal port 8000;
- `deploy/docker-compose.public.yml` — fixed service names and commands;
- `deploy/runtime-descriptor.json` — machine-readable trusted-boundary handoff;
- `deploy/public-ingest-schedule.json` — scheduler and bootstrap contract.

Fixed Compose services:

- `schema-init` -> `rozkalns-weather init-database`;
- `weather` -> image default FastAPI/uvicorn entrypoint;
- `public-ingest` -> `rozkalns-weather ingest-public`;
- `readiness` -> `rozkalns-weather readiness`.

The future trusted adapter selects these reviewed identities. GitHub issue prose must never supply an arbitrary shell command, path, argv or environment payload.

## Persistent corpus semantics

The logical persistent storage class is the Docker named volume `weather_data`, mounted at `/app/data`; the canonical in-container database URL is `sqlite:///data/weather.db`.

Application startup in the reviewed RPi5 candidate uses `require-existing` and therefore does not initialize the production database. Schema creation is the separate explicit `schema-init` operation. Historical backfill is also separate from schema initialization and recurring ingest.

The intended first-live sequence is:

1. establish the persistent data volume;
2. explicit schema initialization;
3. `readiness` / `/ready` schema and privacy check;
4. optional read-only `smoke-public` network contract check;
5. explicit bounded DWD truth backfill;
6. explicit bounded deterministic forecast backfill;
7. integrity check;
8. enable recurring public ingest at the reviewed cadence.

Steps that write SQLite or historical corpus data require explicit production-data/LIVE authority. Merely merging this source does not authorize them.

## Backup and failure semantics

Before historical production corpus writes, a persistent storage target and an explicit backup/recovery decision must be established by the later LIVE operation. Application replacement must retain the named corpus volume.

No automatic corpus deletion, restore, cleanup or destructive rollback is part of this contract. After a mutation-capable LIVE step begins, unexpected state follows the repository fail-closed rules. Application rollback must never imply database rollback.

## Readiness contract

`GET /ready`, `GET /api/readiness` and `rozkalns-weather readiness` expose schema version 1 readiness. They report:

- runtime mode;
- database schema state and missing required tables;
- persistent storage class/writability without exposing its host path;
- public-provider last known state without performing network calls;
- WeatherNext configured/pending state as non-required for public runtime;
- home configured state as non-required;
- explicit privacy flags for coordinates, credentials and DB path.

Public provider `error` or `adapter_ready_not_ingested` is visible but does not make application runtime readiness false. Runtime readiness is based on the local application/storage/schema contract; provider network health remains an independently visible operational signal.

## Future `RPi5_main` source adapter contract

This repository does **not** mutate or authorize `RPi5_main`. After this handoff is merged, a separate RPi5_main source issue may review and register a static adapter compatible with `deploy/runtime-descriptor.json`.

Candidate identity:

- target alias: `rozkalns-weather-public-rpi5`;
- operation ID: `rozkalns-weather.public-runtime-release.v1`;
- execution location: `trusted-home-host`;
- authorization class: `STRICT` initially;
- ordinary `LIVE-ALL` eligibility: false until a dedicated canary proves the operation.

The future adapter must bind an exact merged weather source SHA and exact-SHA CI, independently resolve the current target baseline, and enforce fixed mutation categories/counts. It must not accept generic shell/path/argv/environment authority from GitHub text.

Database schema initialization, historical corpus backfill, backup/restore, private home configuration, Google Cloud/WeatherNext credentials, Cloudflare/network changes and package/root permission changes remain separate mutation classes. They must not be smuggled into an ordinary application-release adapter.

At the time this handoff was designed, the RPi5 executor registry did not contain a weather operation and global execution was disabled. That is dependency evidence only, not a promise about future mutable runtime state; the future RPi5_main issue must refresh it.

## Warning and privacy invariants

DWD remains the authoritative severe-weather warning source in Germany. WeatherNext is research output only. Exact home coordinates, credentials, `.env`, private host paths and runtime logs must not enter GitHub evidence.
