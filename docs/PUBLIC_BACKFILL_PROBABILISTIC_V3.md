# Public backfill + probabilistic benchmark v4

This source lane builds a reproducible public benchmark while WeatherNext 3 private access remains separately gated. It does not authorize production corpus writes.

## Deterministic common-window scope

The source-selected common window is fixed and non-rolling: `2026-08-13..2026-08-26`.

Open-Meteo Single Runs with explicit `run=` is used for:

- DWD ICON-D2;
- ECMWF IFS HRES;
- ECMWF AIFS 0.25° Single.

Every common-window model uses exactly `00/06/12/18 UTC` initialization times at the exact public coordinates of DWD CDC station `05480` / `station_05480`.

Issue #159 independently proved all `168/168` selected exact-init/model combinations for the complete adapter variable set and `24/24` start/end full-horizon boundaries. Historical Forecast, Previous Runs and rolling timeseries are not substitutes for exact-init corpus rows.

Historical forecast rows outside the fixed common window remain immutable audit evidence. They are not deleted and do not silently enter common-readiness counts.

## Deterministic backfill command

The later separately authorized production backfill is bounded to the fixed common window:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<path> forecast \
  --model icon_d2 --start 2026-08-13 --end 2026-08-26 \
  --run-hours 0,6,12,18 --checkpoint <new-fixed-window-checkpoint.json> --dry-run
```

Equivalent model-specific invocations apply to `ecmwf_ifs` and `ecmwf_aifs`. Remove `--dry-run` only under a current exact LIVE/DATA authorization bound to the merged source SHA and new bootstrap fingerprint.

The new checkpoint namespace is `fixed-window-20260813-20260826-v1`; the old partial ICON-D2 checkpoint must not be reused.

## Observation truth

Historical truth is direct DWD CDC Open Data for station `05480` (`Werl`), not Bright Sky and not WMO/MOSMIX `10416` substitution. DWD remains source authority. Forecast and truth use `location_id=station_05480`.

Required truth coverage is source-verified through `2026-09-10`, which covers the entire selected window and the latest requested AIFS horizon. Missing DWD values remain missing and are never imputed.

## Integrity reconciliation

Production readiness uses the existing read-only report against exactly the fixed window:

```bash
rozkalns-weather corpus-report --start 2026-08-13 --end 2026-08-26
```

Required properties remain: all expected runs present, no unexpected runs, no revision anomalies, required lead-bucket coverage, matching DWD truth, and preserved critical provenance.

## Ensemble surface

Public ensemble adapters remain separate from the deterministic exact-run corpus. ICON-D2-EPS, ECMWF IFS ENS and ECMWF AIFS ENS member identities are preserved. Expired members are never fabricated.

WeatherNext 2, when exposed as legacy AI context, never replaces or impersonates WeatherNext 3.

## Verification

Deterministic metrics use common samples inside each lead bucket and include MAE, RMSE, bias and sample count. Probabilistic metrics require genuine ensemble/probability inputs and include CRPS, interval coverage/score, Brier score and reliability where appropriate.

Deterministic precipitation amount and event probability remain distinct. WeatherNext summary quantiles are not converted into fabricated occurrence probabilities.

## Safety boundary

This document and source implementation do not authorize:

- production SQLite/corpus/checkpoint writes;
- schema migration/init;
- deletion or rewriting of the old 279-run ICON-D2 prefix or DWD truth;
- RPi5/Docker/systemd/timer mutation;
- WeatherNext 3 private BigQuery/GCS activation;
- private home coordinates or credentials;
- Cloudflare/network/secrets/permissions changes.
