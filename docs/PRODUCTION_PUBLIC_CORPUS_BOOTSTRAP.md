# Production public corpus bootstrap

## Current source state — issue #159

Issue #159 replaces the **common production verification window**, not the historical corpus.

Canonical source decision: `deploy/exact-run-common-window.json`.

The selected fixed, non-rolling common window is:

- `2026-08-13..2026-08-26` (14 inclusive days);
- DWD CDC truth station `05480` / `station_05480` (`Werl`);
- deterministic models exactly `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- exact cycles `00/06/12/18 UTC`;
- `56` expected exact runs per model;
- exact-init/full-horizon semantics through Open-Meteo Single Runs;
- checkpoint namespace `fixed-window-20260813-20260826-v1`.

The source state is `SOURCE_READY_REQUIRES_EXACT_LIVE_DATA_AUTHORITY`. Source readiness is **not** production write authority.

## Why the window changed

Issue #157 proved that the old `2026-04-02..2026-09-10` window could not be completed defensibly because exact historical ICON-D2 runs had aged out of the known public exact-run surfaces. The #157 machine decision remains immutable audit evidence in `deploy/icon-d2-exact-run-transport-decision.json`.

Issue #159 deliberately selected a newer fixed window rather than weakening verification methodology. Historical Forecast, Previous Runs, rolling timeseries, missing-run acceptance, skip-ahead, imputation, model substitution and provider relabelling remain forbidden for the exact-run corpus.

## Public exact-run evidence

The candidate window was probed at the public DWD station coordinates from `deploy/dwd-cdc-05480-benchmark.json`.

Primary exhaustive probe run `35614910970` checked all `168` exact init/model combinations with the complete adapter variable set and `24` start/end full-horizon boundaries. It returned:

- `155/168` required-variable exact-run PASS;
- `23/24` full-horizon boundary PASS;
- every non-PASS result was an SSL handshake transport timeout;
- zero API/model-unavailable or truncated-horizon verdicts.

A targeted transport-only gap-closure run `35616166217` then rechecked only those 14 transport gaps. It returned `14/14 PASS`. API/model errors were never retried. Its evidence fingerprint is:

`aa8bd30174a660ab5ae38f5202925eb2622521a5bf52485208fc499e8284bbf2`

Combined evidence therefore closes `168/168` exact required-variable checks and `24/24` full-horizon boundary checks separately across ICON-D2, IFS and AIFS.

Open-Meteo Single Runs remains the canonical transport because `run=` identifies one model initialization and the surface exposes that run's forecast horizon. Public AWS `data_run` retention is approximately three months; on the 2026-09-21 evidence date the oldest selected init (`2026-08-13`) was 39 days old, leaving a material margin from the retention edge. Retention was not inferred across models: every model was probed separately.

## DWD CDC truth

Truth remains direct DWD CDC Open Data, station ID `05480`. Source coverage for the required variables is verified for `2026-04-02..2026-09-10`; the new common window is fully inside that truth envelope. The latest requested AIFS horizon ends at `2026-09-10T18:00:00Z`.

Required mappings remain:

| DWD CDC family | archive code | CSV column | canonical variable |
| --- | --- | --- | --- |
| air temperature | `TU` | `TT_TU` | `temperature_2m` |
| relative humidity | `TU` | `RF_TU` | `relative_humidity_2m` |
| dew point | `TD` | `TD` | `dew_point_2m` |
| pressure | `P0` | `P` | `pressure_msl` |
| wind | `FF` | `F` | `wind_speed_10m` |
| gust | `FX` | `FX_911` | `wind_gust_10m` |
| precipitation | `RR` | `R1` | `precipitation_1h` |
| cloudiness | `N` | `V_N` | `cloud_cover` |

DWD `-999` remains missing, never zero or imputed. Negative cloud special states remain omitted.

## Preserved historical production evidence

Nothing from the previous partial bootstrap is deleted, rewritten, relabelled or rolled back:

- DWD CDC truth: `30,963` observations, old `12/12` chunks complete;
- ICON-D2 old ordered prefix: `279/648` runs;
- last old completed ICON-D2 init: `2026-06-10T12:00:00Z`;
- old next required init: `2026-06-10T18:00:00Z`;
- IFS/AIFS old bootstrap: not started.

Those rows remain historical audit evidence. They do not count toward fixed-window common readiness merely because they exist. The old checkpoint and pre-#159 bootstrap fingerprints are not reusable for the new namespace.

## Source plan and corpus report

The only valid production bootstrap identity is the exact fixed window:

```bash
rozkalns-weather production-bootstrap-plan \
  --source-sha <MERGED_SHA> \
  --start 2026-08-13 \
  --end 2026-08-26 \
  --recovery-decision verified_backup_available
```

The plan rejects the old window, a rolling window, and partial substitutes. A new `bootstrap_fingerprint` is derived from the exact source SHA, fixed dates, station/model/run-hour scope, transport decision and checkpoint namespace.

For production readiness, run the existing read-only corpus reporter against exactly the selected common window:

```bash
rozkalns-weather corpus-report --start 2026-08-13 --end 2026-08-26
```

The reporter remains usable for historical audit outside that window, but historical rows outside `2026-08-13..2026-08-26` are not part of the new common-readiness decision.

## Authority boundary

Issue #159 does not authorize:

- production SQLite/corpus/checkpoint writes or resume;
- schema init/migration;
- deleting or rewriting old rows;
- RPi5 Docker/systemd/timer mutation;
- recurring ingest activation;
- WeatherNext/private-home data;
- Cloudflare/network/secrets/permissions;
- restore/cleanup/rollback.

After merge, parent #148 requires a fresh read-only production preflight bound to the merged source SHA and the new bootstrap fingerprint. Any bounded corpus write then requires a new exact LIVE/DATA authorization. Recurring ingest remains a later separate host gate after fixed-window corpus integrity is PASS.
