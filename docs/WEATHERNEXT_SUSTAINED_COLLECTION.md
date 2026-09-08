# WeatherNext 3 sustained collection and first-month verification

This document is a **source-only readiness contract**. It does not authorize Google Cloud/BigQuery access, production SQLite writes, private runtime scheduling, RPi5 changes, credentials/IAM changes or Analytics Hub link mutations.

Canonical machine contract: `deploy/weathernext-sustained-collection.json`.

Prerequisite source contract: `deploy/weathernext-first-access.json` / `docs/WEATHERNEXT_FIRST_ACCESS.md`.

## Lifecycle

After a separately authorized first-access canary and first real snapshot, the collection lifecycle is explicit:

```text
access_ready
  -> snapshot_admissible
  -> collecting
  -> degraded -> collecting
  -> version_boundary -> collecting
  -> sample_insufficient -> collecting
  -> first_month_ready
```

Transitions are evidence-driven. Missing/pending WeatherNext data is never represented by fabricated values.

`first_month_ready` is a verification-readiness state, not proof that a real month of WeatherNext data already exists.

## Canary -> immutable snapshot admission

`validate_snapshot_admission(...)` accepts only the already-sanitized first-access evidence from Issue #22 plus WeatherNext runs whose provenance validator passes.

Admission requires:

- exact canary init match;
- current schema fingerprint;
- one WeatherNext model version only;
- complete 0.05° station + 0.1° surface products (or an explicit combined surface);
- `mean/p10/p25/p50/p75/p90` provenance;
- immutable revision/idempotency semantics;
- 60-minute accumulation metadata for `precipitation_1h`.

The returned envelope says only `snapshot_admissible`. It sets `production_write_performed=false` and requires a separate exact `production_sqlite_forecast_snapshot_write` authorization.

## Sustained collection planning

Network-free source planning:

```bash
python -m rozkalns_weather.weathernext_collection plan \
  --now <UTC_TIMESTAMP> \
  --limit 24 \
  --known-init <UTC_INIT_ALREADY_PRESENT>
```

The planner uses target-disseminated WeatherNext init candidates and preserves both run classes:

- `interim_48h`: hourly initialization, 48-hour forecast horizon;
- `synoptic_360h`: `00/06/12/18 UTC`, 360-hour forecast horizon.

Known init times are removed from the plan. The logical dedupe identity is:

```text
provider + model_version + init_time_utc + location_id + source_surface
```

Planning never contacts BigQuery and never installs/enables a scheduler.

## Missing-run and latency ledger

Expected runs are classified as one of:

- `expected` — target dissemination has not arrived yet;
- `target_disseminated` — target time passed but the bounded latency grace window is still open;
- `retrieved` — a defensible retrieval receipt exists;
- `missing` — target time + grace passed without retrieval;
- `delayed` — explicitly classified ordinary publication latency;
- `superseded` — a later accepted revision/state supersedes an operational expectation without deleting history.

Permission, linked-dataset, schema and cost-cap failures are not rewritten into `delayed`.

Recovery planning is bounded to at most 168 hours of age and 24 init times per plan. It only emits a plan; real historical BigQuery reads and production corpus writes each remain separately authorized mutation classes. There is no automatic cleanup or hidden retry.

## Model/schema boundaries

Collection keeps both `model_version` and schema fingerprint first-class. Any change creates `version_boundary` and stops metric pooling until an explicit adapter/version decision is made.

Current source support is `WeatherNext 3.0.0`. WeatherNext 2, WeatherNext Gen/Graph, an unknown future major version, or an unexpected schema is never silently coerced into the current WeatherNext 3 metric period.

## Freshness and provider health

Sanitized health evidence keeps three timestamps distinct:

1. `expected_available_at_utc` — documented dissemination target;
2. `observed_publication_at_utc` — only when defensibly observed upstream;
3. `retrieved_at_utc` — when this project retrieved the run.

The source helper can report expected-vs-observed publication lag, retrieval lag, freshness age and consecutive missing runs. Two consecutive missing runs enter `degraded`; a later successful retrieval with zero consecutive missing runs is `recovered_or_healthy`.

Health evidence must not expose Google project/dataset identity, credentials, home coordinates, SQL, filesystem paths or raw logs.

## First-month measured verification

Measured first-month eligibility is only for logical location `station_10416` with truth `DWD WMO 10416`.

The eligibility helper:

- intersects WeatherNext samples with explicit common comparison valid-times;
- groups by `model_version` and lead bucket;
- reports explicit `n` and `sample_confidence`;
- emits MAE/RMSE/bias only for slices with `n >= 30`;
- keeps insufficient slices explicit rather than fabricating confidence;
- excludes `home` from measured station accuracy.

A month may therefore remain `sample_insufficient` even though collection is technically healthy.

## WeatherNext summary-statistic calibration

For `mean/p10/p25/p50/p75/p90`, source verification supports:

- p10-p90 empirical coverage and mean width;
- p25-p75 empirical coverage and mean width;
- p50 MAE and bias;
- strict quantile monotonicity validation.

`precipitation_1h` requires a 60-minute accumulation window.

WeatherNext summary quantiles do **not** imply precipitation event probability. Brier/reliability from a probability and full-ensemble CRPS remain unavailable unless a defensible genuine probability/member source is later added.

## Sanitized first-month evidence

`build_first_month_evidence(...)` / `validate_first_month_evidence(...)` are for aggregate evidence only. Example validation surface:

```bash
python -m rozkalns_weather.weathernext_collection validate-evidence \
  < sanitized-first-month-evidence.json
```

Allowed content includes aggregate model-version/run-class/lead-bucket sample metrics, freshness counts, quantile calibration summaries and sanitized notable-miss summaries.

Forbidden content includes:

- Google project or linked-dataset IDs;
- credentials/tokens/service-account material;
- exact home coordinates;
- SQL containing private coordinates;
- private host/database/filesystem paths;
- raw provider payloads or raw logs.

The validated payload always keeps:

```text
publication_allowed=false
terms_recheck_required_before_publication=true
weather_warning_authority=false
```

WeatherNext real-time data remains private/restricted according to the applicable upstream terms. DWD remains the official severe-weather warning authority in Germany.

## Exact later gate A — recurring private BigQuery collection

Before enabling any recurring real WeatherNext collection, freshly bind all fields below in one explicit owner authorization:

```text
allowlist_approved_evidence=<fresh private evidence>
weather_sha=<reviewed merged exact SHA>
weather_exact_sha_ci=<fresh required-check evidence>
auth_method=<runtime-only ADC/service identity>
google_project=<private runtime binding>
linked_dataset=<private runtime binding>
linked_dataset_location=<fresh private evidence>
schema_fingerprint=<fresh observed + reviewed expected binding>
supported_model_version=3.0.0
run_classes=interim_48h,synoptic_360h
collection_cadence=hourly planner
maximum_bytes_billed_per_query=<explicit cap>
query_scope=<station_10416 and any separately authorized private-home scope>
dedupe_identity=provider+model_version+init+location+surface
missing_run_latency_grace_minutes=90
recovery_max_age_hours=168
recovery_max_inits_per_plan=24
scheduler_target=<exact runtime scheduler identity>
mutation_classes=<read_only_private_bigquery + exact scheduler/runtime class if enabled>
verification=<provider health/freshness + no duplicate init + privacy-safe evidence>
failure=<STOP on permission/schema/link/cost/version drift; no undeclared retry or cleanup>
rollback=<scheduler/application semantics only; no implicit corpus delete/restore>
```

Credential/IAM/Analytics Hub mutation is not implied by this gate and must be named separately if ever required.

## Exact later gate B — production SQLite first-month accumulation

Before allowing real WeatherNext forecast rows to accumulate in production SQLite, freshly bind:

```text
weather_sha=<reviewed merged exact SHA>
weather_exact_sha_ci=<fresh required-check evidence>
production_sqlite_target=<exact trusted runtime DB identity>
validated_snapshot_admission=<sanitized fingerprint/evidence>
location_scope=station_10416[,home only if separately authorized]
model_version=3.0.0
schema_fingerprint=<current accepted fingerprint>
run_classes=interim_48h,synoptic_360h
immutable_revision_and_idempotency=true
truth_scope=DWD_WMO_10416_for_measured_accuracy
first_month_min_samples_per_version_lead_bucket=30
verification=<corpus integrity + revision/dedupe + first-month eligibility + privacy-safe evidence>
failure=<STOP; no undeclared delete/restore/cleanup>
rollback=<application rollback never implies SQLite rollback>
```

This gate does not authorize backup/restore, destructive migration or private scheduler activation unless those classes are explicitly added and separately valid under the current trust-boundary policy.

## Source-only completion boundary

Merging this readiness contract may prove that sustained collection and first-month verification are deterministic and fixture-tested. It cannot prove:

- WeatherNext allowlist approval;
- successful real BigQuery access;
- a first real WeatherNext snapshot;
- recurring collection enabled on RPi5;
- any production WeatherNext corpus rows;
- a completed month of real observations/forecasts;
- measured WeatherNext superiority or any other empirical ranking.

Those claims require fresh external/LIVE/data evidence.
