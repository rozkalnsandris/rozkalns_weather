# Roadmap

## Phase 0 — Bootstrap / access

- [x] Define project goal and WeatherNext 3 priority.
- [x] Define provider roles and privacy policy.
- [x] Define verification methodology.
- [ ] Make repository private if desired; current repository visibility must be checked before committing any private location detail.
- [ ] Submit WeatherNext Data Request / allowlist request.
- [ ] Decide runtime secrets/config mechanism for `HOME_LAT` / `HOME_LON`.

**Exit:** project docs are canonical and WeatherNext access request is in progress or approved.

## Phase 1 — DWD baseline

Implement first working local forecast without waiting for WeatherNext access.

- [ ] Backend skeleton (`FastAPI`).
- [ ] SQLite schema for immutable forecast snapshots and observations.
- [ ] `home` location loaded from environment only.
- [ ] DWD MOSMIX-L 10416 adapter.
- [ ] DWD observation adapter.
- [ ] ICON-D2 point forecast adapter.
- [ ] Provider freshness/status API.
- [ ] Basic 48 h hourly endpoint.
- [ ] Tests for units/timezone/accumulation semantics.

**Exit:** private local API can show DWD forecast + observations with provenance.

## Phase 2 — WeatherNext 3 first-class integration

- [ ] Confirm allowlist access works.
- [ ] Inspect current BigQuery dataset schema.
- [ ] Implement spatial point lookup for home location.
- [ ] Ingest selected surface variables.
- [ ] Ingest `mean`, `p10`, `p25`, `p50`, `p75`, `p90` where available.
- [ ] Store init time, retrieval time, valid time, lead time and model version.
- [ ] Handle dissemination latency correctly.
- [ ] Prevent overwrite of older forecast runs.
- [ ] Add WeatherNext-specific health/freshness diagnostics.
- [ ] Add first WeatherNext vs DWD chart.

**Exit:** WeatherNext 3 forecasts are visible and stored in a form suitable for long-term local verification.

## Phase 3 — ECMWF comparison

- [ ] Add IFS HRES adapter.
- [ ] Add AIFS adapter.
- [ ] Preserve upstream model identity if Open-Meteo is transport layer.
- [ ] Add common variable semantics mapping.
- [ ] Add model comparison view.

**Exit:** WeatherNext 3 can be compared with both traditional NWP and another AI model.

## Phase 4 — Verification engine

- [ ] Join forecast snapshots to DWD observations by valid time.
- [ ] Temperature MAE/RMSE/bias.
- [ ] Lead-time buckets.
- [ ] Rolling 30d/90d metrics.
- [ ] Model version dimension.
- [ ] Precipitation occurrence event definition.
- [ ] Brier Score/reliability pipeline.
- [ ] WeatherNext p10–p90 coverage metrics.
- [ ] Accuracy API.
- [ ] Accuracy UI.

**Exit:** project can answer “which model has actually been more accurate here?” with reproducible metrics.

## Phase 5 — Full private PWA

- [ ] Overview page.
- [ ] Hourly graph.
- [ ] Daily cards.
- [ ] `Combined | DWD | WeatherNext | ECMWF` provider switch.
- [ ] WeatherNext uncertainty band.
- [ ] Freshness/status indicators.
- [ ] Installable PWA.
- [ ] Private remote access design (e.g. Cloudflare Access) — separate runtime authorization required.

**Exit:** practical daily-use weather app on phone.

## Phase 6 — Radar + warnings

- [ ] DWD CAP official warnings.
- [ ] DWD radar ingest/rendering.
- [ ] Home-centered radar view.
- [ ] Warning priority UX.
- [ ] Distinguish observed radar from forecast/nowcast.

**Exit:** app covers forecast + actual precipitation + official severe-weather information.

## Phase 7 — Additional environment data

Optional, only after core forecast comparison is stable.

- [ ] European AQI.
- [ ] PM2.5 / PM10 / NO2 / O3.
- [ ] pollen.
- [ ] UV.
- [ ] sunrise/sunset/daylight/sunshine.

## Phase 8 — Combined forecast

Only after sufficient verified history.

- [ ] Define minimum sample requirement.
- [ ] Calculate provider skill by variable and lead time.
- [ ] Design transparent weighting.
- [ ] Version weights and evaluation windows.
- [ ] Backtest Combined against naive baselines.
- [ ] Keep all original provider lines visible.

**Exit:** Combined forecast demonstrates measurable out-of-sample benefit rather than just averaging models.

## Phase 9 — WeatherNext evolution reports

- [ ] Monthly WeatherNext local skill report.
- [ ] Version-change annotations.
- [ ] Compare new model period vs previous model period.
- [ ] Archive notable misses/wins.
- [ ] Track Google release notes relevant to operational forecast behavior.

This phase is ongoing and directly serves the original reason for creating the project.

## Ordering principle

Do not let radar, AQI, styling or extra providers delay the core loop:

```text
forecast snapshot -> observation -> verification -> WeatherNext comparison
```

That loop is the project’s primary product.
