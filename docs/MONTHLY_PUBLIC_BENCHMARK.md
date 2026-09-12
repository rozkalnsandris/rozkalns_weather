# Monthly public benchmark report

Issue #45 adds a deterministic, privacy-safe monthly reporting pipeline for the public `station_10416` benchmark.

## Scope

The report reuses the reproducible `public-benchmark-export-v1` metric contract rather than defining another verification engine. It therefore preserves the same common-sample, lead-bucket, model-version, genuine-ensemble and DWD-truth semantics.

The report emits:

- `report.json` — machine-readable monthly benchmark evidence;
- `report.md` — human-readable rendering of the same evidence;
- `checksums.json` — SHA-256 checksums for both report artifacts.

## Command

```bash
python -m rozkalns_weather.monthly_public_report \
  --source-sha <EXACT_MERGED_SHA> \
  --month 2026-09 \
  --output ./monthly-public-2026-09
```

The SQLite corpus is opened through the same `mode=ro` + `PRAGMA query_only=ON` path as the reproducible benchmark export. The command never initializes, migrates, repairs or writes the corpus. The output directory must not already exist.

## Window semantics

The common public comparison begins on `2026-04-02`.

- A normal later month is `common_full_month`.
- April 2026 is `common_clipped`: April 1 remains explicit IFS-only historical context and is excluded from common metrics.
- A month entirely before `2026-04-02` is `historical_ifs_only` and emits `WARN`, not a false common benchmark.

Older IFS-only history is descriptive context only. It must never be mixed into the ICON-D2/IFS/AIFS common-sample metrics.

## Metrics

Deterministic rows are grouped by variable and lead bucket on the exact common valid-time intersection across `icon_d2`, `ecmwf_ifs` and `ecmwf_aifs`. Every provider row keeps model version, `n`, sample-sufficiency state, missingness, MAE, RMSE and bias.

Genuine `member_N` ensemble inputs may additionally produce CRPS, empirical interval coverage/width, WIS-style score, precipitation member-fraction probability, Brier Score and precipitation reliability bins. Summary quantiles or deterministic precipitation are never treated as ensemble members or probability forecasts.

A model-version boundary inside one requested common report is fail-closed (`MIXED_MODEL_VERSIONS`) rather than silently combined. Later drill-down work may explicitly split such periods.

## Notable cases

Notable cases are not manually chosen. The deterministic rule is:

> up to three largest absolute errors per provider / model version / variable / lead bucket, restricted to the exact common matched sample, with `valid_time_utc` as the deterministic tie-break.

This keeps provider/model-version boundaries visible and prevents a report author from cherry-picking cases after seeing outcomes.

## WeatherNext

WeatherNext 3 remains `pending` in this public-only report until a defensible real corpus exists. No WeatherNext values are fabricated, inferred from other models, or substituted from summary context.

## Privacy and authority

Only public station-level benchmark evidence is emitted. The report excludes exact home coordinates, credentials, database paths and raw private logs.

Generating or merging this source package does not authorize scheduler activation, production corpus mutation, WeatherNext private access, RPi5 runtime changes or any other LIVE action.
