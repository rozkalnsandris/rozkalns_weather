# Verification golden corpus

Issue #71 adds a deliberately small, synthetic-only oracle for verification semantics. The fixture is `tests/fixtures/verification_golden_corpus.json`; `tests/test_verification_golden_corpus.py` executes the production verification primitives against those frozen expectations.

## Safety and provenance boundary

All numbers in this corpus are synthetic. They are not WeatherNext observations or forecasts, are not read from the production corpus, and must not be presented as real model performance. `observed` values stand in for the DWD observation-truth contract only so matching and metric formulas can be checked deterministically. WeatherNext-style names and statistics exercise semantic contracts without fabricating real WeatherNext values.

## Point metrics, interval coverage, and missingness

The three available point forecasts have errors `+1`, `-2`, and `0`.

- MAE = `(1 + 2 + 0) / 3 = 1`.
- RMSE = `sqrt((1^2 + (-2)^2 + 0^2) / 3) = sqrt(5/3) = 1.2909944487358056`.
- Bias = `(1 - 2 + 0) / 3 = -1/3`.
- The synthetic p10-p90 intervals cover observations in cases 1 and 3 but not case 2, so coverage is `2/3` with `coverage_n=3`.
- `expected_n=4` and `available_n=3`, therefore `missing_n=1` and missing fraction `1/4 = 0.25`.

The fixture also pins lead-bucket boundaries at 6, 12, 24, 360, and 361 hours so an inclusive/exclusive boundary change fails deterministically.

## Genuine ensemble CRPS

For members `[0, 1, 2]` and observation `1`:

- mean absolute member-to-observation distance = `2/3`;
- mean of all nine pairwise member distances = `8/9`;
- CRPS = `2/3 - 0.5*(8/9) = 2/9 = 0.2222222222222222`.

For members `[1, 3, 5]` and observation `4`:

- first term = `5/3`;
- pairwise mean distance = `16/9`;
- CRPS = `5/3 - 0.5*(16/9) = 7/9 = 0.7777777777777778`.

The mean CRPS is therefore `(2/9 + 7/9) / 2 = 0.5`.

## WIS-style score

`weighted_interval_score` uses median weight `0.5` and alpha weights `alpha/2` for `alpha = 0.1, 0.2, 0.4`.

For `[0,1,2]` with observation `1`, the interpolated interval widths are `1.8`, `1.6`, and `1.2`; there is no miss penalty and the median error is zero. The weighted numerator is `0.05*1.8 + 0.1*1.6 + 0.2*1.2 = 0.49`. Total weight is `0.85`, giving `0.49 / 0.85 = 0.5764705882352941`.

For `[1,3,5]` with observation `4`, the median error contributes `0.5`, while interval terms contribute `0.18 + 0.32 + 0.48`. The numerator is `1.48`; `1.48 / 0.85 = 1.741176470588235`.

These scores are valid only for genuine ensemble members. WeatherNext-style summary quantiles are explicitly tested as ineligible for CRPS/WIS and cannot be converted into synthetic members.

## Explicit precipitation probability

The explicit probabilities/observations are `(0.8,1)`, `(0.2,0)`, `(0.6,0)`, `(0.4,1)`. Squared errors are `0.04`, `0.04`, `0.36`, `0.36`, so Brier score is `0.8 / 4 = 0.2`.

With five reliability bins, the four samples land in `[0.2,0.4)`, `[0.4,0.6)`, `[0.6,0.8)`, and `[0.8,1.0]` respectively; the fixture freezes each bin count, mean probability, and observed frequency. `expected_n=5` also freezes one missing sample and a `0.2` missing fraction.

For genuine precipitation members `[0,0.2,0.3,0]` at the `0.1 mm` occurrence threshold, event probability is `2/4 = 0.5`. A second all-zero member set gives probability `0`. Against synthetic observed amounts `0.2` and `0`, event outcomes are `1` and `0`; Brier score is `(0.25 + 0) / 2 = 0.125`.

A deterministic precipitation amount is not a probability. The semantic gate allows Brier/reliability only for `precipitation_probability_1h` explicit event probability or a fraction derived from genuine `precipitation_1h` ensemble members. `ProbabilityPair(probability_source="deterministic_amount")` must fail.

## WeatherNext-style summary statistics and units

Synthetic `mean`, `p10`, and `p50` values exercise the same semantic families expected from WeatherNext-style summaries:

- `mean` is `summary_mean` and is eligible for point metrics such as MAE;
- `p10`/`p50` are `summary_quantile`, not ensemble members;
- summary quantiles are therefore ineligible for CRPS/WIS and for Brier/reliability.

The corpus also freezes the canonical `temperature_2m` unit as `degC`: supplying `K` must produce `invalid_unit:temperature_2m:K` rather than silently mixing units.

## Common-sample and model-version matching

The common-sample case uses two synthetic providers in the same `12-24h` lead bucket. Samples `s1` and `s2` share the version cohort `dwd_icon_d2=2026a` plus `weathernext3=3.0.0-synthetic`. `s4` shares a different WeatherNext version, `3.1.0-synthetic`, and therefore forms a separate cohort. `s3` exists only for DWD and must never enter a common matched set.

For the `3.0.0-synthetic` cohort the matched IDs are exactly `s1,s2`; `s3,s4` are explicitly excluded. For the `3.1.0-synthetic` cohort only `s4` is matched; `s1,s2,s3` are excluded. DWD has four available IDs while WeatherNext has three, so expected missing counts are `0` and `1` respectively. This prevents future matching changes from silently pooling model versions or using non-common samples.

## Regression intent

A change to a metric formula, lead-bucket boundary, probability binning rule, semantic/unit eligibility, model-version cohorting, common-sample intersection, or missingness accounting should change a frozen expected output and fail the suite. Updating a golden value therefore requires a deliberate review of the corresponding manual calculation and semantic contract rather than a blanket fixture refresh.
