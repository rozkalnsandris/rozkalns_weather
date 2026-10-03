# Architecture

## Principle

Keep the weather product small.

```text
public weather sources ─┐
                       ├─> ingest -> SQLite -> FastAPI -> private PWA
WeatherNext optional ──┘
DWD warnings/radar ---------------------------> PWA
```

## Runtime components

### FastAPI
Serves the PWA and JSON endpoints.

### SQLite
Stores immutable forecast snapshots, observations and provider ingest state. Historical forecasts are retained because measured verification needs the forecast that was actually available at that time.

### Public ingest
One recurring ingest command collects:
- DWD CDC current observations;
- DWD CDC hourly truth for station_05480;
- ICON-D2;
- ECMWF IFS;
- ECMWF AIFS;
- home forecasts when private home coordinates are configured.

### WeatherNext
WeatherNext is optional and separate. The preferred research transport is the bounded GCS statistics/Zarr adapter. It must never block ordinary home weather.

### Warnings and radar
DWD warnings are authoritative. Radar/nowcast is observation context, not a forecast-model warning.

## Locations

`station_05480` is the only measured benchmark.
`home` is the private operational point.

Exact home coordinates stay in runtime configuration only.

## Deployment

Weather consumes shared SIMPLE-DEPLOY. The repository does not own a separate deployment platform.

```text
merge main
-> shared image build
-> immutable GHCR image
-> generic RPi5 pull deployer
-> weather container replacement
-> /health
-> /ready
```

Sensitive runtime/data/host changes remain separately authorized.
