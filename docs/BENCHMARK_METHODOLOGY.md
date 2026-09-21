# Benchmark methodology v3

## Location identity

Measured public forecast skill uses the canonical DWD CDC benchmark station `05480` (`Werl`) with source identity `station_05480`. Forecast and truth rows must share that exact `location_id` before they can enter measured-skill comparisons.

The public station coordinates stored in source are DWD station metadata. They are not private home coordinates.

`home` remains private/runtime-only. Home forecasts may be shown in the dashboard when configured, but they are not silently mixed with station truth.

Legacy `station_10416`/MOSMIX material may remain as historical or current-reference compatibility data. It is not the truth identity for the new measured public common benchmark and is never relabelled as `station_05480`.

## Fixed common window

The first production common verification window selected by issue #159 is fixed and non-rolling:

`2026-08-13..2026-08-26`

It uses exactly:

- `icon_d2`;
- `ecmwf_ifs`;
- `ecmwf_aifs`;
- run hours `00/06/12/18 UTC`;
- DWD CDC `05480` observation truth.

Rows outside this window remain immutable historical evidence but do not count toward this common-window readiness decision.

## Run provenance

Every immutable forecast run preserves provider/model identity, model version when known, `init_time_utc`, upstream availability when known, `retrieved_at_utc`, valid time, lead, statistic, transport and content/revision provenance.

Open-Meteo comparison models use Single Runs with explicit `run=` initialization. Issue #159 independently proved exact-run availability for every selected init/model combination and full-horizon boundaries; it did not substitute Historical Forecast, Previous Runs or rolling timeseries.

IFS lead-bucket integrity is cycle-aware. The common benchmark still requires all `00/06/12/18 UTC` init cycles, but their expected lead coverage follows the upstream cycle horizon: the long `00/12 UTC` runs use the requested 10-day comparison surface, while `06/18 UTC` are capped at T+144h. Therefore `5-7d` coverage remains required from all four cycles, while `7-10d` is expected only from `00/12`. This matches the ECMWF Open Data forecast-step contract and does not truncate long runs or synthesize short-run values.

Missing runs may not be skipped or fabricated. Alternate models/providers may not be substituted or relabelled. Revision drift remains an integrity condition rather than an invitation to overwrite older snapshots.

## Observation truth

DWD is the observation authority. The station `05480` truth transport is direct DWD CDC Open Data. Missing sentinels are omitted, never imputed. Forecast transport does not change observation authority.

DWD severe-weather warnings remain authoritative. WeatherNext, ICON, IFS and AIFS are forecasts and must never be rendered as official warnings.

## Temperature skill

Primary deterministic metrics remain MAE, RMSE, bias, sample count and lead-time bucket. Direct rankings use common valid timestamps inside the same lead bucket and location identity.

## Run skill vs user-available skill

Run-to-run verification compares exact init/lead forecasts against station truth. Operational/user-available analysis additionally requires the forecast to have been available and retrieved by the relevant decision time. Retrieval time is not fabricated as upstream publication time.

## Precipitation

`precipitation_1h` is an amount in mm for a 60-minute accumulation. `precipitation_probability_1h` is a probability for a versioned event. They remain distinct verification inputs.

Deterministic precipitation uses amount errors. Genuine ensemble probabilities use probabilistic metrics such as Brier score/reliability. WeatherNext quantiles are not converted into fabricated occurrence probabilities.

## Historical preservation

The previous `2026-04-02..2026-09-10` bootstrap attempt and its partial ICON-D2 prefix are retained as audit evidence. Selecting the issue #159 fixed window does not authorize deletion, cleanup, rollback, checkpoint editing, relabelling or rewriting of those rows.

## Authority

Source benchmark readiness does not grant production SQLite/corpus writes, host mutation, recurring ingest activation, WeatherNext private access, network changes or secret changes. Those remain separate explicit gates.
