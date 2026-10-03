# rozkalns_weather

A **simple private weather PWA** for home use in Dortmund-Wickede.

The app answers five practical questions:

1. What is the weather now?
2. What will happen over the next hours and days?
3. How do ICON-D2, ECMWF IFS, ECMWF AIFS and WeatherNext 3 differ?
4. Are there official DWD warnings or nearby precipitation on radar?
5. Which forecast models have actually been more accurate over time?

## Stack

- Python / FastAPI
- SQLite
- plain HTML/CSS/JavaScript PWA
- Open-Meteo transport for ICON-D2 / ECMWF IFS / ECMWF AIFS
- DWD CDC observations for measured verification
- DWD warnings and DWD/Bright Sky radar context
- optional WeatherNext 3 GCS/Zarr research adapter
- Docker + shared SIMPLE-DEPLOY to the private RPi5

## Locations

- `home`: private runtime-only forecast/radar point; coordinates never belong in GitHub.
- `station_05480`: DWD CDC Werl 05480, the single measured verification benchmark.

There is no active legacy 10416/MOSMIX product path in the simple version.

## Product views

- **Overview** — current conditions, next hours, next days, model snapshot.
- **Models** — provider-by-provider forecast comparison.
- **Radar** — DWD warnings plus precipitation radar/nowcast context.
- **Accuracy** — basic measured model error against DWD CDC 05480.
- **Status** — provider freshness and availability.

WeatherNext is optional research data and never blocks the operational home forecast.

## Normal operations

```bash
rozkalns-weather readiness
rozkalns-weather ingest-public
rozkalns-weather corpus-stats
rozkalns-weather corpus-check
```

One-time/admin operations:

```bash
rozkalns-weather init-database
rozkalns-weather backup --output <path>
```

## Deploy

Ordinary application release:

```text
PR -> tests -> MERGE -> owner-authorized SIMPLE-DEPLOY -> GHCR -> RPi5 -> /health + /ready
```

`SIMPLE-DEPLOY` is dispatched only after merge with separate LIVE authorization bound to the exact merged `main` SHA.

No Weather-specific rollout controller, queue, receipt chain or deploy state machine is required.

DB/schema/data changes, secrets, Cloudflare/network and host/systemd changes remain separate explicit gates.

See `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md` and `docs/ROADMAP.md`.
