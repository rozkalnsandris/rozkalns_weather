# Production public corpus bootstrap contract

Issue #31 freezes source behavior for a later, separately authorized production SQLite bootstrap. This document does not authorize a database, corpus, host or runtime mutation.

## Frozen first-bootstrap scope

- benchmark location: `station_10416`; DWD truth station: WMO `10416`;
- common archive start: `2026-04-02`;
- first rollout source window: `2026-04-02..2026-09-10` (162 inclusive days, hard maximum 180);
- forecast models: exactly `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- forecast cycles: exactly `00/06/12/18 UTC`;
- DWD truth: exact 14-day chunks, final chunk shortened only at the requested end date.

`deploy/production-public-corpus-bootstrap.json` is the machine contract. `build_production_bootstrap_plan()` produces a deterministic fingerprint over source SHA, bounds, station, models, run hours and owner recovery decision. Source planning grants no production-data authority.

## Schema and backfill separation

Schema initialization is an explicit mutation: `rozkalns-weather init-database`. Historical backfill must start only after the required schema already exists and is ready. `python -m rozkalns_weather.backfill` must not implicitly initialize or migrate a database.

This means an old/incomplete production schema is a STOP condition. A future schema migration must be separately reviewed and authorized; a backfill command may not silently turn into a migration.

## Checkpoint and resume semantics

Checkpoint files use schema version 1 and atomic temporary-file replacement. Completed entries must be unique and form the exact ordered prefix of the requested truth chunks or forecast runs. Skipping ahead, unknown entries, duplicate checkpoint entries or a changed bootstrap fingerprint fail closed.

A crash after a database insert but before checkpoint publication is treated as an interrupted checkpoint. Same-payload forecast insertion remains idempotent through immutable payload-hash dedupe, but source validation does not silently repair or advance the checkpoint. Fresh resume evidence is required. If a repeated upstream run changes payload and creates a revision, production bootstrap integrity is blocked as revision drift rather than rewriting history.

## Integrity and destructive behavior

Completion requires zero missing runs, zero unexpected runs and zero revision drift for each frozen deterministic model, plus the complete WMO 10416 truth chunk prefix. Immutable forecast snapshots remain mandatory.

There is no automatic delete, restore, cleanup, repair or SQLite rollback. Backup/restore is a separate mutation class. Application rollback never implies corpus rollback.

## Later owner gate

A future production bootstrap authorization must bind the reviewed merged Weather SHA and exact-SHA CI, exact production SQLite target, start/end dates, station, all three models, `00/06/12/18 UTC`, recovery decision, schema-init/backfill mutation classes, checkpoint fingerprint, verification postconditions and failure semantics. Any runtime/host/Docker/systemd mutation remains separately governed by the trusted `RPi5_main` boundary.
