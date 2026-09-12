# WeatherNext 3 first-snapshot admission hardening

This is a **source-only** successor gate layered on the existing WeatherNext first-access and sustained-collection contracts. It does not query BigQuery, write SQLite, use private credentials, enable runtime scheduling or expose home coordinates.

Canonical machine contract: `deploy/weathernext-first-snapshot-admission.json`.

## Purpose

Issue #24 already established canary-to-snapshot admission and the separation between source readiness and production SQLite mutation. This contract tightens that boundary before the first real WeatherNext 3 snapshot can be written:

- exact validated first-access canary evidence is mandatory;
- the candidate schema fingerprint must exactly match the canary schema fingerprint;
- WeatherNext provider/model/version/init/valid/lead/statistic provenance must pass the existing validators;
- exactly one `0p05` and one `0p1` candidate run are admitted, unless a future explicit combined surface is provided as the only run;
- every variable/valid-time identity must contain the complete `mean/p10/p25/p50/p75/p90` statistics matrix;
- malformed temporal provenance, stale candidates and duplicate snapshot identities fail closed;
- output is a privacy-safe write plan, never a write.

WeatherNext remains research output. DWD remains the official severe-weather warning authority in Germany.

## Explicit freshness envelope

The gate does not invent a hidden freshness threshold. The caller must explicitly bind:

```text
admission_time_utc=<UTC timestamp>
maximum_candidate_age_hours=<1..48>
```

Each candidate retrieval timestamp must be:

1. on or after its model init;
2. on or before `admission_time_utc`;
3. no older than the explicitly supplied candidate-age bound.

This makes the stale-snapshot decision reproducible and owner-reviewable instead of burying an operational threshold in code.

## Deterministic immutable identity

The admission fingerprint is SHA-256 over public-safe semantic identity:

```text
provider
+ model_version
+ location_id=station_10416
+ selected_init_time_utc
+ schema_fingerprint
+ sorted semantic run hashes
```

A semantic run hash includes model/source-surface identity and the normalized forecast value identities/content. Retrieval receipt time is intentionally excluded so re-reading the same immutable provider snapshot is idempotent. `raw_payload_hash` is included when present so a defensible provider-payload revision remains visible.

The caller supplies already-known admitted fingerprints through `existing_admission_fingerprints`. If the candidate fingerprint already exists, the gate returns `SNAPSHOT_IDENTITY_DUPLICATE` instead of producing another write plan.

This does not delete or overwrite earlier revisions. Existing SQLite immutable/revision semantics remain authoritative.

## Statistics completeness

The existing WeatherNext provenance validator confirms the supported statistic vocabulary. The hardening gate additionally verifies completeness **per variable and valid time**, not just across the run as a whole.

Each admitted identity must contain exactly:

```text
mean, p10, p25, p50, p75, p90
```

Duplicate `(valid_time, variable, statistic, accumulation_window)` identities are rejected. `precipitation_1h` continues to require the existing 60-minute accumulation semantics.

## Stable blocking reasons

The source gate uses stable reason codes:

- `CANARY_EVIDENCE_INVALID`
- `SCHEMA_FINGERPRINT_MISMATCH`
- `MODEL_PROVENANCE_MISMATCH`
- `TEMPORAL_PROVENANCE_INVALID`
- `SNAPSHOT_STALE`
- `STATISTICS_MATRIX_INCOMPLETE`
- `VALUE_IDENTITY_DUPLICATE`
- `PRODUCT_SURFACE_DUPLICATE`
- `SNAPSHOT_IDENTITY_DUPLICATE`

No reason automatically triggers a retry, alternate dataset, credential change, schema coercion, cleanup or write.

## Privacy-safe write plan

`validate_first_snapshot_admission(...)` returns only aggregate/admission evidence such as:

- selected init;
- accepted model version;
- schema fingerprint;
- snapshot admission fingerprint;
- product-surface identities;
- run count;
- explicit freshness bound and oldest retrieval age;
- validation booleans;
- required mutation class.

It does **not** include WeatherNext forecast values, SQL, Google project/dataset IDs, credentials, private paths, home coordinates or raw logs.

The successful state is:

```text
snapshot_write_plan_ready
```

and always contains:

```text
requires_exact_private_live_data_authority=true
production_write_performed=false
```

## Later production gate

A successful source write plan is not production authority. Before a real first snapshot write, the owner gate must freshly bind at minimum:

```text
weather_sha=<current reviewed merged SHA>
weather_exact_sha_ci=<fresh required-check evidence>
validated_first_access_canary=<fresh sanitized evidence>
candidate_schema_fingerprint=<exact matched fingerprint>
snapshot_admission_fingerprint=<not already present>
admission_time_utc=<exact UTC timestamp>
maximum_candidate_age_hours=<explicit 1..48 bound>
production_sqlite_target=<exact trusted target>
mutation_class=production_sqlite_forecast_snapshot_write
verification=<immutable/idempotency/corpus postconditions>
failure=<STOP; no undeclared retry/cleanup/alternate mutation>
rollback=<no implicit delete/restore>
```

Real BigQuery access, credential/IAM changes, Analytics Hub link changes, RPi5/runtime changes and production SQLite writes remain separate exact owner gates under the current trust-boundary policy.
