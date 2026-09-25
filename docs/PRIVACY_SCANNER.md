# Cross-artifact privacy leakage scanner

Issue: `#76`

`src/rozkalns_weather/privacy_scanner.py` is the source-level gate for deciding
whether a machine-readable artifact may be treated as GitHub-safe.

## Covered artifact classes

The same deterministic scanner is used for:

- `api_snapshot`
- `rollout_evidence`
- `diagnostics_bundle`
- `benchmark_export`
- `report`
- `reproducibility_receipt`

Call `scan_github_safe_artifact(kind, payload)` before publication or attachment.
`PASS` means the scanner found no prohibited class. `BLOCKED` means the artifact
must not be treated as GitHub-safe. `require_github_safe_artifact()` is the
fail-closed helper for callers that need an exception boundary.

The scanner does not retrieve secrets, open runtime files, mutate an artifact or
authorize publication/deployment. It only validates the supplied source-level
payload.

## Prohibited classes

Structured fields cover private-home coordinates/address material,
credentials/tokens, private filesystem/database paths and raw private logs.
Conservative text checks additionally detect embedded URL credentials,
credential-like URL query parameters, credential assignments and obvious
private runtime paths.

Findings contain only an artifact path and stable reason code. The source value
is never copied into evidence or exception text.

Unscoped numeric latitude/longitude pairs are BLOCKED. Coordinate pairs bound
to explicit public station metadata are allowed for `station_05480` and the
historical public `station_10416` compatibility reference. `station_05480`
remains the canonical measured benchmark; the allowlist does not change
benchmark semantics.

Placeholder credential values such as `<redacted>` or `${TOKEN}` are allowed so
schemas/examples can represent redacted fields without requiring a real secret.

## Machine contract

`contracts/privacy-scanner-v1.json` pins:

- supported artifact kinds;
- prohibited classes;
- stable reason codes;
- public-station metadata policy;
- sanitized evidence fields;
- explicit no-secret/no-runtime/no-production-data authority.

Fixture tests prove nested JSON leakage, URL/query credential leakage, private
paths, unscoped coordinates, safe public station metadata, deterministic reason
ordering, placeholder handling and machine-contract parity.

## Trust boundary

This gate is source-only. It does not authorize:

- secret or credential retrieval;
- real `HOME_LAT` / `HOME_LON` fixtures;
- production log collection;
- GitHub settings/secrets/permissions mutation;
- RPi5/runtime/LIVE mutation;
- production SQLite/corpus mutation.

DWD remains the official severe-weather warning authority. WeatherNext values
must never be fabricated, and provider/model provenance remains unchanged.
