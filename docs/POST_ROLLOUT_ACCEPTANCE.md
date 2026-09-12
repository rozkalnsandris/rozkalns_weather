# Post-rollout acceptance and rollback decision

`post-rollout-acceptance-v1` is a source-only validator for sanitized evidence
collected after a separately authorized first public-only RPi5 rollout.

It does not deploy, restart, roll back, restore, delete, mutate SQLite, or create
LIVE authority.

## Invocation

```bash
python -m rozkalns_weather.post_rollout_acceptance \
  --source-sha <EXACT_MERGED_WEATHER_SHA> \
  --release-identity <EXACT_RELEASE_ID> \
  < sanitized-post-rollout-evidence.json
```

The expected source SHA and release identity are supplied independently from the
evidence so stale or mismatched runtime evidence cannot self-assert its own
identity. The trusted target alias is fixed to
`rozkalns-weather-public-rpi5`.

## Required sanitized evidence

The JSON object contains:

- `source_sha`, `release_identity`, `target_alias`;
- endpoint statuses for `/health`, `/ready`, provider health, public API and PWA;
- readiness state and `runtime_mode=public-only`;
- explicit schema state with `implicit_migration_performed=false`;
- persistent storage readiness;
- corpus integrity and regression state;
- per-provider freshness evidence using the existing `provider-freshness-v1`
  states/reason codes.

Do not include private host paths, `HOME_LAT`, `HOME_LON`, credentials/tokens,
raw logs, database paths or environment contents. Such evidence is rejected
before evaluation and rejected values are not copied into the result.

## Result states

- `PASS` — identity, service/readiness, schema/storage, corpus and public-provider
  evidence are coherent and public providers are fresh.
- `WARN` — core acceptance passes but one or more public providers are
  `lagging`, `degraded`, `stale`, `error`, `unknown` or `not_ingested`.
  Provider degradation stays isolated and does not by itself erase healthy
  provider evidence.
- `BLOCKED` — source/release/target drift, endpoint/readiness failure,
  schema/storage failure, corpus integrity/regression failure, missing provider
  evidence, malformed/private evidence, or WeatherNext safety drift.

WeatherNext 3 is not required for the public-only runtime. If present in
evidence it must remain `required_for_runtime=false` and
`values_fabricated=false`.

## Rollback decision semantics

The validator only emits decision inputs.

`rollback_decision_inputs.application` is a candidate only for application
identity/reachability/readiness failures. It never authorizes rollback.

`rollback_decision_inputs.production_corpus` is separate and becomes a candidate
only when corpus integrity/regression evidence requires explicit data recovery
consideration. Application rollback never implies SQLite/corpus rollback.
Automatic restore/delete are always false.

After any actual LIVE mutation has started, a health regression, unexpected
state, drift, timeout or ambiguity requires STOP and a fresh exact LIVE
authorization before retry/restart/application rollback. Any production corpus
restore/delete additionally requires a separate exact LIVE/data authorization.

A `PASS` or `WARN` result is verification evidence only. It grants no deploy,
retry, restart, rollback, restore, delete or production-data authority.
