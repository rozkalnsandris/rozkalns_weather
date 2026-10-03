# Verification

## Truth

Canonical measured truth is DWD CDC station 05480.

Private `home` forecasts are not called measured home accuracy unless a defensible home observation source is added.

## Core metrics

Keep the user-facing verification set small:
- MAE;
- RMSE;
- bias;
- sample count `n`;
- lead-time buckets.

Precipitation amount and probability are different quantities and must not be mixed.

WeatherNext probabilistic/quantile coverage is enabled only with genuine WeatherNext statistics.

## Reproducibility

Forecast snapshots remain immutable and retain model/init/retrieval/valid/lead/statistic provenance. Verification must compare the forecast that existed before the observation, not a later overwritten value.
