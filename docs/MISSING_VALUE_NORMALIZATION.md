# Missing-value normalization

`missing-value-normalization-v1` defines the source-side boundary for provider values that are absent, null, non-finite, provider-specific sentinels, or omitted during transport/parse handling.

## Invariants

- Missingness is classified; values are never imputed, inferred, or replaced with zero.
- Legitimate numeric zero remains a present value for precipitation, wind, probabilities, and other supported variables.
- `NaN`, `+Inf`, and `-Inf` are blocked before verification metrics consume them.
- Provider sentinels are explicit provider/field contract data supplied by the adapter or caller. This layer never guesses a global sentinel list.
- Missing raw values are represented by safe provenance tokens such as `NaN`, `+Inf`, or `-Inf`; invalid JSON numeric literals are not emitted.
- The corpus integration is audit-only. It does not mutate, delete, repair, or rewrite stored corpus rows.

## Canonical classes and reason codes

| Missing class | Stable reason code |
| --- | --- |
| `ABSENT_FIELD` | `MISSING_ABSENT_FIELD` |
| `UPSTREAM_NULL` | `MISSING_UPSTREAM_NULL` |
| `NON_FINITE_NUMERIC` | `MISSING_NON_FINITE_NUMERIC` |
| `PROVIDER_SENTINEL` | `MISSING_PROVIDER_SENTINEL` |
| `TRANSPORT_PARSE_OMISSION` | `MISSING_TRANSPORT_PARSE_OMISSION` |

A present value uses `VALUE_PRESENT` and has `missing_class=null`.

## Verification

`verification.ErrorPair`, `ProbabilityPair`, and summary-quantile observed-value scoring now fail before metric calculation when an input is non-finite or normalized missing. The `verification-value-missingness-v1` adapter attaches granular normalization reasons to the existing verification missingness report. Callers must set the canonical verification sample as excluded when normalization found a missing value; the adapter records why and never applies automatic weighting.

## Provider health

`classify_public_provider_health()` accepts an optional `value_missingness_summary`. It is attached as independent evidence and does not overwrite freshness or ingest-failure classification. A provider can therefore be transport-fresh while still exposing degraded value completeness.

## Corpus integrity

`corpus_value_integrity.audit_corpus_values()` performs a deterministic read-only audit of forecast and observation value rows. Missing/non-finite/sentinel findings block the value-integrity result, while legitimate zeros remain clean. No production-data authority is implied.

## Fixtures

`tests/fixtures/missing_value_normalization.json` covers null, NaN, positive and negative infinity, absent JSON field, transport omission, numeric and string sentinels, legitimate zero precipitation/wind/probability, and provider-specific sentinel behavior.
