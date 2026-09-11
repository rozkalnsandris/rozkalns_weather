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
- `deploy/docker-compose.public.yml` — fixed application and one-shot job identities;
- `deploy/runtime-descriptor.json` — machine-readable trusted-boundary handoff;
- `deploy/rollout-readiness.json` — bounded bootstrap/recovery/evidence/failure contract;
- `deploy/public-ingest-schedule.json` — deterministic scheduler handoff.

Fixed Compose services:

- `schema-init` -> `rozkalns-weather init-database`;
- `weather` -> image default FastAPI/uvicorn entrypoint;
- `public-ingest` -> `rozkalns-weather ingest-public`;
- `readiness` -> `rozkalns-weather readiness`;
- `corpus-check` -> `rozkalns-weather corpus-check`.

The application service does not `depends_on` schema-init, backfill or schedule activation. Replacing/starting `weather` therefore cannot silently initialize schema, backfill history, restore or delete corpus.

The trusted adapter selects these reviewed identities. GitHub issue prose must never supply an arbitrary shell command, host path, argv or environment payload.

## Deterministic source preflight

`rozkalns-weather rollout-preflight` validates the exact reviewed source checkout without network calls or runtime mutation. Inputs are explicit:

- exact 40-character weather source SHA form;
- bounded start/end dates;
- WMO `10416` truth identity;
- exact model set `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- exact UTC run hours `0,6,12,18`;
- maximum 180 inclusive days, no earlier than the three-model common benchmark start `2026-04-02`;
- one explicit recovery decision;
- optional already-completed checkpoint stages as an exact ordered prefix only.

The source preflight deliberately cannot prove current GitHub-main membership, exact-SHA CI, current `RPi5_main` state or current host state. Those are fresh evidence requirements at the LIVE gate.

## Persistent corpus and bootstrap semantics

The logical persistent storage class is the Docker named volume `weather_data`, mounted at `/app/data`; the canonical in-container database URL is `sqlite:///data/weather.db`.

Application startup uses `require-existing` and therefore does not initialize the production database. Schema creation is the separate explicit `schema-init` operation. Historical backfill is separate from both schema initialization and recurring ingest.

The fixed bootstrap state order is:

1. `volume_ensure`;
2. `explicit_schema_init`;
3. `readiness_check`;
4. `public_smoke_read_only` — optional, but explicitly checkpointed as passed or skipped;
5. `bounded_dwd_truth_backfill`;
6. `bounded_forecast_backfill`;
7. `corpus_integrity_check`;
8. `enable_recurring_public_ingest` last.

Resume accepts only an exact completed prefix of that sequence. Stage skipping/reordering, hidden retry and implicit stage advancement fail closed. The rollout plan emits a fingerprint bound to source SHA, dates/models/run hours and recovery decision.

Steps that write SQLite or historical corpus data require explicit production-data/LIVE authority. Merely merging this source does not authorize them.

## Backup and recovery semantics

Before historical production corpus writes, the later LIVE operation must bind exactly one recovery decision:

- `verified_backup_available`; or
- `owner_accepts_proceeding_without_prewrite_backup`.

The source verification helper can read a disposable SQLite backup using `PRAGMA integrity_check`, required-table checks and SHA-256 metadata while suppressing its path. That source capability does not authorize a production backup, restore or delete.

No automatic corpus deletion, restore, cleanup or destructive rollback is part of this contract. After a mutation-capable LIVE step begins, unexpected state follows fail-closed rules. Application rollback never implies database rollback.

## Deterministic timer handoff

`deploy/public-ingest-schedule.json` binds:

- `rozkalns-weather-public-ingest.timer`;
- `rozkalns-weather-public-ingest.service`;
- `OnCalendar=*:0/30`;
- `Persistent=true` catch-up semantics;
- bounded 60-second randomized delay and accuracy;
- no-overlap semantics plus the application ingest lock;
- schedule installation/enablement only after corpus integrity succeeds.

WeatherNext scheduling remains disabled and separately gated. This weather source issue never installs/enables/restarts a real systemd unit.

## Readiness and post-rollout evidence

`GET /ready`, `GET /api/readiness` and `rozkalns-weather readiness` expose schema version 1 readiness. They report:

- runtime mode;
- database schema state and missing required tables;
- persistent storage class/writability without exposing its host path;
- public-provider last known state without performing network calls;
- WeatherNext configured/pending state as non-required for public runtime;
- home configured state as non-required;
- explicit privacy flags for coordinates, credentials and DB path.

Public provider `error` or `adapter_ready_not_ingested` is visible but does not make application runtime readiness false. Runtime readiness is based on the local application/storage/schema contract; provider network health remains an independently visible operational signal.

A future trusted executor may pipe sanitized evidence to `rozkalns-weather rollout-evidence-validate`. Passing evidence must bind the deployed exact SHA, target/operation/runtime mode, HTTP 200 for `/health`, `/ready` and `/api/health/providers`, ready schema, persistent SQLite + retained `weather_data`, required provider-state presence and corpus integrity. WeatherNext remains non-required and non-fabricated.

The evidence validator rejects home-coordinate, credential, raw-log, database-path, host-path or environment fields and host-private path strings. Raw private logs are never part of the GitHub receipt.

## Current `RPi5_main` source interface

`RPi5_main` source integration already exists and must be refreshed before LIVE rather than re-created here:

- Issue #408 / PR #409 registered static operation `rozkalns-weather.public-runtime-release.v1` and a dedicated execution-disabled weather adapter;
- Issue #410 / PR #415 added deterministic first-bootstrap composition for application release, volume ensure, schema init, readiness, optional smoke, bounded DWD truth/forecast backfill, integrity and recurring schedule handoff;
- Issue #432 / PR #433 added the source-only Weather LIVE-AUTH/READY pre-activation composition, reusing the owner authorization/queue/replay protocol without enabling execution;
- Issue #435 / PR #436 added the capability-specific trusted host-wiring/helper source bridge and whole-preactivation-envelope binding;
- Issue #455 added the capability-specific privileged helper install/activation bridge and the successor trusted checkout `RPi5_main-weather-public-runtime-install-trusted`; the earlier `RPi5_main-weather-public-runtime-trusted` checkout is retained only as historical evidence and is not current mutation authority;
- Issue #454 / PR #460 added the source-ready Composite operator, issue-number-only caller surface, durable consume-before-first-mutation semantics, JIT pre/post-consume revalidation and fixed one-shot stage launcher.

These are source interfaces, not deployment proof. At the 2026-09-10 reconciliation snapshot, `RPi5_main/main=6711ef153ae6b8636ea0c77fd4224ea2dd3d8d3a` and its exact-main `Validate` run `34514438900` succeeded. The operator contract is `SOURCE_READY_HOST_NOT_INSTALLED`: Weather remains `STRICT`, `ordinary_live_all_eligible=false`, operator/helper installation and invocation remain disabled, and source merge proves neither host readiness nor deployment. This weather repo does not mutate or activate `RPi5_main`.

`deploy/rpi5-source-binding.json` records this source-only reconciliation. It also records that `ops-workflows#46` remains eligibility for Weather candidate `52d3fd0ff946d3d5a0e1379f6c4362bf834a1aa9`; any older `RPi5_main` SHA embedded in that queue issue is a point-in-time queue snapshot, not current RPi5 authority.

A future exact LIVE envelope must freshly bind the trusted host and target alias, exact merged weather SHA and exact-SHA CI, current `RPi5_main` SHA, sanitized current runtime baseline, exact reviewed host-wiring/helper identities, whole preactivation SHA-256, bounded dates/models/run hours and WMO `10416`, recovery decision, exact mutation budgets and postconditions. It must not accept generic shell/path/argv/environment authority from GitHub text.

Database schema initialization, historical corpus backfill, backup/restore, private home configuration, Google Cloud/WeatherNext credentials, Cloudflare/network changes and package/root permission changes remain separate mutation classes. They must not be smuggled into an ordinary application-release adapter.

## Fail-closed stage matrix

`deploy/rollout-readiness.json` freezes stage-specific failure behavior for application release, volume ensure, schema init, truth backfill, forecast backfill, integrity and schedule activation. Once a future mutation starts, unexpected state means STOP with minimum sufficient read-only evidence. There is no undeclared retry, rollback, automatic repair, cleanup, restore or alternate scheduler activation.

## Future exact LIVE gate fields

Before the first live mutation, freshly bind:

- exact trusted host and target alias;
- reviewed **merged** weather SHA and exact-SHA required CI;
- current `RPi5_main` SHA and exact static operation identity;
- current sanitized runtime baseline;
- exact reviewed host-wiring/helper identities and whole preactivation SHA-256;
- bounded start/end dates, exact three-model set, UTC run hours and WMO `10416` truth;
- recovery decision;
- exact mutation classes and budgets;
- health/readiness/provider/schema/storage/corpus-integrity verification postconditions;
- application rollback semantics, explicitly excluding implicit SQLite restore/delete/cleanup.

Any drift after binding must be handled under current authorization/fail-closed rules. Read-only preflight does not consume a later LIVE authorization; the first selected runtime mutation does.

## Warning and privacy invariants

DWD remains the authoritative severe-weather warning source in Germany. WeatherNext is research output only. Exact home coordinates, credentials, `.env`, private host paths and runtime logs must not enter GitHub evidence.
