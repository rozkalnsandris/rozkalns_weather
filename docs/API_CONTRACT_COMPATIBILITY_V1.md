# API contract compatibility gate

Issue #58 freezes the dashboard-facing response contract as `api-contract-v1`.

## Covered surfaces

The machine contract in `contracts/api-contract-v1.json` covers `/health`, `/ready`,
`/api/readiness`, `/api/health/providers`, `/api/current`, `/api/hourly`,
`/api/daily`, and the PWA verification surface `/api/verification/summary`.

`src/rozkalns_weather/api_contracts.py` is the executable registry and validator.
CI tests compare the checked-in snapshot with that registry and validate current
FastAPI fixture payloads against it.

## Compatibility semantics

Response-contract changes are classified with stable reason codes:

- `IDENTICAL`: no contract change.
- `ADDITIVE_COMPATIBLE`: a new endpoint/property or enum value is added while
  existing guarantees remain valid.
- `BREAKING`: an endpoint/property is removed, a required response guarantee is
  weakened, a type changes, nullability is narrowed, or an existing enum value
  disappears.

A response field that was required and later becomes optional is breaking because
clients can no longer rely on it. Additional response fields are compatible.

## State and authority invariants

The frozen contract keeps PWA data states `fresh`, `stale`, `error`, and `offline`
distinct. Provider API freshness uses its source states independently; `offline`
remains a browser/cache state rather than a fabricated upstream provider state.

DWD remains the severe-weather warning authority. WeatherNext 3 is research
forecast data and has no warning authority. Contract changes must not collapse
provider provenance or turn stale/error/offline evidence into fresh data.

## Privacy

The snapshot contains schema/enum metadata only. It must not contain `HOME_LAT`,
`HOME_LON`, exact private coordinates, credentials/tokens, private database or
filesystem paths, or raw logs. `privacy_violations()` reports only sanitized
reason code + structural path and never echoes the sensitive value.

## Scope boundary

This gate is source/CI only. It does not deploy the API, change network/runtime
configuration, access WeatherNext private data, or mutate the production corpus.
