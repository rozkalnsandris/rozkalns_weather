# Production public corpus bootstrap

## Current source state — issue #157

The production public corpus bootstrap is **source-blocked** on deterministic ICON-D2 exact-run archive capability.

Canonical machine decision: `deploy/icon-d2-exact-run-transport-decision.json`.

Current blocker:

```text
NO_COMPLETE_ICON_D2_EXACT_RUN_ARCHIVE_TRANSPORT
```

This is deliberately stricter than treating an upstream transport error as a transient retry condition. The frozen corpus requires every exact model initialization for `00/06/12/18 UTC`; missing runs may not be skipped, imputed, relabelled, or replaced by another model/provider.

The benchmark decision from issue #155 remains unchanged:

- public DWD CDC station `05480` (`Werl`);
- source location identity `station_05480`;
- frozen first window `2026-04-02..2026-09-10`;
- deterministic models exactly `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- exact public benchmark coordinates from DWD station metadata;
- no private home coordinates in the public corpus.

## Preserved production prefix

Parent LIVE gate #148 already wrote a partial but internally consistent corpus before the upstream ICON-D2 gap was proven:

- DWD CDC truth: `30,963` observations, `12/12` ordered chunks complete;
- ICON-D2 exact-run prefix: `279/648` runs;
- last completed ICON-D2 init: `2026-06-10T12:00:00Z`;
- next required ICON-D2 init: `2026-06-10T18:00:00Z`;
- ECMWF IFS and AIFS bootstrap were not started.

That prefix is evidence, not permission to continue. It must be preserved without cleanup, rollback, checkpoint editing, or skip-ahead.

## Why the source gate is blocked

Open-Meteo Single Runs remains the canonical public transport because it accepts an explicit `run=` and preserves one model initialization rather than constructing a stitched historical series.

Fresh read-only evidence showed that the exact next ICON-D2 run is unavailable through that transport. The upstream service can expose unavailable runs in two different shapes:

- HTTP `200` with a body containing `modelRunUnavailable(...)` even though the response declares JSON;
- HTTP `400` JSON with `The requested model run is not available`.

`rozkalns_weather.providers.open_meteo` normalizes both shapes to the stable source reason code:

```text
OPEN_METEO_MODEL_RUN_UNAVAILABLE
```

Unrelated malformed/non-JSON responses use a different reason code and are not silently interpreted as a missing model run.

## Alternate transport decision

No complete public exact-run alternate transport is currently proven for the entire frozen window.

| Candidate | Decision | Reason |
| --- | --- | --- |
| Open-Meteo Historical Forecast API | rejected | combines early forecast hours from successive runs; not one exact init |
| Open-Meteo Previous Runs API | rejected | lead-offset surface; not a complete exact-init full-horizon run archive |
| Open-Meteo AWS `data_run` | rejected for frozen window | public exact-run objects are retained for about three months, insufficient for the full April–September recovery window at the time of issue #157 |
| Open-Meteo AWS `data_spatial` | rejected for frozen window | public retention is seven days |
| Open-Meteo rolling timeseries | rejected | long-term storage does not preserve individual run identity |
| DWD operational ICON-D2 Open Data | unproven for frozen window | current operational run directories do not prove a complete public historical exact-run archive for the full frozen window |

Evidence basis is recorded in the machine decision contract and issue #157. A future source change may replace the blocker only after it proves complete historical exact-init coverage, required variables/units, `station_05480` extraction, and transport provenance.

## DWD CDC truth transport

Truth remains direct DWD CDC Open Data for exact station ID `05480`; issue #157 does not weaken or replace it.

Required mappings remain:

| DWD CDC family | archive code | CSV column | canonical variable |
| --- | --- | --- | --- |
| `air_temperature` | `TU` | `TT_TU` | `temperature_2m` |
| `air_temperature` | `TU` | `RF_TU` | `relative_humidity_2m` |
| `dew_point` | `TD` | `TD` | `dew_point_2m` |
| `pressure` | `P0` | `P` | `pressure_msl` |
| `wind` | `FF` | `F` | `wind_speed_10m` |
| `extreme_wind` | `FX` | `FX_911` | `wind_gust_10m` |
| `precipitation` | `RR` | `R1` | `precipitation_1h` |
| `cloudiness` | `N` | `V_N` | `cloud_cover` |

DWD missing sentinel `-999` is omitted, never converted to zero or imputed. `V_N` oktas are converted to percent only for physical values `0..8`; negative special states are omitted.

## Source plan behavior

`production-bootstrap-plan` remains network/DB-free, but after issue #157 it intentionally returns:

```text
state = BLOCKED_SOURCE_CAPABILITY
block_reasons = [NO_COMPLETE_ICON_D2_EXACT_RUN_ARCHIVE_TRANSPORT]
production_data_authority_granted = false
```

The blocker is part of the plan identity, so a later source fix produces a new bootstrap fingerprint. Old #148 authorization/fingerprint must never be reused after a capability decision changes.

`production-bootstrap-resume-validate` also propagates source plan blockers. Even structurally complete evidence cannot override a current source capability block.

## Checkpoint and integrity invariants

Forecast backfill remains exact ordered-prefix only:

- checkpoint entry is added only after a successful exact-run fetch and SQLite insert;
- an unavailable run leaves the checkpoint unchanged;
- later runs are not fetched after the failure;
- skip-ahead is forbidden;
- `missing_runs_allowed=false` remains unchanged;
- synthetic/imputed forecasts are forbidden;
- alternate model/provider substitution is forbidden;
- immutable snapshot/revision/dedupe checks remain mandatory.

## Authority boundary

Issue #157 is source-only. Its branch, PR, merge, CI, or application SIMPLE-DEPLOY do **not** authorize:

- production SQLite/corpus/checkpoint writes or resume;
- schema init/migration;
- checkpoint editing or skip-ahead;
- recurring ingest installation/enablement;
- RPi5 Docker/systemd mutation;
- WeatherNext/private-home activation;
- Cloudflare/network/secrets/permissions;
- delete/restore/cleanup/rollback.

Parent #148 remains paused. A future production resume requires both:

1. a merged source capability decision that removes `NO_COMPLETE_ICON_D2_EXACT_RUN_ARCHIVE_TRANSPORT` with evidence-backed exact-run coverage; and
2. a new exact LIVE/DATA authorization bound to the new reviewed source SHA and new bootstrap fingerprint.

Recurring public ingest remains a later separate host gate only after frozen corpus integrity is PASS.
