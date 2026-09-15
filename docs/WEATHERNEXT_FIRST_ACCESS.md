# WeatherNext 3 first-access readiness

This document is a **source contract**, not private Google Cloud or production-data authority. `AUTO-RUN FULL` may build and test this contract without making a real BigQuery request. Access approval is established in issue #122; any real access remains a separate exact owner gate. Issue #125 final planning is in `WEATHERNEXT_FINAL_LIVE_PLAN.md`.

Canonical machine contract: `deploy/weathernext-first-access.json`.

## Purpose

The first WeatherNext 3 activation must prove, in order, that the linked BigQuery dataset is accessible, the expected WeatherNext 3 schema is still present, the selected canary query is bounded and within an explicit bytes cap, both required product surfaces return real provider rows, and provenance is complete before any SQLite write is eligible.

The initial canary is intentionally station-only at logical location `station_10416`. Private `HOME_LAT` / `HOME_LON` are not needed for the first benchmark snapshot and never enter GitHub evidence.

## Source-only planning

The network-free command chooses one target-disseminated init and emits a sanitized one-init canary envelope:

```bash
python -m rozkalns_weather.weathernext_access plan \
  --now <UTC_TIMESTAMP> \
  --hours-limit 6 \
  --max-bytes-billed <EXPLICIT_CAP>
```

An explicit `--init <UTC_TIMESTAMP>` may be supplied, but it is rejected if it is not in the target-disseminated candidate set. Canary scope is capped at 24 forecast hours and the source contract rejects a per-query `maximum_bytes_billed` above 1 GiB. The later private gate should normally bind a much smaller value based on a fresh dry-run estimate.

This command does not read environment secrets, contact BigQuery, inspect SQLite or write data.

## Private read-only access preflight

After the still-required runtime-only Google configuration, a separate private read-only gate may run:

```bash
python -m rozkalns_weather.weathernext_access preflight \
  --schema-only \
  --max-bytes-billed <EXPLICIT_CAP>
```

Successful schema-only state is `linked_dataset_ready`. Without Google project/dataset configuration the state is `access_pending`. Permission and linkage failures are reported separately as `permission_denied` or `dataset_unlinked`; required field drift is `schema_changed`.

A later authorized dry-run preflight removes `--schema-only`:

```bash
python -m rozkalns_weather.weathernext_access preflight \
  --hours-limit 6 \
  --max-bytes-billed <EXPLICIT_CAP>
```

The preflight performs schema inspection plus BigQuery **dry-run only** for the 0.05° and 0.1° point queries. It never initializes SQLite and never emits project ID, linked dataset ID, coordinates or SQL. `ready_for_canary` means both dry-run estimates are within the explicit cap. `cost_cap_rejected` stops before a real canary query.

## Query discipline

Both canary product queries must preserve all of these invariants:

- exact `init_time` partition filter;
- selected columns only; `SELECT *` is forbidden;
- one selected init;
- bounded forecast-hour window;
- 0.05° station product `weathernext_3_0_0_0p05deg`;
- 0.1° surface product `weathernext_3_0_0_0p1deg`;
- BigQuery dry-run before a real query;
- explicit `maximum_bytes_billed` on dry-run and real query jobs.

The source library function `execute_canary_queries(...)` requires successful matching dry-run evidence before it will issue the real read-only canary pair. AUTO-RUN FULL #22 does not call this function against Google.

## Schema fingerprint

`schema_summary(...)` produces two public-safe SHA-256 summaries:

- `observed_required_fingerprint` over only the required WeatherNext 3 contract paths;
- `observed_full_fingerprint` over the observed field paths in the two expected tables.

Missing/renamed required fields fail closed as `schema_changed`. Exact WeatherNext 3 table identities remain fixed; WeatherNext 2/Gen/Graph are not accepted as substitutes.

The fingerprint does not contain Google project or linked-dataset identity.

## Dissemination-aware selection

Source selection keeps WeatherNext 3 dissemination targets distinct from observed publication evidence:

- synoptic `00/06/12/18 UTC`: 360 h horizon, target availability around init + 8 h 10 min;
- interim hourly runs: 48 h horizon, target availability around init + 7 h 25 min.

Those are **expected dissemination targets**, not provider-observed publication timestamps. The adapter stores them as `expected_available_at_utc`; `upstream_available_at_utc` stays `null` unless a future source supplies defensible observed publication evidence.

Fallback may move to an earlier target-disseminated run only for genuine data latency. Permission/link/schema/cost failures are not converted into latency.

## Canary completeness

Before the first snapshot write is eligible, sanitized canary evidence must prove:

- non-empty 0.05° station rows;
- station-head temperature present;
- station-head dew point present;
- non-empty 0.1° surface rows with at least one required surface variable;
- both BigQuery dry-run estimates within cap;
- complete WeatherNext provenance validation.

The evidence intentionally reports presence/counts rather than provider values.

## Provenance

`validate_provenance(...)` requires WeatherNext 3 provider/model/version identity, init/retrieval/valid/lead semantics, BigQuery source surface, run class, horizon, all `mean/p10/p25/p50/p75/p90` statistics and 60-minute precipitation accumulation semantics.

A documented dissemination target must never be written into `upstream_available_at_utc` as if it were an observed publication timestamp.

## Canary vs first snapshot write

The ordered source contract is:

1. `linked_dataset_probe` — private read-only BigQuery;
2. `schema_fingerprint` — private read-only BigQuery;
3. `dry_run_cost_guard` — private read-only BigQuery;
4. `bounded_canary_query` — private read-only BigQuery;
5. `provenance_validate` — local read-only validation;
6. `first_snapshot_write` — **separate production SQLite mutation**.

`build_first_snapshot_write_envelope(...)` only emits write eligibility after sanitized canary evidence validates. It never writes data. Actual first-snapshot persistence requires a new exact private LIVE/data authorization and must retain the existing immutable/idempotent forecast-run semantics.

## Privacy-safe evidence

Completed canary evidence may contain schema fingerprints, selected init, run class, hours bound, dry-run bytes/cap results, product row counts/presence and provenance pass/fail. It must not contain:

- Google project or linked dataset identity;
- credentials, service-account material, tokens or secrets;
- `HOME_LAT`, `HOME_LON` or any coordinates;
- SQL containing the private point;
- database/host paths;
- raw logs or environment payloads.

Validate a sanitized evidence document locally with:

```bash
python -m rozkalns_weather.weathernext_access validate-evidence < evidence.json
```

To prove only that the next stage would be eligible, without writing anything:

```bash
python -m rozkalns_weather.weathernext_access validate-evidence --write-envelope < evidence.json
```

The output state `first_snapshot_write_eligible` is **not** data-write authority.

## Exact later private gate template

Before any real WeatherNext query or first snapshot, freshly bind the exact class being authorized. A combined gate must not be inferred from source merge.

```text
allowlist_approved_evidence=<fresh private evidence>
weather_sha=<current reviewed merged exact SHA>
weather_exact_sha_ci=<fresh required-check evidence>
auth_method=<runtime-only ADC/service identity; no credential material in GitHub>
google_project=<private runtime binding>
linked_dataset=<private runtime binding>
linked_dataset_location=<fresh private evidence>
schema_required_fingerprint=<current source contract>
schema_observed_fingerprint=<fresh sanitized evidence>
selected_init_utc=<one exact init>
forecast_hours_limit=<1..24>
maximum_bytes_billed_per_query=<explicit cap>
query_scope=station_10416
home_scope=disabled_for_first_canary
dry_run_required=true
canary_required_surfaces=0p05_station,0p1_surface
first_snapshot_target=<exact production SQLite target>
mutation_classes=<read_only_bigquery and/or production_sqlite_write explicitly named>
verification=<schema/dry-run/canary/provenance/corpus postconditions>
failure=<STOP; no undeclared retry/alternate link/credential/data mutation>
rollback=<no implicit SQLite delete/restore/cleanup>
```

Credential/IAM changes, Analytics Hub subscription/link changes, home-coordinate activation and production SQLite write are distinct owner decisions even if they are operationally adjacent.

## Authority

WeatherNext 3 remains experimental/research forecast output. DWD remains the official severe-weather warning authority in Germany. This source contract never fabricates WeatherNext values, access state or publication metadata.


## Issue #125 guarded station entrypoint

`read_first_access_canary` in `weathernext_access.py` is the private read-only
entrypoint for a later #122 authorization. It fixes `station_10416`, one explicit
init, and six forecast hours. The caller supplies private project/dataset/client
in memory through a separately reviewed trusted binding; never through GitHub.

It caps the metadata query, validates the required schema fingerprint, dry-runs
both exact SQL statements, rejects unknown/negative estimates, then queries both
surfaces with RPC/job retries disabled and bounded 60-second request/result waits.
Any exception propagates to STOP; no fallback init or alternate dataset is tried.
SQL hashes bind transient dry-run objects to the exact query and are not emitted.
A lower real cap is accepted only within the original successful dry-run envelope.
The operator must select the smallest defensible cap from fresh dry-run evidence;
1 GiB is a hard ceiling, never the recommended default cost.

Returns sanitized evidence and two native runs in memory, never prints raw values
or writes SQLite. `prepare_first_snapshot_run` separately validates admission and
prepares one immutable provider/init/retrieval snapshot, retaining complete native
product values in `raw_product_surfaces` metadata. Display values prefer 0.05°
station temperature/dew point; this is product selection, not model weighting.
Only a later exact data gate may call `Database.insert_forecast_run` with the
explicit `location_id="station_10416"`; ordinary unbounded ingest/diagnose/fallback
paths are not first-access entrypoints. Production schema must already be ready.

SDK retry controls were checked against the official Python BigQuery
[Client reference](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.client.Client)
and [QueryJob reference](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.job.QueryJob).
