# WeatherNext 3 first-access readiness

This document is a **source contract**, not private Google Cloud or production-data authority. `AUTO-RUN FULL` may build and test this contract without making a real BigQuery request. Access approval is established in issue #122; any real access remains a separate exact owner gate. Issue #125 final planning is in `WEATHERNEXT_FINAL_LIVE_PLAN.md`.

Canonical machine contract: `deploy/weathernext-first-access.json`.

## Purpose

The first WeatherNext 3 activation must prove, in order, that the linked BigQuery dataset is accessible, the expected WeatherNext 3 schema is still present, the selected canary query is bounded and within an explicit bytes cap, both required product surfaces return real provider rows, and provenance is complete before any SQLite write is eligible.

The initial canary is intentionally station-only at the canonical measured benchmark `station_05480` / DWD CDC Werl 05480. Private `HOME_LAT` / `HOME_LON` are not needed for the first benchmark snapshot and never enter GitHub evidence. Legacy `station_10416` remains compatibility-only and is not a first-access query target.

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
query_scope=station_05480
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
entrypoint for a later #122 authorization. It fixes the canonical benchmark
`station_05480`, one explicit init, and six forecast hours. The caller supplies
private project/dataset/client in memory through a separately reviewed trusted
binding; never through GitHub.

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
explicit `location_id="station_05480"`; ordinary unbounded ingest/diagnose/fallback
paths are not first-access entrypoints. Production schema must already be ready.

SDK retry controls were checked against the official Python BigQuery
[Client reference](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.client.Client)
and [QueryJob reference](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.job.QueryJob).


## 2026-10-02 access-surface evaluation

The BigQuery contract above remains the canonical description of the **BigQuery** first-access path, but its real-query stage is currently blocked by #122 cost control. The observed clustered-table dry-run values are multi-TiB pre-execution upper bounds and do not justify raising the retained 1 GiB real-query ceiling.

Canonical source-only evaluation: `deploy/weathernext-access-surface-evaluation.json` and `docs/WEATHERNEXT_ACCESS_SURFACES.md`.

- BigQuery real-query path remains blocked; no retry or cap increase is implied.
- Preferred source candidate: **GCS precomputed statistics Zarr**.
- Earth Engine remains a secondary candidate requiring its own Cloud-project/API/quota gate.
- This evaluation does not switch the runtime transport, contact Google, authorize a GCS/Earth Engine probe, or authorize production data writes.

Any GCS implementation must first be fixture-driven and preserve `station_05480`, bounded lead hours, the six existing summary statistics and complete WeatherNext provenance. A later real GCS access remains a separate exact private gate.


## GCS statistics candidate contract

The 2026-10-02 access-surface decision now has a fixture-driven GCS statistics
adapter contract at `deploy/weathernext-gcs-statistics-first-access.json` with
pure source helpers in `weathernext_gcs.py`.

This does not replace the historical BigQuery first-access contract or authorize
Google access. It defines the bounded alternative that may be used by a future
exact private GCS gate:

- canonical location remains `station_05480`;
- one explicit init and one explicit validated operational run-directory token;
- maximum 24 continuous hourly lead steps;
- required six precomputed statistics for the 0.05° station head and selected
  0.1° surface variables;
- nearest-grid point selection with 0–360 longitude handling delegated to the
  later live selector without emitting coordinates;
- source provenance maps to `Google Cloud Storage/Zarr`;
- no full-ensemble bucket fallback, no full-dataset load, no alternate-prefix
  retry and no production SQLite write.

Google documents the operational directory shape as
`<YYYYMMDD_HHhr_XX_preds>/predictions.zarr` but does not define the `XX`
semantics in the access guide. The source contract therefore validates a
separately supplied directory token instead of fabricating one.


## Exact private read-only GCS gate design

The first real GCS attempt is intentionally narrower than the generic 24-hour
adapter contract. Source planning fixes it to one explicit init, the canonical
`station_05480`, and exactly six continuous hourly lead steps.

Machine contract:
`deploy/weathernext-gcs-private-readonly-gate.json`.

The later owner-authorized private gate is ordered as:

1. `run_directory_discovery` — list only the exact
   `<root>/<YYYYMMDD_HHhr_>` prefix with delimiter `/`;
2. require exactly one validated run-directory token and STOP on zero or
   multiple candidates;
3. `zarr_metadata_open` — lazily open only that
   `predictions.zarr` store;
4. `schema_validate` — verify the fixture-driven dimensions, coordinates and
   required statistic variables before values are materialized;
5. `bounded_point_slice` — select the declared variables, one nearest
   `station_05480` point on each declared grid and six lead hours before any
   values are materialized;
6. `provenance_validate` — validate the in-memory WeatherNext run without a
   SQLite write.

The six-hour envelope materializes at most 288 required scalar statistic values:
two station-head fields plus six surface fields, each with six statistics over
six lead hours. This is an output/materialization bound, not a claim about
compressed Zarr chunk transfer size.

Google documents `storage.objects.list` for object listing and
`storage.objects.get` for object reads. Those are the only GCS permissions the
source gate requires. The source contract does not grant or modify IAM and does
not require a billing-project header for the statistics bucket.

The first private gate forbids:

- listing unrelated init prefixes or enumerating the full bucket;
- guessing the undocumented run-directory suffix;
- alternate init/bucket/prefix fallback;
- the full 64-member Requester Pays bucket;
- dataset-level `.load()` or persistent object downloads;
- automatic retry after any private request begins;
- private-home scope;
- credential/IAM/quota changes;
- production SQLite/corpus writes;
- emitting coordinates, credentials or raw WeatherNext values into GitHub
  evidence.

A future exact owner authorization must freshly bind the reviewed Weather
`main` SHA, trusted RPi5 source/runtime SHA, live Weather image revision,
runtime-only credential/config presence, one selected init and this exact
`read_only_private_gcs` class. Source merge alone grants none of those
authorities.

Template:

```text
AUTHORIZE WEATHER #122 READ_ONLY_PRIVATE_GCS FIRST ACCESS —
weather_sha=<fresh reviewed main SHA>;
rpi5_sha=<fresh reviewed trusted runtime SHA>;
live_weather_revision=<must equal weather_sha>;
selected_init_utc=<one exact UTC hour>;
location=station_05480;
hours=6;
bucket=weathernext3_statistics_spatial;
discovery=one exact YYYYMMDD_HHhr_ prefix, delimiter "/", exactly one candidate;
permissions=storage.objects.list,storage.objects.get only;
stages=run_directory_discovery,zarr_metadata_open,schema_validate,bounded_point_slice,provenance_validate;
NO_RETRY; NO_FALLBACK; NO_FULL_ENSEMBLE; NO_HOME_SCOPE;
NO_CREDENTIAL_IAM_QUOTA_MUTATION; NO_PRODUCTION_WRITE;
sanitized evidence only; STOP on permission/auth/schema/discovery/selection/provenance ambiguity.
```

That authorization would permit the bounded private read only. It would still
not authorize persistence of the first WeatherNext snapshot.


## Fixture-driven GCS transport implementation

The GCS gate now has a source transport implementation in
`weathernext_gcs_transport.py`. It remains execution-disabled by authority:
importing or merging the module does not contact Google.

The implementation follows Google's current WeatherNext 3 GCS guidance:
`obstore + zarr + xarray` for Zarr v3 reads. The private runtime dependency
extra is `weathernext-gcs`; these packages are not added to the ordinary public
runtime.

Run-directory discovery intentionally does **not** use a broad Obstore directory
listing. Obstore/object_store prefix semantics operate on path segments, while
the WeatherNext operational suffix is undocumented and the gate needs the
partial segment prefix `YYYYMMDD_HHhr_`. The source therefore uses exactly one
Cloud Storage JSON `objects.list` request with:

- bucket fixed to `weathernext3_statistics_spatial`;
- `prefix=<root>/<YYYYMMDD_HHhr_>`;
- `delimiter=/`;
- `maxResults=5` so more than four candidates fails closed;
- `projection=noAcl` and a narrow response-field selector;
- no pagination, retry or fallback.

The response must contain exactly one validated directory and no direct objects.
A `nextPageToken`, zero candidates, multiple candidates, malformed prefix or
unexpected object causes STOP.

The exact `predictions.zarr` store is then opened through `obstore.GCSStore`
with `retry_config={"max_retries": 0}`, wrapped in
`zarr.storage.ObjectStore`, and opened with
`xarray.open_zarr(..., chunks=None, create_default_indexes=False,
zarr_format=3)`.

The transport requires an explicit credential-provider callback. It never
discovers ambient ADC, reads credential files, accepts a project/dataset
selector, or constructs a billing-project header. The later trusted RPi5
boundary must supply the already-reviewed credential object in memory.

Before forecast values are read, the module validates schema/dimensions,
the exact init, continuous 1..6 hour lead indices, and the nearest declared
0.05°/0.1° grid cells. It then materializes only the 48 required statistic
variables at one point over six hours (288 scalar forecast values total).
It never calls dataset-level `.load()`, writes objects/files/SQLite, or emits
coordinates/raw WeatherNext values in sanitized evidence.

Official references:
- WeatherNext 3 GCS Zarr guide: https://developers.google.com/weathernext/guides/gcs
- Cloud Storage JSON objects.list: https://docs.cloud.google.com/storage/docs/json_api/v1/objects/list
- Xarray open_zarr: https://docs.xarray.dev/en/latest/generated/xarray.open_zarr.html
- Obstore Google Cloud Storage/API docs: https://developmentseed.org/obstore/


## Explicit GCS credential-provider runtime prerequisite

The bounded GCS transport remains callback-only: Weather source still requires
an explicit in-memory `credential_provider` and does not read credential files,
discover ADC, select a project/dataset, or construct a billing-project header.

The trusted RPi5 boundary needs a supported implementation for that callback.
Obstore's documented synchronous provider is
`obstore.auth.google.GoogleCredentialProvider`. Its implementation uses
`google-auth` and `requests`, and when an explicit `credentials=...` object
is supplied it does not need to fall back to `google.auth.default()`.

The private-only `weathernext-gcs` extra therefore declares:

- `google-auth>=2.59.1,<3`;
- `obstore>=0.11.1,<0.12`;
- `requests>=2.34.2,<3`;
- `xarray>=2026.9,<2027`;
- `zarr>=3.4,<4`.

These dependencies are not added to the ordinary public Weather runtime. The
trusted host binder, under a later protected credential/LIVE gate, must construct
the explicit Google credentials object from the already-authorized runtime-only
credential reference and pass
`GoogleCredentialProvider(credentials=...)` into the Weather callback boundary.
Weather source itself must never receive a credential filename or credential
contents.

This source change invalidates the previously generated RPi5 GCS wheelhouse
closure as a complete runtime for first access. After this Weather source is
merged, `RPi5_main` must regenerate its deterministic GCS runtime closure from
the updated `weathernext-gcs` extra before GCS host wiring or private preflight
can be considered Ready.

Current package compatibility evidence on 2026-10-02:

- PyPI `google-auth 2.59.1` supports Python 3.13;
- PyPI `requests 2.34.2` supports Python 3.13;
- Obstore documents that `GoogleCredentialProvider` uses `google-auth` and
  `requests`.

No Google request, credential read, RPi5 package mutation or private access is
performed by this source contract.
