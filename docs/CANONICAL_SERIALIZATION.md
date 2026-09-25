# Canonical evidence serialization

Contract: `canonical-evidence-serialization-v1`.

This contract defines the byte representation used when weather evidence, corpus manifests, verification receipts, watermarks, or future readiness evidence need a deterministic SHA-256 identity. It is a source-level determinism contract only. It does not authorize or perform production corpus rehashing, artifact publication, runtime mutation, provider mutation, or LIVE work.

## Canonical JSON rules

- Output is UTF-8 JSON followed by exactly one LF (`\n`).
- Object keys must be strings and are emitted in lexicographic Unicode code-point order.
- Array/tuple order is preserved. Unordered containers such as sets are unsupported.
- Booleans and null use JSON `true`, `false`, and `null`.
- Enum values are serialized recursively using their declared value.
- Strings are emitted as JSON strings with UTF-8 characters preserved.
- Unsupported object and numeric types fail closed instead of being coerced.

## UTC timestamp normalization

Fields named `utc` or ending in `_utc` are timestamp-bearing contract fields. Their string values must be ISO-8601 timestamps with an explicit zero UTC offset. Equivalent zero-offset spellings such as `Z`, `z`, `+00`, `+0000`, and `+00:00` normalize to a single `...Z` representation. A space or `T` separator normalizes to `T`.

Fractional-second precision is preserved. Only insignificant trailing zeroes are removed, so `.120000Z` becomes `.12Z`; no non-zero fractional digit is discarded. Non-zero timezone offsets are rejected in `_utc` fields rather than silently converted, because these fields already assert UTC semantics.

## Numeric determinism

Integers are emitted as base-10 JSON integer tokens. Finite Python floats are emitted using their shortest round-trip decimal representation; exponent spelling is normalized to lowercase `e`, without a plus sign or leading exponent zeroes. Positive and negative floating-point zero both serialize as numeric `0`.

`NaN`, positive infinity, negative infinity, `Decimal`, complex numbers, and other unsupported numeric representations fail closed. Canonical serialization performs **no domain rounding, clipping, unit conversion, imputation, correction, or quantization**.

This distinction is important:

- **Raw provider precision:** preserve the parsed finite provider value in provenance/evidence. Canonical serialization must not round it.
- **Derived metrics:** serialize the computed finite value without an extra canonicalization rounding stage.
- **Display values:** presentation-specific payloads may intentionally round values for readability, but that rounded display value is a different payload and must never replace raw/provenance evidence used for verification identity.

## SHA-256 identity

`canonical_sha256(value)` is SHA-256 over the exact bytes returned by `canonical_json_bytes(value)`, including the final LF. Logically equivalent payloads therefore receive the same identity when their only differences are mapping insertion order, supported equivalent UTC timestamp spelling, signed zero, or redundant integral `.0` float spelling. Materially different values, provenance, or configuration must produce a different identity.

The first integrations are the existing corpus provenance manifest, verification report lineage, and verification watermark hash paths. No existing production corpus is rewritten or rehashed by this issue.
