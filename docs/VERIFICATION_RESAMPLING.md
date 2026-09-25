# Deterministic verification resampling

`verification-resampling-v1` defines source-only reproducibility rules for bootstrap confidence intervals used by verification reports.

The contract does **not** create a model ranking, winner, combined score, production-data mutation, or runtime authority. A confidence interval is uncertainty evidence around one already-eligible verification statistic.

## Existing sample-sufficiency contract remains authoritative

Resampling reuses `rozkalns_weather.verification.sample_confidence` unchanged:

- `n < 30` → `insufficient_sample` → resampling is blocked;
- `30 <= n < 100` → `limited_sample` → resampling is eligible;
- `n >= 100` → `usable_sample` → resampling is eligible.

An upstream verification slice may also explicitly be ineligible. In that case resampling fails closed with `SAMPLE_NOT_ELIGIBLE` even when `n >= 30`.

## Algorithm

The v1 algorithm is `sha256-index-bootstrap` version `1`.

1. Each real verification contribution is represented as `{sample_id, value}`.
2. `sample_id` must be stable and unique inside the verification slice.
3. Samples are sorted by `sample_id` before hashing or resampling. Reordering an otherwise identical input set therefore does not change identity or output.
4. The canonical sample list is hashed with the repository canonical JSON serializer to obtain `sample_identity_sha256`.
5. Stable context is normalized: provider, model name, explicit model version (including `null` when appropriate), lead bucket, variable, comparison mode, statistic, and metric configuration.
6. `seed_identity_sha256` is derived from canonical SHA-256 over the sample identity, normalized context, metric configuration identity, algorithm identity, statistic, and explicit seed namespace.
7. For each bootstrap replicate and draw position, the selected source index is:

   `sha256(seed_identity:replicate:draw)[:8] modulo sample_count`

8. No process RNG or Python `random` state is used.
9. Replicate statistics are sorted and interval bounds use deterministic linear interpolation (`linear-interpolation-v1`).

The v1 implementation supports `mean` and `root_mean_square` aggregators. Metric semantics remain explicit in `metric_configuration`: for example, MAE uses per-sample absolute-error contributions with `mean`; bias uses signed-error contributions with `mean`; RMSE uses signed-error contributions with `root_mean_square`.

Bootstrap draws select only values from the supplied real verification sample set. The implementation does not invent forecast or observation values.

## Receipt identity

Every receipt binds:

- `sample_identity_sha256`;
- provider / model / model version;
- lead bucket;
- variable;
- comparison mode;
- sample count and inherited sample-sufficiency state;
- metric configuration and `metric_configuration_sha256`;
- statistic;
- confidence level;
- resample count;
- algorithm method/version;
- seed derivation and `seed_identity_sha256`;
- point estimate and interval;
- non-ranking interpretation.

`resampling_receipt_identity_sha256` is the canonical SHA-256 of that complete receipt core. Identical inputs and configuration reproduce the same receipt. A changed sample value, sample identity, metric configuration, binding, confidence configuration, or seed namespace changes the receipt identity. An unsupported algorithm version fails closed rather than silently changing methodology.

## Reordered samples

The canonical sample identity is order-insensitive because the normalized sample list is sorted by `sample_id` before hashing. This is intentional: changing database row order or serialization order must not create a new statistical result.

Duplicate `sample_id` values are rejected because they make sample identity ambiguous.

## Report lineage

`verification-report-lineage-v1` may bind one or more validated resampling receipts. The report lineage stores only privacy-safe resampling lineage fields:

- resampling receipt identity;
- method and version;
- seed derivation and seed identity;
- sample identity;
- provider/model/version, lead bucket, variable, comparison mode;
- sample count;
- metric configuration identity;
- statistic and confidence level;
- `interpretation=uncertainty_interval_only`;
- `ranking_verdict=false`.

Raw sample contributions and bootstrap replicate arrays are not copied into report lineage. When resampling lineage is absent, existing report-lineage configuration and identity behavior remains backward compatible.

## Stable fail-closed reason codes

Important v1 reasons include:

- `SAMPLE_NOT_ELIGIBLE`
- `INSUFFICIENT_SAMPLE_COUNT`
- `MISSING_SAMPLE_IDENTITY`
- `DUPLICATE_SAMPLE_IDENTITY`
- `INVALID_SAMPLE_VALUE`
- `MISSING_RESAMPLING_BINDING`
- `MISSING_METRIC_CONFIGURATION`
- `UNSUPPORTED_STATISTIC`
- `UNSUPPORTED_ALGORITHM_VERSION`
- `INVALID_CONFIDENCE_LEVEL`
- `INVALID_RESAMPLE_COUNT`
- `MISSING_RESAMPLING_LINEAGE`
- `RESAMPLING_RECEIPT_CONTRACT_MISMATCH`
- `INVALID_RESAMPLING_RECEIPT_IDENTITY`

## Interpretation boundary

The interval is not a statement that one provider is better than another. It must not be converted into a winner, rank, blended score, model weight, or selection policy by this contract.

Any future comparative decision rule needs its own explicitly reviewed methodology and issue scope.

## Authority boundary

Issue #98 is source-only. It grants no authority for:

- production corpus mutation;
- scheduler or service changes;
- RPi5 deployment/restart;
- private BigQuery reads or credentials;
- publication decisions;
- outcome-driven seed selection;
- model ranking or combined weighting.

Real runtime or production-data changes remain separate owner gates under repository policy.
