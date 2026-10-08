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


## WeatherNext one-shot snapshot persistence

After the read-only GCS canary has passed, the ordinary Weather image exposes one
explicit persistence command:

```bash
python -m rozkalns_weather weathernext-gcs-persist --init <exact-UTC-init>
```

This remains an owner-gated admin operation. The command reuses the fixed
read-only Google credential path, requires the existing SQLite schema, reads the
same bounded `station_05480` WeatherNext statistics snapshot, and then writes
one immutable `ForecastRun` plus its values through the normal database
transaction. It does not initialize or migrate the schema, write the private
home location, add retries/fallbacks, or create a second deployment path.

Running this command against the production corpus is a DB/data mutation and
therefore requires a separate exact LIVE authorization. Source readiness alone
does not authorize the write.

## Weather PUBLIC ingress: loopback-only consumer source

The Weather service's consumer Compose publish declaration is explicitly
`127.0.0.1:${WEATHER_PORT:-9180}:8000`. This preserves the configurable
host port and fixed container port while disallowing wildcard interfaces
for the Docker origin. The Cloudflare Tunnel route and its policy are
managed separately by `RPi5_main`, not by this application repository.
The other `public-ingest` job, persistent `weather_data` volume,
health/readiness checks, and immutable-image SIMPLE-DEPLOY interface are
unchanged.

This consumer source change complements the separately reviewed RPi5 host
SIMPLE-DEPLOY target in `rozkalnsandris/RPi5_main#915` / PR #916. The
active host-owned Compose and registry digest must also be reconciled
under that repository's independent merge/authorization rules. Neither
source PR constitutes a production change.

**Runtime remains a separate owner gate.** After both source changes
have been reviewed and explicitly merged, obtain fresh sanitized
Weather-only host preflight evidence: exact deployed identity, Compose
and registry install hash, protected runtime/persistence preservation,
and the approved narrow recovery boundary. Any container reconcile or
recreate needs separate exact LIVE authority; do not perform schema,
database, volume, credentials, shared Tunnel, firewall, DNS or
unrelated-service mutation. Verify `/health` and `/ready`, public
Cloudflare route behavior, and rerun the read-only Phase 7 ingress audit
after an authorized rollout. Keep the recorded Weather wildcard drift
open until a fresh runtime PASS; no automatic retry or rollback.
