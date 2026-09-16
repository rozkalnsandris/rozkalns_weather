# Verification missingness and selection-bias audit

Contract: `verification-missingness-selection-bias-v1`.

This audit makes verification attrition explicit before provider/model metrics are interpreted. It does not rank models, choose an overall winner, impute samples, or assign Combined/automatic weights.

## Expected-sample matrix

The audit input is an explicit expected provider × sample matrix using `ExpectedVerificationSample` from `rozkalns_weather.verification_missingness`.

Each cell preserves:

- `sample_id`;
- provider and exact `model_version`;
- `variable`;
- `lead_hours`;
- `valid_time_utc`;
- `init_time_utc`;
- whether the forecast is available;
- whether truth is available;
- whether forecast/truth semantics are compatible;
- whether verification filters include the sample.

The report is grouped by provider/model-version cohort, lead bucket, variable, valid-time month, and UTC init cycle. A missing provider/sample cell is `INCOMPLETE_EXPECTED_MATRIX` and fails closed. The implementation never guesses whether an absent record means an upstream forecast gap, a truth gap, a semantic mismatch, or a verification-filter exclusion.

## Attrition reason codes

Direct reason precedence is deterministic:

1. `UPSTREAM_FORECAST_MISSING`
2. `TRUTH_GAP`
3. `SEMANTIC_INCOMPATIBILITY`
4. `VERIFICATION_FILTER_EXCLUDED`

A provider sample that is locally eligible but cannot enter the strict common set because another provider failed is `PEER_COMMON_SAMPLE_EXCLUDED`. A retained common sample is `MATCHED`.

When more than one direct condition applies, `reason_counts` uses the first reason above as the primary attrition code while `direct_reason_codes_by_sample` retains the full evidence list.

## Counts and matched-set identity

Each provider row reports:

- `expected_n`;
- `available_n`;
- `eligible_n`;
- `matched_n`;
- `excluded_n`;
- availability, eligibility, and matched fractions;
- reason counts and exact excluded sample IDs.

Each comparison reports the exact `expected_sample_ids`, `matched_sample_ids`, `excluded_n`, and a deterministic SHA-256 `matched_set_id`. The hash binds the comparison dimensions, exact model-version cohort, and ordered matched sample IDs.

`common_sample_leaderboard()` publishes the same evidence principle beside MAE/RMSE/bias/coverage output: `matched_set_id`, `matched_sample_ids`, `excluded_sample_ids`, and `excluded_sample_count`. The legacy `common_sample_ids` field remains for compatibility and is identical to `matched_sample_ids`.

## Selection-bias state

The audit compares provider availability and eligibility fractions within each exact comparison cohort.

- `PASS`: imbalance below `0.10` and at least one matched sample.
- `WARN`: imbalance is at least `0.10` but below `0.25`; reason `ATTRITION_IMBALANCE_WARN`.
- `BLOCKED`: imbalance is at least `0.25`; reason `ATTRITION_IMBALANCE_BLOCKED`.
- `BLOCKED`: no common matched samples; reason `NO_COMMON_MATCHED_SAMPLES`.

These thresholds are deterministic reporting gates. They do not change metric weights or select a preferred model.

## Machine-readable report

`build_verification_missingness_report()` returns a JSON-serializable dictionary containing:

- `schema_version` and `contract`;
- overall state and threshold metadata;
- exact expected provider scope;
- reason-code precedence;
- comparison rows and per-provider counts/evidence;
- `automatic_weighting: false`.

This function is the canonical machine-readable audit builder. Callers that only have already-filtered forecast/truth rows must not manufacture an attrition reason. They must first construct explicit expected cells from authoritative collection/truth/semantic/filter evidence.

In particular, current benchmark/report SQL paths that inner-join only available forecast and truth rows are insufficient to distinguish all four direct attrition causes by themselves. They may consume this audit once explicit expected-cell evidence is available, but they must not infer a cause from a row being absent.

## Boundaries

The contract does not authorize or perform:

- production corpus mutation;
- observation/forecast repair or imputation;
- nearest-station fallback;
- fabricated WeatherNext values;
- overall model ranking or weighting;
- LIVE/runtime mutation.

DWD remains the authoritative severe-weather warning source; this verification audit is analytical evidence only and must not be presented as an official warning source.
