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
