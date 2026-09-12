# Private home + WeatherNext runtime activation

Issue #52 prepares the **source-side eligibility contract** for a later private-home + WeatherNext runtime. It does not activate runtime, credentials, BigQuery access, production data writes, scheduler state, Cloudflare or RPi5 services.

Canonical machine contract: `deploy/private-runtime-activation.json`.
Validator: `rozkalns-weather private-runtime-activation-validate`.

## Location semantics

`station_10416` remains the measured verification location and uses DWD WMO 10416 observation truth. Private `home` is forecast-display only. A configured private home point must not be described as measured home accuracy until a separate defensible home observation-truth contract exists.

Exact `HOME_LAT` / `HOME_LON` values are runtime-only. GitHub evidence contains only `coordinates_present=true|false` plus the requirement that exact coordinates are not exposed.

## WeatherNext eligibility

Private runtime eligibility requires all of the following sanitized evidence at the same preflight boundary:

- runtime mode is `private-research`;
- the home coordinate pair is present at runtime but not exposed in evidence;
- Google authentication and project/dataset configuration are present, with no credential material exposed;
- WeatherNext private access is freshly verified through the reviewed first-access contract;
- provider/model identity is `weathernext3` / `WeatherNext 3` / `3.0.0`;
- the schema fingerprint matches the current repository WeatherNext required schema contract;
- at least one accepted WeatherNext snapshot exists with complete provenance, both `0p05` + `0p1` product surfaces and exact `mean/p10/p25/p50/p75/p90` statistic identity;
- production schema, station truth, public forecast corpus and immutable history prerequisites are already ready;
- DWD remains the only official severe-weather warning authority.

The validator accepts only a closed sanitized JSON schema. Unknown fields fail closed. Private coordinate/project/dataset/credential/SQL/path/log keys are rejected rather than redacted after ingestion.

## Example sanitized evidence

Values below are synthetic identities only; they are not real WeatherNext observations or private configuration.

```json
{
  "schema_version": 1,
  "source_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "checked_at_utc": "2026-09-12T20:00:00Z",
  "runtime_mode": "private-research",
  "home": {
    "coordinates_present": true,
    "exact_coordinates_exposed": false,
    "forecast_display_enabled": true,
    "measured_home_accuracy_claimed": false
  },
  "credentials": {
    "google_auth_present": true,
    "project_dataset_config_present": true,
    "credential_material_exposed": false
  },
  "weathernext_access": {
    "verified": true,
    "state": "canary_ready_for_snapshot",
    "verified_at_utc": "2026-09-12T19:30:00Z",
    "provider": "weathernext3",
    "model_name": "WeatherNext 3",
    "model_version": "3.0.0",
    "schema_fingerprint_sha256": "<current public schema fingerprint>"
  },
  "accepted_snapshot": {
    "present": true,
    "provenance_complete": true,
    "provider": "weathernext3",
    "model_name": "WeatherNext 3",
    "model_version": "3.0.0",
    "schema_fingerprint_sha256": "<same current public schema fingerprint>",
    "product_surfaces": ["0p05", "0p1"],
    "statistics": ["mean", "p10", "p25", "p50", "p75", "p90"],
    "snapshot_identity_sha256": "<sanitized immutable snapshot identity>",
    "real_values_exposed": false
  },
  "production_corpus": {
    "schema_ready": true,
    "station_10416_truth_ready": true,
    "public_forecast_corpus_ready": true,
    "immutable_forecast_history_ready": true
  },
  "ui_safety": {
    "station_measured_accuracy_location_id": "station_10416",
    "home_display_role": "forecast_only",
    "official_warning_authority": "DWD",
    "model_warning_authority": false
  },
  "authority": {
    "live_authority_granted": false,
    "production_data_authority_granted": false,
    "credential_mutation_authority_granted": false,
    "runtime_mutation_performed": false
  }
}
```

A `PASS` from this validator means only that the sanitized source contract is coherent enough to ask for the later exact owner gates. It is not evidence that any private runtime is deployed or healthy and it grants no authority.

## Exact future owner gates

The future work remains deliberately split by mutation class.

1. **Private config / credentials gate** — exact target host; runtime-only HOME coordinate pair; Google authentication and linked dataset configuration presence; no secret values copied to GitHub. Any `.env`, credential, IAM or filesystem permission change is a separately authorized mutation.
2. **Private BigQuery read gate** — exact reviewed Weather source SHA + exact-SHA CI; exact WeatherNext first-access contract; fixed bounded query/cost envelope; verified auth/runtime identity; no production SQLite write authority implied.
3. **Production WeatherNext snapshot/corpus write gate** — exact target database/corpus; accepted provenance; immutable snapshot identity; explicit write scope, verification and recovery semantics. A successful read/canary does not grant this gate.
4. **RPi5 runtime deploy/restart gate** — exact trusted `rozkalnsandris/RPi5_main` boundary, reviewed release/source identity, target, baseline, mutation list, verification and rollback semantics. Source merge never grants this gate.
5. **Private recurring scheduler gate** — exact systemd/timer or equivalent identities and bounded cadence after collection prerequisites are satisfied. It is not activated by this source package.

Cloudflare/network changes remain outside Issue #52 and need their own exact authority if ever required.

## Fail-closed behavior

Missing coordinate presence, missing auth/config presence, stale access evidence, model/schema drift, absent accepted snapshot provenance, missing production-corpus prerequisites, home-accuracy mislabeling, DWD warning-authority drift, sensitive evidence fields or attempted authority expansion all prevent readiness.

No automatic retry, secret discovery, runtime repair, data repair, deploy, restart, scheduler enable, rollback or alternate mutation path is provided by this source contract.
