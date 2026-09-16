# Provider availability and retrieval-latency benchmark

Issue #69 adds a deterministic, read-only source contract for measuring public forecast-run availability and retrieval latency without treating documented dissemination targets as observed publication evidence.

## Evidence fields

Each benchmark sample supplies explicit provenance for:

- `provider`, `model_name`, optional `model_version`, and `run_cycle`;
- `init_time_utc` — provider/model run initialization time;
- `expected_available_at_utc` — documented or reviewed expected-availability target;
- `expected_availability_source` — provenance for that target;
- optional `upstream_available_at_utc` — only defensible observed upstream availability evidence;
- optional `upstream_availability_source` — required whenever observed upstream availability is present;
- `ingest_attempt_at_utc` — local collection attempt start;
- `retrieved_at_utc` — completed retrieval timestamp.

`expected_available_at_utc` and `upstream_available_at_utc` are intentionally different fields. Missing observed publication evidence remains `null`; it is never replaced with the documented target or retrieval timestamp.

## Latency dimensions

`provider_latency_report(...)` reports deterministic minute deltas for:

- init → expected availability;
- init → observed upstream availability, when known;
- expected → observed upstream availability, when known;
- expected → retrieval;
- observed upstream availability → local ingest attempt, when known;
- local ingest attempt → retrieval.

Distributions are grouped by exact `(provider, model_name, run_cycle)` identity and expose sample count, p50, p95 and max values. Groups also retain the count of samples with defensible upstream-availability evidence.

## Classification

The benchmark thresholds are source-level comparison thresholds, not claims about provider SLAs:

- observed upstream availability more than 30 minutes after the expected target → `WARN / UPSTREAM_AVAILABILITY_LATE`;
- local ingest attempt more than 30 minutes after observed upstream availability → `WARN / LOCAL_RETRIEVAL_ATTEMPT_LATE`;
- retrieval more than 60 minutes after expected availability → `WARN / RETRIEVAL_LATE`;
- no defensible observed upstream timestamp → `WARN / UPSTREAM_AVAILABILITY_UNOBSERVED`;
- valid evidence inside those bounds → `PASS / LATENCY_WITHIN_BOUNDS`;
- missing benchmark evidence → `BLOCKED / LATENCY_EVIDENCE_UNAVAILABLE`;
- malformed evidence → `BLOCKED / LATENCY_EVIDENCE_INVALID`;
- timezone-naive timestamps → `BLOCKED / LATENCY_TIMESTAMP_NOT_UTC`;
- impossible ordering such as upstream availability after retrieval or local attempt after retrieval → `BLOCKED / TIMESTAMP_ORDER_INVALID`.

A WARN latency classification is not an outage classification.

## Provider-health integration

`provider_health_latency_summary(...)` produces a compact provider-specific latency surface. `classify_public_provider_health(...)` can expose that object through the optional `latency_summary` argument as `latency_benchmark`.

The existing `provider-freshness-v1` state, failure domain and reason code are computed independently. Attaching a latency WARN therefore cannot convert a healthy provider into an outage/error state. Every latency report explicitly carries `outage_claimed=false` and `affects_provider_freshness_state=false`.

## Provenance and privacy boundary

Open-Meteo Single Runs already preserves explicit `ForecastRun.upstream_available_at_utc` when model metadata supplies `last_run_availability_time`; historical samples may legitimately have no observed availability timestamp. The benchmark consumes explicit evidence only and performs no provider polling, network access, host/systemd inspection, database write, production ingest retry, WeatherNext query or LIVE mutation.

The report contains no coordinates, credentials, runtime paths, raw logs or provider payloads.

## Fixture coverage

`tests/test_provider_latency.py` covers normal latency, delayed upstream publication, delayed local retrieval attempt, missing observed publication evidence, unusually late retrieval, timestamp inversion, provider/model/run-cycle grouping and provider-health integration without false outage classification.
