# Production public corpus bootstrap contract

This source contract prepares the first public corpus but **does not authorize any production SQLite, corpus, checkpoint, host or runtime mutation**.

## Benchmark truth policy — issue #153

The approved measured benchmark is DWD Climate Data Center station **05480, Werl**. The old WMO `10416` / `station_10416` identity is retained only for legacy provenance and the separate MOSMIX local baseline; no CDC↔WMO mapping is inferred.

DWD remains the sole observation-truth authority. The measured benchmark variables are exactly:

- `temperature_2m` from CDC hourly air-temperature product `TT_TU` (`degC`);
- `precipitation_1h` from CDC hourly precipitation product `R1` (`mm`, hourly sum);
- `wind_gust_10m` from CDC hourly extreme-wind product `FX_911` (`m/s`).

Station identity is pinned to CDC `Stations_id=05480`. Missing value `-999` is omitted and never imputed. Nearest-station fallback, station substitution, synthetic observations and third-party truth are forbidden.

Authoritative DWD evidence reviewed for #153 shows station 05480 in both `historical/` and `recent/` product families for all three measured variables. The source implementation pins the currently reviewed historical archives and the station-specific `*_05480_akt.zip` recent archives. `historical/` is versioned and updated annually; `recent/` is rolling and updated daily.

## Frozen first-bootstrap scope

- benchmark location: `station_dwd_cdc_05480`;
- DWD truth station: CDC `05480` (Werl);
- common archive start: `2026-04-02`;
- first rollout window: `2026-04-02..2026-09-10` (162 inclusive days, hard maximum 180);
- forecast models: exactly `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- forecast cycles: exactly `00/06/12/18 UTC`;
- truth chunks: 14 days, with the final chunk shortened only at the requested end date;
- source planning and dry-run remain network/DB independent;
- `production_data_authority_granted=false` remains mandatory.

`deploy/production-public-corpus-bootstrap.json` is the machine contract. `build_production_bootstrap_plan()` fingerprints source SHA, bounds, benchmark identity, required truth variables, models, run hours, DWD CDC transport state and explicit recovery decision.

## Schema and backfill separation

Schema initialization remains an explicit write operation: `rozkalns-weather init-database`. Historical backfill requires an already-ready schema and the canonical public benchmark location. `python -m rozkalns_weather.backfill` never implicitly initializes or migrates production SQLite.

Forecast backfill uses the same public Werl reference coordinates as truth, so measured verification cannot silently join a forecast point for one station to observations from another station. The legacy `station_10416` row/data is not deleted, rewritten or migrated.

## DWD CDC transport

The fixture-driven parser enforces:

- exact `STATIONS_ID=05480`;
- UTC `MESS_DATUM` (`YYYYMMDDHH`);
- expected DWD CDC product column per variable;
- exact units used by project semantics;
- DWD provenance, product family/code, archive URL and quality-level metadata;
- missing-value omission without imputation.

For the frozen 2026 production window the rolling `recent` archives provide the observations. Versioned historical archives remain supported for older requested dates inside their reviewed station coverage.

## Checkpoint, integrity and recovery

Checkpoint schema remains version 1 with atomic replacement. Entries must be unique and the exact ordered prefix. A changed bootstrap fingerprint, station identity mismatch, skip-ahead, duplicate checkpoint, database-ahead ambiguity, revision drift or unexpected run blocks the operation.

Completion requires zero missing/unexpected/revised deterministic runs plus the complete pinned DWD truth prefix. No automatic retry, delete, restore, cleanup or repair is authorized.

## Authority boundary

A `SOURCE_READY` plan means only that the source contract is no longer blocked by the old WMO10416/Bright Sky transport assumption. It is **not** data-write authority.

Before any production corpus write, parent #148 requires a fresh exact LIVE/DATA authorization bound to the merged Weather SHA, exact production target, window, station `05480`, models/cycles, recovery decision, plan fingerprint, postconditions and fail-closed semantics. RPi5/systemd recurring-ingest activation remains a later separate host gate and stays enable-last after corpus integrity PASS.
