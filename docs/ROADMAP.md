# Roadmap

```text
forecast snapshot -> observation -> verification -> WeatherNext comparison
```

## Phase 0 — access
- [x] WeatherNext-first goal/privacy/methodology.
- [x] Runtime-only home config contract.
- [ ] WeatherNext allowlist approved.
- [ ] Private Google Cloud + home runtime configured.

## Phase 1 — robust public baseline
- [x] FastAPI + SQLite immutable corpus.
- [x] DWD MOSMIX-L 10416 + observations.
- [x] ICON-D2 / IFS / AIFS adapters.
- [x] Ingest orchestration, locking, retry, failure isolation.
- [x] Idempotency/revisions/integrity/stats/backup.
- [x] Public provider smoke tooling.
- [x] Single Runs init provenance and availability metadata contract.

## Phase 2 — WeatherNext 3
- [x] BigQuery 0.05°/0.1° schema/query contract.
- [x] `mean/p10/p25/p50/p75/p90`.
- [x] hourly interim + synoptic run classes.
- [x] dissemination latency/readiness diagnostics.
- [x] station benchmark + optional home collection design.
- [ ] live BigQuery access verified.
- [ ] first real WeatherNext snapshot stored.

## Phase 3 — verification
- [x] station-only location-matched truth join.
- [x] MAE/RMSE/bias + lead buckets + model versions.
- [x] WeatherNext p10–p90 coverage.
- [x] common-case monthly comparison by lead bucket.
- [x] precipitation amount/probability separation.
- [x] Brier/reliability foundation for genuine probability inputs.
- [ ] larger-sample confidence intervals after corpus exists.
- [ ] optional full-ensemble WeatherNext CRPS/Brier via GCS if justified.

## Phase 4 — private PWA
- [x] Overview / Models / Accuracy / Warnings-Radar.
- [x] current DWD station truth clearly labeled.
- [x] home forecast charts/daily cards.
- [x] provider init/freshness states.
- [x] WeatherNext uncertainty surface.
- [ ] private RPi5 deploy.
- [ ] optional Cloudflare Access.

## Phase 5 — DWD safety/radar
- [x] warning lifecycle normalization.
- [x] DWD authority separation.
- [x] radar observed/nowcast contract.
- [ ] live home-centered map validation.

## Phase 6 — WeatherNext evolution
- [x] monthly report generator.
- [x] model-version + lead-bucket dimensions.
- [x] notable misses archive payload.
- [x] release-note hook without fabricated events.
- [ ] first month of real corpus.
- [ ] version-change comparative reports.

AQI/pollen/UV and Combined weighting remain lower priority until enough real corpus exists.
