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

## First public corpus bootstrap order

The machine contract in `deploy/public-ingest-schedule.json` freezes the intended order:

1. persistent storage target established;
2. explicit `schema-init` under data-write authority;
3. `readiness` / `/ready` must report schema/storage privacy readiness;
4. optional read-only `smoke-public`;
5. explicit bounded historical DWD truth backfill;
6. explicit bounded deterministic forecast backfill;
7. integrity check;
8. only then enable recurring public ingest.

Backfill is never an implicit application/container startup side effect. WeatherNext scheduling remains disabled in this public-only phase.

## Public baseline collector

```bash
rozkalns-weather ingest-public
```

It collects the DWD 10416 station benchmark and, only if private home coordinates are configured later, a separate home forecast comparison. Provider failures are isolated. The reviewed scheduling contract is every 30 minutes; exact systemd/host installation remains owned by the trusted RPi5 boundary and requires later authority.

## Readiness / API preflight

```bash
uvicorn rozkalns_weather.app:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8000/api/health/providers
```

`/ready` and `/api/readiness` expose schema version 1 and must not reveal coordinates, credentials or the host/database path. Public-provider network state is visible but isolated from local runtime readiness.

## WeatherNext first-live preflight

After allowlist approval and only in private runtime:

```bash
rozkalns-weather diagnose-weathernext --no-point-query
rozkalns-weather diagnose-weathernext
```

Ready means:

1. linked dataset contains `weathernext_3_0_0_0p05deg` and `weathernext_3_0_0_0p1deg`;
2. schema validator finds the expected station-head/surface field paths;
3. query is bounded by `init_time` partition filter and selected columns;
4. point query returns real provider data.

Only after that and separate data authority:

```bash
rozkalns-weather ingest-weathernext
rozkalns-weather corpus-check
rozkalns-weather corpus-stats
```

If the newest hourly dissemination window has passed but data is delayed, collector fallback is only to a prior target-disseminated hourly run. Permission/schema errors are not masked by fallback. WeatherNext values are never fabricated.

## Trusted RPi5 boundary

`rozkalns_weather` is not autonomous host authority. The future adapter contract is documented in `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md` and `deploy/runtime-descriptor.json`.

Candidate future identity:

- target alias `rozkalns-weather-public-rpi5`;
- operation ID `rozkalns-weather.public-runtime-release.v1`;
- execution class `trusted-home-host`;
- initial authorization class `STRICT`;
- no arbitrary command/path/argv/environment authority from GitHub prose.

A separate `RPi5_main` source issue must refresh its current rules/registry and implement/review the static adapter. This weather issue does not modify that repository or register an operation.

## Exact LIVE gate preflight

Before any RPi5 mutation freshly determine:

- exact target host/alias;
- reviewed and merged exact weather source SHA;
- exact-SHA CI/review evidence;
- current trusted-controller/deployed baseline;
- exact static `RPi5_main` operation/adapter identity;
- exact Docker/systemd/data mutation classes and practical budgets;
- current persistent corpus baseline without exposing protected data;
- health/readiness verification;
- explicit rollback semantics and exclusions.

Merge does not authorize this step. Separate explicit LIVE authorization is mandatory before deploy/redeploy/restart, Docker/systemd/timer mutation, credentials, Cloudflare, database/schema/corpus data mutation or filesystem permissions.

## Backup / recovery

Source provides a consistent SQLite backup command:

```bash
rozkalns-weather backup --output <private-backup-path>
```

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
