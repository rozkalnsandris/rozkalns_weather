# Bounded API query and response contract

`api-query-bounds-v1` prevents public read-only API and report surfaces from turning corpus growth into unbounded work or oversized responses. It is a source-level contract only; it does not authorize or apply SQLite indexes, production corpus changes, reverse-proxy limits, runtime tuning, Cloudflare changes, or any LIVE mutation.

## Fixed source envelopes

The canonical limits are defined in `src/rozkalns_weather/query_bounds.py` and mirrored by `contracts/api-query-bounds-v1.json`:

- hourly forecast window: 1–360 hours;
- daily forecast window: 1–15 days;
- verification window: 1–366 days;
- monthly report query window: at most 31 days;
- continuation page: 100 rows by default when a cursor needs an implicit size, 200 rows maximum;
- provider selections: at most 8 distinct identifiers;
- model-version selections: at most 8 distinct identifiers;
- hourly source result: at most 5,000 rows after explicit provider/model filtering;
- verification sample envelope: at most 50,000 selected rows/samples per guarded endpoint;
- serialized response envelope: 512 KiB.

These are application safety envelopes, not statements about provider capability or forecast horizon quality.

## Hourly continuation semantics

`GET /api/hourly` preserves the previous default behavior for requests that fit the source-row and byte envelopes: without `page_size` or `cursor`, the complete bounded result is returned.

Clients that need continuation may provide:

- `page_size` (1–200),
- `cursor`,
- optional comma-separated `providers`,
- optional comma-separated `model_versions`.

Every successful response now includes a `query` object with:

- `query_identity_sha256`, bound to endpoint, window, variable, location, provider/model selections and effective page size;
- `snapshot_identity_sha256`, bound to the exact selected forecast values and provenance identity;
- `total_rows`, `offset`, `returned_rows`, `complete`, and `next_cursor`;
- `silent_truncation=false`.

The continuation token carries the query and snapshot identities plus the next offset. A changed query produces `CURSOR_QUERY_MISMATCH`. If the latest forecast snapshot changes between pages, continuation produces `CURSOR_SNAPSHOT_MISMATCH` (HTTP 409) instead of combining rows from two corpus states.

A non-paginated hourly response that would exceed the hard byte envelope is rejected with `RESPONSE_PAYLOAD_TOO_LARGE`; it is never silently shortened. A caller can then opt into an explicit bounded page size.

## Verification semantics

`/api/verification/truth-quality`, `/api/verification/summary`, and `/api/verification/precipitation` are limited to 366 days. Summary and precipitation routes also enforce the explicit verification sample envelope before publishing metrics.

`/api/verification/summary` and `/api/verification/precipitation` accept the same optional provider and model-version selection syntax. Aggregated results are not paginated because splitting a benchmark sample before metric calculation would change metric meaning. Instead, oversized sample sets fail closed with `SAMPLE_COUNT_TOO_LARGE`; callers must request a smaller time window or narrower selection. Successful aggregated responses include a completeness/query identity object and exact selected sample counts.

This preserves existing sample-sufficiency and common-sample semantics. No benchmark is silently truncated to make it fit.

## Monthly reporting

Monthly reporting already derives a closed-open calendar-month window with `_month_bounds()`. The #99 regression fixture binds that existing report query to `validate_date_window()` and proves a normal calendar month stays inside the explicit 31-day report envelope. Multi-month ad-hoc report scans are not introduced by this change.

## Existing lightweight paths

`/health`, `/ready`, `/api/readiness`, provider-health, current observations, corpus aggregate stats, warnings, and radar do not gain pagination or expanding selection parameters in this contract. Health and readiness remain independent of benchmark query guards and are exercised before/after guarded requests in regression tests.

`/api/corpus/integrity` remains an explicit full-corpus diagnostic rather than a user/report slice. #99 does not redefine an integrity scan as a partial result; production scheduling or runtime policy for that diagnostic remains a separate operational decision.

## Stable blocked reasons

The source contract emits machine-readable blocked envelopes with stable reason codes, including:

- `INVALID_QUERY_RANGE`
- `QUERY_WINDOW_TOO_LARGE`
- `INVALID_QUERY_WINDOW`
- `INVALID_PAGE_SIZE`
- `PAGE_SIZE_TOO_LARGE`
- `INVALID_SELECTION`
- `SELECTION_TOO_BROAD`
- `INVALID_CURSOR`
- `CURSOR_QUERY_MISMATCH`
- `CURSOR_SNAPSHOT_MISMATCH`
- `SAMPLE_COUNT_TOO_LARGE`
- `HOURLY_SOURCE_ROWS_TOO_LARGE`
- `RESPONSE_PAYLOAD_TOO_LARGE`

Blocked envelopes do not echo raw request values, coordinates, credentials, database paths, or logs.

## Relationship to SQLite scale readiness

Issue #59's `sqlite-scale-index-readiness-v1` remains the authority for query-plan evidence and proposed indexes. #99 does not apply those indexes. Query bounds reduce accidental request expansion, while #59 separately records where corpus growth can still justify a reviewed schema/index migration.

## Safety and mutation boundary

The implementation is read-only with respect to weather corpus data. Tests snapshot corpus aggregate state around health/readiness and guarded requests and require forecast-run/provider state to remain unchanged. The AUTO-RUN FULL #99 source authorization does not grant production database/index mutation, runtime deployment, reverse-proxy/rate-limit changes, Cloudflare/network changes, or any other LIVE action.
