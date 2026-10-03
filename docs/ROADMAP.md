# Roadmap

## P0 — simple private weather app

- [x] FastAPI + SQLite
- [x] private home forecast mode
- [x] ICON-D2 / ECMWF IFS / ECMWF AIFS
- [x] DWD current observation
- [x] DWD CDC 05480 verification truth
- [x] DWD official warnings
- [x] radar/nowcast context
- [x] mobile-first PWA
- [x] Overview / Models / Radar / Accuracy / Status
- [x] recurring public ingest
- [x] SIMPLE-DEPLOY application releases

## P1 — finish the useful UI

- [ ] make Radar a polished visual player rather than a technical surface
- [ ] keep mobile interaction fast and clear
- [ ] remove remaining UI wording or controls that expose obsolete project history
- [ ] validate the simple app on the real phone after relevant source changes

## P2 — WeatherNext 3

- [x] source-level bounded GCS statistics/Zarr adapter
- [ ] perform one separately authorized private read-only GCS canary
- [ ] persist real WeatherNext snapshots only after that succeeds
- [ ] collect enough real samples for measured comparison

BigQuery is no longer the active first-access path for the simple app.

## P3 — accuracy

Keep this practical:
- temperature MAE / RMSE / bias;
- lead-time buckets;
- precipitation amount/error where defensible;
- sample count `n`;
- WeatherNext quantile coverage only after genuine WeatherNext data exists.

## Not planned

- project-local deployment controllers/queues;
- large rollout state machines;
- Weighted Combined before enough measured evidence;
- AQI/pollen/UV until the core weather experience is complete;
- publication/research infrastructure that does not improve the private app.
