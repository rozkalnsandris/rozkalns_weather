# RPi5 public-only runtime handoff — SIMPLE-DEPLOY v1

Current ordinary application-release handoff uses shared SIMPLE-DEPLOY v1. Weather consumer config is `.simple-deploy.json`, pinned shared revision is `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`, and generic trusted host source is `RPi5_main@ff20fcf64ba62c95e5f15eeb481c3c66bb5c9708`. Target `rozkalns-weather-public-rpi5` remains inactive until one separate exact LIVE cutover installs/enables the generic deployer and binds the fixed target.

The generic deployer, not Weather GitHub prose, owns fixed host authority: it resolves the discovery pointer, freezes one immutable digest, pulls/updates only the allowlisted `weather` service, verifies `/health` and `/ready`, and records an exact receipt. `weather_data` is retained and `DATABASE_INIT_MODE=require-existing` prevents application replacement from becoming a schema/data operation.

The old Weather-specific broker/operator/`ops-workflows#46` queue/JIT/Composite flow is **legacy/superseded for ordinary application releases**. Its source files are retained only as audit/regression evidence and do not gate SIMPLE-DEPLOY.

## Runtime mode and safety

The first public runtime uses:

- `WEATHER_RUNTIME_MODE=public-only`;
- `DATABASE_INIT_MODE=require-existing`;
- DWD/Bright Sky/Open-Meteo public providers;
- DWD WMO `10416` as measured benchmark truth;
- no required `HOME_LAT` / `HOME_LON`;
- no required Google Cloud or WeatherNext credentials.

WeatherNext 3 remains first-class `primary_research`, but `access_pending` is non-blocking for this runtime class and no WeatherNext values are fabricated. DWD is the severe-weather warning authority.

## Fixed package surface

Canonical source contracts include:

- `Dockerfile`;
- `deploy/docker-compose.public.yml`;
- `deploy/runtime-descriptor.json`;
- `deploy/rollout-readiness.json`;
- `deploy/rpi5-source-binding.json`;
- `deploy/first-public-rollout-preflight.json`;
- `deploy/production-public-corpus-bootstrap.json`;
- `deploy/public-ingest-schedule.json`.

The application service does not implicitly initialize schema, backfill history, restore/delete corpus or enable the recurring timer.

## Source preflight versus runtime proof

`rozkalns-weather rollout-preflight` validates the reviewed source checkout without network calls or runtime mutation. It validates fixed package identities, an exact 40-character source SHA form, bounded dates, WMO `10416`, exact `icon_d2/ecmwf_ifs/ecmwf_aifs`, exact UTC run hours `0,6,12,18`, ordered checkpoints and one explicit recovery decision.

It deliberately cannot prove:

- current GitHub `main` membership;
- current exact-SHA CI;
- current queue state;
- current operator installation;
- current runtime baseline;
- current deployment/readiness.

Those are fresh JIT inputs.

## Persistent corpus and rollout ordering

The persistent storage class is Docker named volume `weather_data`, mounted at `/app/data`; canonical in-container DB URL is `sqlite:///data/weather.db`.

The fixed first-public sequence is:

1. `volume_ensure`;
2. `explicit_schema_init`;
3. `readiness_check`;
4. `public_smoke_read_only`;
5. `bounded_dwd_truth_backfill`;
6. `bounded_forecast_backfill`;
7. `corpus_integrity_check`;
8. `enable_recurring_public_ingest` last.

Resume accepts only an exact completed prefix. Hidden retry, implicit stage advancement, automatic restore/delete/cleanup and destructive SQLite rollback remain forbidden.

## Recovery semantics

Before production corpus writes, one explicit recovery decision must be bound:

- `verified_backup_available`; or
- `owner_accepts_proceeding_without_prewrite_backup`.

Backup creation/restore/delete are separate mutation classes. Application rollback does not imply SQLite rollback.

## Legacy source/control-plane reconciliation — superseded for ordinary application releases

Issue `#140` supersedes the stale v7 handoff after the Weather-v9 operator/control-plane recovery completed.

Point-in-time source anchors at reconciliation:

- Weather `main=9e903b0e1d129856c4b1533b48487b7f5c36737d`;
- `RPi5_main/main=84e129909831bd8111c4f4c1f6618b7fff2a803b`;
- `ops-workflows#46` blocked on Weather source-handoff reconciliation.

These anchors are **not** runtime proof. `deploy/rpi5-source-binding.json` therefore records source/control-plane lineage and proof requirements, but does not contain a current host observation or stale v7 next-owner gate.

`deploy/rollout-readiness.json` likewise does not encode mutable current-host assertions such as `operator_host_installed=false`. The v1 source-package validator still has compatibility sentinel fields in `deploy/rpi5-source-binding.json`; they are explicitly marked non-authoritative and are not current host observations or capability decisions.

## Legacy first-public JIT gate — superseded for ordinary application releases

`deploy/first-public-rollout-preflight.json` plus `rozkalns-weather rollout-live-preflight-validate` require fresh:

- exact current Weather SHA + exact-SHA CI;
- exact current `RPi5_main` SHA + exact-SHA CI;
- matching `ops-workflows#46` `OPEN_READY` queue;
- trusted host/target identity;
- operator installation proof;
- sanitized runtime baseline with exact token match;
- reviewed contract identities;
- bounded bootstrap inputs;
- explicit recovery decision;
- exact mutation/read-only budgets;
- owner/TTL/raw-body/replay authorization evidence.

The validator returns only `PASS` or explicit `BLOCKED` reasons and does not create/consume LIVE authority or mutate runtime.

A retained `next_owner_live_gate` node in the v1 preflight JSON exists only for schema compatibility with the current source-package validator. It is marked unavailable, historical and superseded; it is **not** the current gate.

## Legacy post-merge control-plane sequence — superseded for ordinary application releases

After Issue `#140` merges:

1. resolve the final merged Weather SHA;
2. reconcile `ops-workflows#46` to that exact SHA under its own rules;
3. refresh Weather/RPi5 exact-SHA CI;
4. collect fresh sanitized operator-installation proof and runtime baseline;
5. run the JIT preflight;
6. only after JIT `PASS`, request a new bounded Composite STRICT LIVE authorization.

Queue READY remains eligibility-only. Source merge, queue READY and JIT PASS do not themselves authorize mutation.

## LIVE mutation boundary

Production schema initialization, DWD truth/forecast corpus backfill, Docker/systemd changes, timer enablement, backup/restore, private home configuration, WeatherNext/Google Cloud credentials and Cloudflare/network changes require separate explicit owner authority.

After the first mutation starts, unexpected state follows fail-closed semantics: collect minimum sufficient read-only evidence and STOP; no undeclared retry, rollback, cleanup or alternate mutation path.

## Post-rollout evidence

Successful rollout evidence must prove, without private data:

- deployed exact authorized Weather SHA;
- HTTP 200 for `/health`, `/ready` and `/api/health/providers`;
- ready schema and persistent SQLite storage;
- retained `weather_data`;
- required provider states;
- corpus integrity;
- WeatherNext optional/non-fabricated status.

The evidence validator rejects coordinates, credentials, raw logs, DB paths, host-private paths and environment fields.

## Warning and privacy invariants

DWD remains authoritative for severe-weather warnings in Germany. WeatherNext remains research output only.

Exact home address/coordinates, credentials, `.env`, private host paths and raw runtime logs must not be committed to GitHub.
