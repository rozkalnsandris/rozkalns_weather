# Verification data watermark contract

`verification-data-watermark-v1` freezes verification/report eligibility to data that was defensibly available by an explicit UTC `as_of` cutoff.

## Availability semantics

The contract never invents provider or DWD publication timestamps.

- Forecast availability is based only on the actual forecast `retrieved_at_utc` recorded in provenance.
- DWD truth availability is based only on the actual retrieval time of a truth revision.
- The selected truth revision is the latest revision whose retrieval timestamp is `<= as_of_utc`.
- A later truth revision remains in corpus history but is excluded from an earlier cutoff and reported as `POST_CUTOFF_TRUTH_REVISION`.
- `report_generated_at_utc` must be at or after the watermark.

Stable reason codes distinguish:

- `LATE_FORECAST_RETRIEVAL`
- `LATE_TRUTH_ARRIVAL`
- `POST_CUTOFF_TRUTH_REVISION`
- `FORECAST_MISSING`
- `TRUTH_MISSING`
- `ON_TIME`

## Reproducibility

The output contains two SHA-256 identities:

1. `watermark_identity_sha256` binds the contract version, exact `as_of_utc`, forecast retrieval evidence and the truth revision selected at that cutoff.
2. `matched_set_identity_sha256` binds the exact metric-eligible sample set to that watermark identity.

A rerun at a later watermark is therefore allowed to admit late data or a later DWD revision, but it produces a different identity rather than silently changing the earlier report.

`watermark_report_lineage_inputs()` maps those identities into the existing `verification-report-lineage-v1` inputs. The report receipt therefore declares the watermark contract, `as_of_utc`, exact watermark identity and matched-set identity without changing the existing report-lineage schema.

## Missingness and latency integration

Each watermark sample exposes a `missingness` object with the forecast/truth availability and verification inclusion decision at the cutoff. This is the cutoff-aware evidence expected by the existing missingness/selection-bias layer; late forecast/truth are not collapsed into genuinely missing data.

When `provider-availability-latency-v1` evidence is supplied, its state/reason codes are retained in `latency_context`. Latency evidence is context only and never fabricates or overrides cutoff availability.

## Boundaries

The contract is pure/read-only. It does not:

- rewrite or delete production corpus rows;
- mutate observation revisions or checkpoints;
- infer unavailable provider publication timestamps;
- rank or weight models;
- poll live providers;
- mutate RPi5, Docker, systemd, timers, Cloudflare, credentials or other LIVE/runtime state.
