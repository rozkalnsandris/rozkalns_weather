# Operations — private RPi5 deployment candidate

This is a deploy-ready **source contract**, not LIVE authorization. Source/CI state does not prove RPi5 deployment/runtime state.

## Runtime classes

### Public-only first rollout

The first reviewed RPi5 candidate intentionally works without WeatherNext credentials and without private home coordinates:

```dotenv
WEATHER_RUNTIME_MODE=public-only
DATABASE_INIT_MODE=require-existing
HOME_TIMEZONE=Europe/Berlin
DATABASE_URL=sqlite:///data/weather.db
WEATHER_PORT=9180
```

`HOME_LAT`, `HOME_LON`, Google project/dataset and credentials are not required for the station benchmark in this runtime class. WeatherNext remains explicit `access_pending` and is not fabricated or treated as a startup failure.

Canonical package/contract files:

- `deploy/docker-compose.public.yml`
- `deploy/runtime-descriptor.json`
- `deploy/rollout-readiness.json`
- `deploy/public-ingest-schedule.json`
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md`

### Later private research activation

Private home forecast collection and WeatherNext ingest may later add runtime-only:

```dotenv
HOME_LAT=<private>
HOME_LON=<private>
HOME_TIMEZONE=Europe/Berlin
HOME_LABEL=Dortmund-Wickede
GOOGLE_CLOUD_PROJECT=<private-project>
WEATHERNEXT_BIGQUERY_DATASET=<private-linked-dataset>
```

Google authentication uses Application Default Credentials/service identity outside Git. Service-account JSON, API keys and tokens must never enter the repository.

## Source-level validation

Mandatory CI remains fixture-driven and network-independent:

```bash
python -m pytest
```

Optional read-only public feed preflight:

```bash
rozkalns-weather smoke-public
```

Privacy-safe local readiness/corpus diagnostics:

```bash
rozkalns-weather readiness
rozkalns-weather corpus-check
rozkalns-weather corpus-stats
```

`readiness` does not perform provider network calls and does not implicitly initialize the SQLite schema when the runtime uses `DATABASE_INIT_MODE=require-existing`.

## Deterministic rollout source preflight

Run this only from the exact reviewed repository checkout whose fixed `deploy/` files will later be materialized. It is read-only, network-independent and does not inspect or mutate live RPi5 state:

```bash
rozkalns-weather rollout-preflight \
  --source-sha <EXACT_REVIEWED_40_CHAR_SHA> \
  --start <YYYY-MM-DD> \
  --end <YYYY-MM-DD> \
  --models icon_d2,ecmwf_ifs,ecmwf_aifs \
  --run-hours 0,6,12,18 \
  --recovery-decision <verified_backup_available|owner_accepts_proceeding_without_prewrite_backup>
```

The command validates:

1. fixed target `rozkalns-weather-public-rpi5` and operation `rozkalns-weather.public-runtime-release.v1`;
2. Compose/service/volume/readiness identities and absence of implicit `depends_on`, private env file or home-coordinate wiring;
3. public-only + `require-existing` runtime semantics;
4. DWD truth identity WMO `10416`;
5. exactly ICON-D2, IFS and AIFS at UTC `00/06/12/18`;
6. common benchmark start no earlier than `2026-04-02` and no more than 180 inclusive days;
7. ordered checkpoint prefix and next stage;
8. explicit recovery decision and no automatic restore/delete/cleanup.

The preflight validates only the **form and source contract** of `--source-sha`. It cannot claim GitHub `main` membership, exact-SHA CI, current `RPi5_main` baseline or current RPi5 runtime state; those must be freshly proven at the later LIVE gate.

## Explicit SQLite schema bootstrap

Production-candidate application startup does **not** create the schema. Schema creation is a separately invoked data-write operation:

```bash
rozkalns-weather init-database
```

The fixed Compose identity is `schema-init`. Executing it against production persistent storage requires an exact LIVE/data authorization. Merging source does not authorize it.

The public runtime uses the logical persistent Docker volume `weather_data` mounted at `/app/data`. The application must retain that corpus volume across application replacement. Application rollback never implies database rollback.

## Public archive backfill source contract

`python -m rozkalns_weather.backfill` is deliberately separate from normal runtime ingest. It requires explicit `--database-url`, model/date/run-hour ranges and checkpoint path. The safe planning step is always `--dry-run`:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<non-production-path> forecast \
  --model icon_d2 --start 2026-04-02 --end 2026-04-03 \
  --run-hours 0,6,12,18 --checkpoint <checkpoint.json> --dry-run

python -m rozkalns_weather.backfill --database-url sqlite:///<non-production-path> truth \
  --start 2026-04-02 --end 2026-04-30 \
  --checkpoint <truth-checkpoint.json> --chunk-days 14 --dry-run
```

Forecast backfill is rate-limited and checkpointed atomically after each successful exact run. An identical immutable snapshot is idempotent; a changed upstream payload becomes a new revision rather than overwriting old history.

Historical Single Runs may not expose original publication/availability timestamps; in that case `upstream_available_at_utc` stays `null`. Retrieval time is never fabricated as publication time.

Truth backfill requires explicit WMO station `10416`. Bright Sky is transport only; rows whose source metadata does not confirm `10416` are rejected. Missing values are not imputed.

Reconciliation is read-only against the selected DB:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<path> integrity \
  --model icon_d2 --start 2026-04-02 --end 2026-04-30 --run-hours 0,6,12,18
```

Production/public corpus backfill itself is a data-write/LIVE mutation.

## First public corpus bootstrap state machine

`deploy/rollout-readiness.json` and `deploy/public-ingest-schedule.json` freeze the intended order:

1. `volume_ensure`;
2. `explicit_schema_init` under data-write authority;
3. `readiness_check` / `/ready` schema-storage-privacy proof;
4. `public_smoke_read_only` — optional network smoke, but the stage must still be explicitly checkpointed as passed or skipped;
5. `bounded_dwd_truth_backfill`;
6. `bounded_forecast_backfill`;
7. `corpus_integrity_check`;
8. `enable_recurring_public_ingest` last.

Resume may name only an exact already-completed ordered prefix using repeated `--completed-stage`. A missing middle stage, reordering, implicit stage advance or hidden retry fails closed. The preflight emits a `bootstrap_fingerprint`; later resume evidence must remain bound to the same source SHA, dates/models/run-hours and recovery decision.

Backfill is never an implicit application/container startup side effect. WeatherNext scheduling remains disabled in this public-only phase.

## Public baseline collector and timer handoff

```bash
rozkalns-weather ingest-public
```

It collects the DWD 10416 station benchmark and, only if private home coordinates are configured later, a separate home forecast comparison. Provider failures are isolated.

The machine-readable timer handoff is fixed to:

- timer unit `rozkalns-weather-public-ingest.timer`;
- service unit `rozkalns-weather-public-ingest.service`;
- `OnCalendar=*:0/30`;
- `Persistent=true` with catch-up-after-downtime semantics;
- `RandomizedDelaySec=60` and `AccuracySec=60` contract;
- no overlapping second oneshot plus the application ingest lock as an additional rejection layer;
- timer installation/enablement only after corpus integrity passes.

Actual systemd installation/enable/restart is owned by `RPi5_main` and remains a separate LIVE mutation.

## Readiness / API preflight

```bash
uvicorn rozkalns_weather.app:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8000/api/health/providers
```

`/ready` and `/api/readiness` expose schema version 1 and must not reveal coordinates, credentials or the host/database path. Public-provider network state is visible but isolated from local runtime readiness.

## Privacy-safe post-rollout evidence

A future trusted executor may collect only sanitized evidence and pipe it to:

```bash
rozkalns-weather rollout-evidence-validate < sanitized-evidence.json
```

Required postconditions include exact deployed source SHA identity, target/operation identity, HTTP 200 for `/health`, `/ready` and `/api/health/providers`, ready schema, persistent SQLite storage class, retained `weather_data`, DWD/ICON/ECMWF/WeatherNext provider state presence, `corpus_integrity.ok=true`, and WeatherNext remaining non-required/non-fabricated in public-only mode.

Evidence is rejected if it contains fields for home coordinates, credentials, raw logs, database path, host path or environment payload, or string values exposing `/home/`, `/opt/` or `/root/` paths. The validator emits only a sanitized summary.

## WeatherNext first-access gate

Canonical source contract and detailed runbook:

- `deploy/weathernext-first-access.json`
- `docs/WEATHERNEXT_FIRST_ACCESS.md`

Before any private Google access, the exact reviewed checkout can build a **network-free** one-init canary envelope:

```bash
python -m rozkalns_weather.weathernext_access plan \
  --now <UTC_TIMESTAMP> \
  --hours-limit 6 \
  --max-bytes-billed <EXPLICIT_CAP>
```

This does not read Google credentials, contact BigQuery or inspect/write SQLite. The first canary is pinned to logical benchmark point `station_10416`, not private home coordinates.

After WeatherNext allowlist approval, a **separately authorized private read-only BigQuery gate** may first verify only linked-dataset/schema state:

```bash
python -m rozkalns_weather.weathernext_access preflight \
  --schema-only \
  --max-bytes-billed <EXPLICIT_CAP>
```

Then, still under an exact read-only BigQuery authorization, dry-run both bounded product queries:

```bash
python -m rozkalns_weather.weathernext_access preflight \
  --hours-limit 6 \
  --max-bytes-billed <EXPLICIT_CAP>
```

The dry-run path requires both `weathernext_3_0_0_0p05deg` and `weathernext_3_0_0_0p1deg`, exact `init_time` filtering, selected columns only, one init, <=24 forecast hours and explicit `maximum_bytes_billed`. It emits sanitized bytes/cap evidence but not project/dataset IDs, coordinates or SQL. `cost_cap_rejected` stops before a real canary query.

A real bounded canary query is a later explicitly authorized **read-only private BigQuery** step. Source helper `execute_canary_queries(...)` refuses to run unless matching successful dry-run evidence is supplied. Canary completeness requires non-empty 0.05° station temperature/dew-point output plus non-empty 0.1° surface output. Permission, linked-dataset, schema and cost failures are not masked as data latency.

Documented WeatherNext dissemination targets remain expected timing evidence only. They are stored as `expected_available_at_utc`; `upstream_available_at_utc` remains `null` unless a future source supplies defensible observed publication evidence.

Completed sanitized canary evidence can be validated without provider access:

```bash
python -m rozkalns_weather.weathernext_access validate-evidence < evidence.json
python -m rozkalns_weather.weathernext_access validate-evidence --write-envelope < evidence.json
```

The second command only proves `first_snapshot_write_eligible`; it performs no database write. The first actual snapshot remains a distinct `production_sqlite_forecast_snapshot_write` mutation requiring separate exact private LIVE/data authority. Only after that authority may the runtime write a real WeatherNext run and then use corpus integrity/stats checks.

Legacy `rozkalns-weather diagnose-weathernext` remains a diagnostic surface, but it does not replace the first-access dry-run/cost-cap gate above.

## WeatherNext exact private gate template

Freshly bind the exact class before any real WeatherNext access or write:

```text
allowlist_approved_evidence=<fresh private evidence>
weather_sha=<current reviewed merged exact SHA>
weather_exact_sha_ci=<fresh required-check evidence>
auth_method=<runtime-only ADC/service identity; no credentials in GitHub>
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
failure=<STOP; no undeclared retry/link/credential/data mutation>
rollback=<no implicit SQLite delete/restore/cleanup>
```

Credential/IAM/ADC setup, Analytics Hub subscription/link mutation, private-home coordinates and production SQLite write remain distinct gates. Source merge is not authorization for any of them.

## Trusted RPi5 boundary

`rozkalns_weather` is not autonomous host authority. The adapter contract is documented in `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md`, `deploy/runtime-descriptor.json` and `deploy/rollout-readiness.json`.

Current source-side integration identity:

- target alias `rozkalns-weather-public-rpi5`;
- operation ID `rozkalns-weather.public-runtime-release.v1`;
- execution class `trusted-home-host`;
- authorization class `STRICT`;
- no arbitrary command/path/argv/environment authority from GitHub prose.

`RPi5_main` Issue #408 / PR #409 registered the static operation, #410 / PR #415 added deterministic bootstrap composition, #432 / PR #433 added preactivation, #435 / PR #436 added host-wiring/helper source, #455 added the successor privileged install/activation bridge, and #454 / PR #460 added the source-ready Composite operator. The canonical current checkout contract uses `RPi5_main-weather-public-runtime-install-trusted`; the earlier checkout is historical evidence only. These source interfaces do not prove host installation, runtime enablement or deployment and do not grant LIVE authority. `deploy/rpi5-source-binding.json` is a timestamped source reconciliation only; current `RPi5_main`, queue eligibility, exact-SHA CI and host state must still be freshly read before a real rollout.

## Exact LIVE gate template

Before any RPi5 mutation bind **all** of the following in the exact owner-authorized LIVE envelope:

```text
host=<exact trusted RPi5 host>
target=rozkalns-weather-public-rpi5
weather_sha=<reviewed merged exact SHA>
weather_exact_sha_ci=<fresh required-check evidence>
rpi5_main_sha=<fresh current main SHA>
operation=rozkalns-weather.public-runtime-release.v1
runtime_baseline=<fresh sanitized read-only baseline>
bootstrap_start=<YYYY-MM-DD>
bootstrap_end=<YYYY-MM-DD>
models=icon_d2,ecmwf_ifs,ecmwf_aifs
run_hours_utc=0,6,12,18
truth_station=10416
recovery_decision=<verified_backup_available|owner_accepts_proceeding_without_prewrite_backup>
mutation_classes_and_budgets=<exact frozen set>
verification=<health/readiness/provider/schema/storage/corpus-integrity postconditions>
rollback=<application semantics only; no implicit SQLite restore/delete/cleanup>
```

Read-only preflight must also prove the selected date window is <=180 inclusive days and consistent with the common archive start, and that the current live baseline has not drifted after authorization binding.

Merge does not authorize this step. Separate explicit LIVE authorization is mandatory before deploy/redeploy/restart, Docker/systemd/timer mutation, credentials, Cloudflare, database/schema/corpus data mutation or filesystem permissions.

## Fail-closed failure matrix

`deploy/rollout-readiness.json` freezes failure behavior for application release, volume ensure, schema init, truth backfill, forecast backfill, integrity and schedule activation. Once a future mutation starts, unexpected state means STOP with minimum read-only evidence. There is no undeclared retry, alternate scheduler, automatic repair, volume cleanup, corpus delete or restore.

`deploy/weathernext-first-access.json` separately freezes WeatherNext first-access failures including pending allowlist, permission denied, dataset unlinked, schema changed, cost-cap reject, data latency, empty canary and write-stage failure. No stage silently broadens from read-only Google access to credential/IAM/link or SQLite mutation authority.

## Backup / recovery

Source provides a consistent SQLite backup command:

```bash
rozkalns-weather backup --output <private-backup-path>
```

Source tests additionally verify disposable SQLite backups with read-only `PRAGMA integrity_check`, required-table presence, SHA-256 and size metadata while suppressing the path from output. A future production backup remains separately gated and must not be inferred from source test success.

Backup/restore execution against live storage is itself a separately gated LIVE/data operation. No automatic restore, corpus deletion, cleanup or destructive rollback is declared by the public runtime contract.

Forecast tables remain immutable; provider status/location config is mutable runtime state.

## Monthly WeatherNext evolution report

After real corpus accumulation:

```bash
rozkalns-weather report-monthly --month YYYY-MM
```

The report compares only location-matched `station_10416` truth, separates lead bucket/model version/common timestamps, shows sample warnings and notable misses/wins, and uses only previously verified model events. Release-note events are never invented.

## Authority

- DWD is the official warning authority.
- Bright Sky is a DWD transport/API layer.
- Open-Meteo is a transport layer; ICON-D2/IFS/AIFS upstream identity remains preserved.
- WeatherNext 3 is experimental/research forecast output and is never presented as an official warning.
