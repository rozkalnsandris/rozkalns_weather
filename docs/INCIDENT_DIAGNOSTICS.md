# Incident diagnostics v1

`incident-diagnostics-v1` is the privacy-safe, read-only incident triage envelope for `rozkalns_weather`.

It composes existing source contracts rather than inventing a second health model:

- runtime configuration: `runtime-config-v1`;
- application/schema/storage readiness: `readiness_payload`;
- public provider freshness and ingest isolation: `provider_health`;
- corpus integrity: `Database.corpus_integrity()`.

The frozen machine contract is `contracts/incident-diagnostics-v1.json`.

## States

- `PASS`: config, schema/readiness and corpus evidence are healthy and no provider degradation is present.
- `WARN`: the application remains diagnosable but one or more providers are stale, unavailable, locally failing or not yet ingested, or config has a non-blocking warning.
- `BLOCKED`: config readiness, database/schema/application readiness or corpus integrity prevents a healthy runtime claim.
- `ERROR`: the diagnostics evidence itself is malformed, has an invalid source identity or contains material that is not GitHub-safe.

Provider incidents are deliberately isolated. A single provider's upstream/transport failure does not hide healthy providers and is not mislabeled as a local ingest failure. `SOURCE_DATA_STALE` is also kept distinct from an upstream outage.

## Privacy boundary

The bundle contains classifications and presence/readiness evidence only. It must not contain:

- `HOME_LAT` / `HOME_LON` or other exact private coordinate values;
- credentials, tokens, authorization material or secret-bearing URLs;
- private database/filesystem paths;
- raw logs, tracebacks or raw diagnostic detail;
- private/raw payloads.

Rejected values are never echoed back. Corpus integrity output is reduced to `checked`, `ok` and `error_count`; raw integrity errors are not emitted. Provider `detail` is never emitted.

The bundle always reports that LIVE authority, production-data authority and automatic recovery authority are false.

## Source-side use

The collector is available without adding another application mutation path:

```text
python -m rozkalns_weather.incident_diagnostics --source-sha <exact-reviewed-40-char-sha>
```

Exit semantics:

- `0`: `PASS` or `WARN`;
- `3`: `BLOCKED`;
- `4`: `ERROR`.

The command does not initialize or migrate SQLite. With `DATABASE_INIT_MODE=require-existing`, a missing database remains missing; diagnostics reports the schema/readiness blocker instead of creating a file.

## Future runtime collection

A future runtime incident collection must be separately authorized against the exact target/runtime evidence boundary. The collection itself is read-only and must use the reviewed source SHA and current runtime configuration presence evidence. It must not restart/redeploy services, mutate Docker/systemd, repair the database, retrieve secrets, change Cloudflare/network state or perform automatic recovery.

Recommended runtime sequence after that separate authorization:

1. bind the exact reviewed/deployed weather source SHA;
2. run the diagnostics module once against the current runtime configuration/database;
3. retain only the returned sanitized JSON envelope;
4. STOP on `BLOCKED`/`ERROR` and obtain a new exact mutation authorization before any restart, rollback, repair or recovery action.

DWD remains the authoritative severe-weather warning source; this diagnostics bundle does not change warning authority or fabricate WeatherNext values.
