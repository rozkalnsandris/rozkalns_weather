# Verification drilldown v1

`verification-drilldown-v1` is a read-only station benchmark view for explaining model skill without collapsing unlike forecast cycles, lead times, variables or model versions into one score.

## Dimensions

Every comparable row keeps these dimensions explicit:

- provider;
- exact model version;
- UTC init cycle;
- lead bucket;
- variable;
- valid-time month.

The comparison location is always DWD WMO `10416`. Home forecasts are not measured home accuracy.

## Common-sample policy

Deterministic public models (`icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`) are compared only on exact common valid times inside the same month, variable, UTC init cycle and lead bucket. Common timestamps are then split by the exact model-version vector of all compared providers.

Each metric row exposes `n`, sample sufficiency and missingness. Missingness distinguishes absent provider forecasts, missing DWD truth, samples excluded because they are not common across providers, and common timestamps assigned to another model-version cohort.

## Metric eligibility

Deterministic rows use the existing MAE/RMSE/bias semantics plus existing temperature, precipitation and wind-gust event definitions. Deterministic precipitation amount never implies event probability, CRPS or Brier.

Ensemble rows are separate. CRPS and interval/WIS metrics require genuine `member_N` inputs. Precipitation Brier/reliability is emitted only from genuine member fractions. Summary quantiles, deterministic values and WeatherNext summary statistics are never converted into synthetic ensemble members or probability.

## Interfaces

```bash
rozkalns-weather verification-drilldown --month YYYY-MM
```

The command opens the existing SQLite corpus read-only through the benchmark-export reader. It does not initialize schema, ingest data, repair snapshots or grant production-data/LIVE authority.

The PWA Accuracy view exposes a month selector and separate deterministic/ensemble tables. Provenance dimensions, `n`, missingness and sample-sufficiency state remain visible beside metrics.

API:

```text
GET /api/verification/drilldown?month=YYYY-MM
```

No overall model winner, ranking shortcut or Combined weighting is emitted.
