# Roadmap

Galvenais prioritātes cikls nemainās:

```text
forecast snapshot -> observation -> verification -> WeatherNext comparison
```

## Phase 0 — bootstrap/access

- [x] Project goal, WeatherNext-first priority, privacy un verification methodology.
- [x] Runtime-only home point contract.
- [ ] WeatherNext Data Request / allowlist apstiprināts.
- [ ] Privātajā runtime konfigurēts Google Cloud + home point.

**Exit:** source ir gatavs; live WeatherNext ingest sākas tiklīdz ir access.

## Phase 1 — DWD baseline

- [x] FastAPI backend.
- [x] SQLite immutable forecast store + observations.
- [x] DWD MOSMIX-L 10416 adapter.
- [x] DWD observations adapter WMO 10416.
- [x] ICON-D2 point adapter.
- [x] Provider health/freshness API.
- [x] 48 h hourly API.
- [x] Unit/timezone/immutability/privacy tests.

**Exit:** source gatavs lokālam DWD baseline ingest.

## Phase 2 — WeatherNext 3 first-class integration

- [x] Current BigQuery 0.05°/0.1° table contract + schema probe.
- [x] Runtime home-point spatial lookup.
- [x] Station-head temperature/dew point + 0.1° surface field ingestion contract.
- [x] `mean/p10/p25/p50/p75/p90` support.
- [x] Model/init/retrieval/valid/lead/statistic provenance.
- [x] Dissemination-latency state.
- [x] WeatherNext-specific provider health state (`access_pending`, latency, configured).
- [ ] Live allowlist access verified with real query.
- [ ] First real WeatherNext snapshot stored.

**Exit:** pēc access nav vajadzīgs schema redesign; live query ir vienīgais ārējais gate.

## Phase 3 — ECMWF comparison

- [x] IFS HRES adapter.
- [x] AIFS adapter.
- [x] Upstream model identity preserved when Open-Meteo is transport.
- [x] Shared normalized semantics.
- [x] Model comparison web surface.

## Phase 4 — verification engine

- [x] Forecast ↔ DWD observation exact-hour matching V1.
- [x] Temperature MAE/RMSE/bias.
- [x] Lead-time buckets.
- [x] Rolling 30d/90d API windows.
- [x] Model-version dimension.
- [x] WeatherNext p10–p90 coverage.
- [ ] Precipitation Brier/reliability pipeline after probabilistic rain semantics are validated end-to-end.
- [ ] Larger-sample statistical confidence reporting after corpus exists.

## Phase 5 — private PWA

- [x] Overview.
- [x] Model comparison chart surface.
- [x] WeatherNext first-class research panel.
- [x] Accuracy surface.
- [x] PWA manifest/service worker basics.
- [x] Freshness/status display.
- [ ] Live private deployment on RPi5.
- [ ] Cloudflare Access, if chosen — separate LIVE gate.

## Phase 6 — radar + warnings

- [x] DWD warning API contract (Bright Sky transport; DWD authority explicit).
- [x] DWD radar API contract/metadata surface.
- [x] Observed/radar-nowcast vs model forecast separation.
- [ ] Live UI map rendering validation after private runtime has home coordinates.

## Phase 7 — environment extras

Optional after the core comparison runs reliably:

- [ ] AQI / PM2.5 / PM10 / NO2 / O3.
- [ ] pollen.
- [ ] UV.
- [ ] sunrise/sunset/daylight.

## Phase 8 — Combined forecast

Blocked intentionally until enough verified history exists:

- [ ] minimum sample requirement;
- [ ] skill by provider/variable/lead;
- [ ] transparent/versioned weights;
- [ ] out-of-sample backtest;
- [ ] original provider lines always visible.

## Phase 9 — WeatherNext evolution

Ongoing after live corpus starts:

- [ ] monthly WeatherNext local skill report;
- [ ] version-change annotations;
- [ ] new-vs-old version period comparison;
- [ ] notable misses/wins archive;
- [ ] release-note tracking.
