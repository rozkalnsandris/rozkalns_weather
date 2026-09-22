# Implementation status

Status reconciled by #167 after the completed public-only UI-FIRST milestone on 2026-09-21.

## Current outcome

The first real, usable public-only Weather Web UI is LIVE and verified.

Current authoritative project state:

- master #136 is completed;
- public data/bootstrap gate #148 is completed;
- ordinary application releases use standing shared SIMPLE-DEPLOY v1;
- production schema/public corpus are present and integrity passes;
- recurring public ingest is enabled and active;
- public-only Overview / Models / Accuracy / Warnings-Radar are operational;
- current measured benchmark is `station_05480` / DWD CDC 05480;
- fixed current common benchmark window is `2026-08-13..2026-08-26`;
- `station_10416` is legacy/MOSMIX compatibility only;
- DWD remains the official severe-weather warning authority.

Mutable deployed SHA, image digest, provider freshness and runtime counts belong in fresh controller/runtime receipts (#9), not as static authority in this file.

## Public benchmark implementation

Current benchmark identity is `station_05480` with DWD CDC truth and co-located deterministic model forecasts.

Implemented:

- DWD CDC historical/recent observation transport for the measured benchmark;
- ICON-D2 / ECMWF IFS / ECMWF AIFS exact-run provenance;
- immutable forecast snapshots, idempotency/revision checks and provider failure isolation;
- cycle-aware IFS horizon/lead-bucket expectations;
- corpus stats, integrity and read-only corpus reporting;
- MAE/RMSE/bias, lead buckets and model-version dimensions;
- public ensemble verification primitives where genuine member input exists;
- provider freshness/ingest-health observability;
- privacy-safe current/forecast/verification/safety API surfaces.

The old `2026-04-02..2026-09-10` production-bootstrap attempt and 10416 truth path remain historical evidence. They are not the current benchmark readiness contract and are not destructively rewritten.

## Deployment status — SIMPLE-DEPLOY v1

Weather is a consumer/canary of shared SIMPLE-DEPLOY, not the deployment platform owner.

Current ordinary release path is active:

```text
AUTO-RUN FULL
-> exact-head CI/review readiness
-> guarded merge
-> shared SIMPLE-DEPLOY build/publish/promotion
-> immutable GHCR digest
-> generic RPi5 pull reconciler
-> application replacement
-> /health + /ready verification
-> LIVE
```

Completed deployment milestones include:

- Weather SIMPLE-DEPLOY source adoption;
- one-time RPi5 generic-deployer/target cutover;
- first standing `AUTO_DEPLOY_SAFE` release proof (#146);
- repeated ordinary post-cutover releases through the same reviewed path;
- production public corpus bootstrap and recurring-ingest activation under separate exact gates.

Historical Weather broker/operator/queue/JIT/Composite assets are retained only as audit/regression evidence and are superseded for ordinary application releases.

Ordinary source merge never authorizes production SQLite/corpus writes, private-provider access, secrets/permissions, Cloudflare/network, private home configuration or arbitrary host/systemd/root operations.

## Runtime/data status

Production runtime is `public-only`:

- `DATABASE_INIT_MODE=require-existing` prevents app startup from implicitly creating/migrating production schema;
- persistent `weather_data` is retained across ordinary application replacement;
- recurring public ingest runs separately from app deployment;
- provider failures remain isolated and visible through health/freshness state;
- DWD Warnings/Radar remain distinct from experimental model output.

The DWD measured-current freshness contract is pinned to canonical `station_05480` ingest provenance. A successful fetch/write cycle is only ingest success: freshness is classified from the latest canonical observed-at timestamp as `FRESH`, `SOURCE_DATA_LAGGING`, `SOURCE_DATA_STALE`, or `SOURCE_TIME_MISSING`. Empty/no-new results never fabricate a source timestamp, and legacy `station_10416` evidence must not satisfy current DWD measured-current health.

One isolated ECMWF IFS upstream/transport failure was observed in the #167 audit. Provider failures remain follow-up signals rather than architecture blockers and source time must never be fabricated.

## WeatherNext 3 current continuation

WeatherNext 3 remains first-class `primary_research` but real private access is not yet executed.

Completed source foundations:

- BigQuery 0.05° station-head / 0.1° surface contracts;
- `mean/p10/p25/p50/p75/p90` statistics;
- init/retrieval/valid/lead/model-version/source-surface provenance;
- dry-run/cost guardrails and sanitized evidence contracts;
- sustained-collection and version-evolution source planning.

Current next sequence:

1. #168 — migrate first-access canary source contract from legacy `station_10416` to canonical `station_05480`;
2. #122 — later explicit owner-authorized private read-only BigQuery first access after #168 and fresh binding;
3. first real WeatherNext snapshot — separate production-data authorization;
4. sustained private collection and measured evaluation only after defensible real corpus exists.

WeatherNext real values are never fabricated. Private Google identity, credentials and exact home coordinates never belong in GitHub evidence.

## Open source-quality / research backlog

Material future contracts have been reconciled to current 05480 benchmark semantics:

- #78 — DWD observation finality/revision-window contract;
- #83 — end-to-end value provenance trace;
- #100 — spatial collocation/grid-identity provenance;
- #76 — cross-artifact privacy leakage scanner.

Issue #1 is now the remaining WeatherNext-private research umbrella. Issue #122 is intentionally blocked by source migration #168 rather than silently executing against legacy 10416.

## Historical source lineage

Closed issues/PRs and Git history preserve point-in-time source and rollout evidence, including earlier WMO 10416 benchmark contracts, old public bootstrap attempts and Weather-specific control-plane work.

Those historical statements are not current runtime authority. Current state must be reconstructed from:

1. `AGENTS.md` and repo-local contracts;
2. controller issue #9;
3. current `main` and exact-head CI;
4. fresh RPi5 read-only evidence when runtime state matters.

## Safety invariants

- DWD is the authoritative severe-weather warning source.
- WeatherNext/model output is research forecast output, never an official warning.
- No exact home address, `HOME_LAT`, `HOME_LON`, `.env`, credentials/tokens or private runtime logs in GitHub.
- Provider provenance and immutable snapshot history must remain reproducible.
- Production data/private access/host/network mutations require the exact separate owner authority defined by current contracts.
