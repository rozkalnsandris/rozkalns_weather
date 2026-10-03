# Operations

## Daily runtime

The application service reads the existing SQLite database.
A recurring ingest job updates public forecast/observation data.

Useful checks:

```bash
rozkalns-weather readiness
rozkalns-weather corpus-check
rozkalns-weather corpus-stats
```

Run a public ingest:

```bash
rozkalns-weather ingest-public
```

## Database initialization

Initialization is explicit:

```bash
rozkalns-weather init-database
```

Production schema/data mutation remains a separate owner-gated operation. App startup must not silently initialize production storage.

## Backup

```bash
rozkalns-weather backup --output <backup-path>
```

## Application release

Ordinary source releases use the single shared path:

```text
main merge
-> SIMPLE-DEPLOY
-> immutable GHCR image
-> generic RPi5 deployer
-> /health + /ready
```

Do not recreate Weather-specific rollout queues, JIT envelopes, receipts or bootstrap state machines.

## Separate gates

Still require explicit authorization when applicable:
- runtime secrets/credentials;
- HOME_LAT / HOME_LON changes;
- DB/schema/data migration or restore;
- systemd/host/permissions changes;
- Cloudflare/network changes;
- private WeatherNext access.


## WeatherNext one-shot GCS canary

WeatherNext private access is intentionally **not** a second deployment system.
The ordinary Weather image contains the optional GCS runtime. The first
read-only canary uses one ephemeral container and exactly one existing Google
credential file mounted read-only at a fixed in-container path.

After a separate exact LIVE authorization, the operator shape is:

```text
exact Weather image
-> docker run --rm --user 0:0
-> mount one existing credential file at /run/secrets/weathernext-google.json:ro
-> python -m rozkalns_weather weathernext-gcs-canary --init <exact-UTC-init>
-> print sanitized canary evidence only
```

The canary has no binding manifest or credential-directory protocol, no database
volume and no persistence, schema change, credential copy, IAM change, alternate
dataset fallback or automatic retry.
It is fixed to `station_05480`, six forecast hours and the precomputed
WeatherNext 3 statistics GCS/Zarr surface. Any private binding, credential,
schema or transport mismatch fails closed.
