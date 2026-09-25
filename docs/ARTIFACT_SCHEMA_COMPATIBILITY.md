# Verification/report artifact schema compatibility

Contract: `verification-report-schema-compatibility-v1`.

This gate applies only to machine-readable verification/report artifacts. Human-readable Markdown or presentation text is intentionally outside the compatibility decision and may evolve independently as long as the machine-readable contract remains valid.

## Explicit artifact identities

The current source registers these machine-readable families:

- verification summary: `verification-summary-v1`, schema version `1`;
- public monthly benchmark report: `public-monthly-benchmark-report-v1`, schema version `1`;
- public benchmark export: `public-benchmark-export-v1`, schema version `1`;
- reproducibility/lineage receipt: `verification-report-lineage-v1`, schema version `1`.

The historical `station_benchmark_monthly_v3` report identity remains readable as `station_benchmark_monthly` version `3`; the reader derives that identity from the explicit `report_type` and does not rewrite the historical artifact.

## Compatibility classes

`additive-compatible` means the producer added only optional fields. A current reader can read the historical artifact and tolerant historical readers can ignore the new fields.

`reader-compatible` means the current reader can consume the supported historical artifact without rewriting it, but an older reader is not guaranteed to understand every value produced by the newer schema. Enum expansion is intentionally in this class.

`breaking` means interpretation or consumer compatibility cannot be preserved safely. Required-field removal/addition, field type or requiredness changes, nullability changes, enum-value removal, family changes and version regression fail closed.

Every result carries stable reason codes and a deterministic evidence SHA-256. Mixed schema name/version identities in one bundle are `BLOCKED` with `MIXED_BUNDLE_SCHEMA_VERSION`.

## Historical reads

Historical upgrade/read behavior is source-side and non-mutating. `read_historical_artifact()` builds an in-memory reader view. A newly introduced field can be populated only from a schema-declared deterministic default; a missing required field without such a default blocks the read. The original artifact is never rewritten.

No production artifact rewrite, publication/deploy, production SQLite migration or runtime/LIVE mutation is authorized by this contract.

## Lineage binding

`report_lineage.py` now validates that the declared `report_schema` exactly matches the schema identity carried by the machine-readable artifact before building a receipt. Receipt validation repeats that binding check before accepting the artifact checksum. A caller therefore cannot label a v2 artifact as v3 (or vice versa) while retaining a valid lineage receipt.

The artifact checksum, corpus manifest identity, truth revision set and configuration identity remain independently bound exactly as before.
