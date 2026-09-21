# Production public corpus bootstrap

## Current benchmark decision

Issue #155 supersedes WMO `10416` **only for new measured public verification**. The canonical benchmark is now the public DWD CDC station `05480` (`Werl`) at source location identity `station_05480`. The station coordinates stored in source are public DWD station metadata; they are not the private home point.

The previous `deploy/dwd-10416-historical-truth-decision.json` remains immutable legacy audit evidence for why the old production truth path failed closed. Existing `station_10416` rows are not rewritten, migrated, deleted or silently relabelled. MOSMIX `10416` may remain a separate legacy/current-reference baseline because this issue does not infer an unproven WMO/MOSMIX mapping for CDC `05480`.

Canonical station policy is `deploy/dwd-cdc-05480-benchmark.json`.

## Frozen first window

The reviewed source envelope remains:

- window: `2026-04-02..2026-09-10` (162 inclusive days; hard cap 180);
- benchmark location: `station_05480`;
- DWD CDC `Stations_id=05480` only;
- deterministic forecast models: exactly `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- init cycles: exactly `00/06/12/18 UTC`;
- truth chunks: ordered 14-day chunks;
- checkpoint/resume: exact ordered prefix only;
- recovery decision: `verified_backup_available` or `owner_accepts_proceeding_without_prewrite_backup`.

The plan is source-ready only for the frozen window. Before a later LIVE/data write, the DWD CDC source URLs/product coverage must be freshly revalidated; source readiness is not runtime or production-data authority.

## DWD CDC truth transport

Truth comes directly from DWD CDC Open Data, not Bright Sky and not a nearest-station fallback. The dedicated adapter requires exact station ID `05480` in every parsed row and preserves product/column/source URL/retrieval provenance.

Required truth semantics and native mappings are:

| DWD CDC family | archive code | CSV column | canonical variable | handling |
| --- | --- | --- | --- | --- |
| `air_temperature` | `TU` | `TT_TU` | `temperature_2m` | °C |
| `air_temperature` | `TU` | `RF_TU` | `relative_humidity_2m` | % |
| `dew_point` | `TD` | `TD` | `dew_point_2m` | °C |
| `pressure` | `P0` | `P` | `pressure_msl` | hPa; **P is sea-level pressure**; `P0` is not mapped to MSL |
| `wind` | `FF` | `F` | `wind_speed_10m` | m/s |
| `extreme_wind` | `FX` | `FX_911` | `wind_gust_10m` | m/s |
| `precipitation` | `RR` | `R1` | `precipitation_1h` | mm, 60-minute accumulation |
| `cloudiness` | `N` | `V_N` | `cloud_cover` | native eighths; convert `value * 12.5` to % |

DWD missing sentinel values such as `-999` are omitted. They are never converted to zero and are never imputed. Negative cloud-cover special states are omitted rather than treated as physical cloud percentage.

## Forecast/truth co-location

All new measured deterministic forecast backfill for ICON-D2, ECMWF IFS and ECMWF AIFS uses the exact public coordinates of `station_05480` and stores the run under the same `location_id=station_05480` as DWD truth. The production plan, corpus report, benchmark export and verification drilldown fail closed on location/station mismatch. Runtime nearest-station selection and station substitution are not allowed.

`home` remains private/runtime-only and is not changed by this decision.

## Source commands

Source-only planning remains network/DB-free:

```bash
rozkalns-weather production-bootstrap-plan \
  --source-sha <MERGED_SHA> \
  --start 2026-04-02 \
  --end 2026-09-10 \
  --recovery-decision verified_backup_available
```

The backfill executable is still separately gated because it writes SQLite/checkpoints and performs provider reads:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<path> truth \
  --start 2026-04-02 --end 2026-09-10 \
  --checkpoint <path> --chunk-days 14

python -m rozkalns_weather.backfill --database-url sqlite:///<path> forecast \
  --model icon_d2 --start 2026-04-02 --end 2026-09-10 \
  --run-hours 0,6,12,18 --checkpoint <path>
```

Equivalent forecast commands apply to `ecmwf_ifs` and `ecmwf_aifs`. Dry-run does not create the new location row. An actual authorized backfill creates/ensures the public benchmark location immediately before the first write; app startup does not silently create it in production.

## Integrity and fail-closed rules

Completion requires:

- exact station/location identity on truth;
- exact benchmark location on each deterministic model run;
- all expected runs present and no unexpected runs;
- required lead-bucket coverage;
- zero revision drift / conflicting immutable payload identity;
- DWD temperature continuity for matched valid times;
- required provenance fields present;
- checkpoint and database progress consistent.

After any future authorized production mutation begins, error, timeout, DWD product drift, unexpected station ID, changed source/head, checkpoint ambiguity, conflicting truth revision or integrity regression requires STOP. No undeclared retry, rollback, cleanup, delete, restore, station substitution or alternate provider is authorized.

## Authority boundary

Issue #155 is source-only. Its merge **does not** authorize:

- production SQLite/corpus/checkpoint writes;
- schema init/migration;
- backfill execution;
- recurring ingest installation/enablement;
- RPi5/Docker/systemd mutation;
- WeatherNext/private-home activation;
- Cloudflare/network/secrets/permissions.

Parent #148 must cross a new exact LIVE/DATA owner gate before the frozen production bootstrap is executed. Recurring public ingest is enabled only after post-bootstrap corpus integrity passes.
