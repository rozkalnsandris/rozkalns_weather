# Common sample sufficiency contract

Contract id: `common-sample-sufficiency-v1`

## Purpose

Verification comparison surfaces must not imply comparable model skill when providers use different timestamps, lead buckets, variables or model-version periods. Every metric family also exposes its sample size and sufficiency state so sparse evidence stays visibly sparse.

## Strict deterministic comparison boundary

`common_sample_leaderboard` partitions samples by:

1. comparison mode;
2. variable;
3. lead bucket;
4. exact provider model-version vector for that common timestamp.

Within that slice it intersects sample identities across all compared providers. Provider-only timestamps are excluded from comparison metrics. Exact model-version vectors form separate cohorts, so a stable peer version is not silently pooled across another provider's old/new model boundary.

One provider/sample identity may occur only once inside a comparison slice; duplicates fail closed.

## Sample evidence

Every strict comparison row exposes:

- `n` — samples actually used by that exact version cohort;
- `sample_sufficiency_state` / `sample_confidence`;
- `missingness.expected_n` — union of sample identities observed across compared providers in the slice;
- `missingness.available_n` — identities available for this provider;
- `missingness.missing_n` and `missing_fraction`;
- `missingness.common_n` — common sample count for this exact version cohort;
- `missingness.total_common_n` — common sample count before splitting by model-version cohort;
- `missingness.excluded_non_common_n` — provider samples excluded because peers do not share them.

Thresholds remain:

- `n < 30` → `insufficient_sample`;
- `30 <= n < 100` → `limited_sample`;
- `n >= 100` → `usable_sample`.

Bootstrap MAE 95% confidence intervals are emitted only at `n >= 30`.

## API and PWA

`/api/verification/summary` exposes `common_sample_slices` under this contract. Provider `overall`, `by_lead_bucket` and `by_model_version` aggregates remain available as descriptive diagnostics and are explicitly marked `descriptive_only`; the PWA Accuracy comparison table uses only `common_sample_slices`.

Each row shows provider/model version, lead bucket, `n`, missingness, sufficiency, MAE, RMSE, bias and eligible p10-p90 coverage.

## Probabilistic metrics

CRPS, interval/WIS and Brier outputs expose `n`/sample-sufficiency evidence. Where no strict common-sample denominator has been constructed, missingness is explicitly `not_assessed`; those outputs are descriptive calibration evidence, not a cross-provider ranking shortcut.

Summary quantiles are not converted into ensemble members or event probabilities.

## Monthly reports

`station_benchmark_monthly_v3` declares the same contract. Deterministic leaderboard and wins/losses are separated by the complete provider model-version cohort. Ensemble calibration surfaces carry sample-sufficiency evidence beside CRPS, interval/WIS and Brier results.

## Safety boundaries

This contract is source/reporting logic only. It does not authorize production corpus mutation, model weighting/Combined forecast, fabricated WeatherNext values, or any LIVE/runtime mutation.
