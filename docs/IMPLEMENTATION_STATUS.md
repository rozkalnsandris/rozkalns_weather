# Implementation status

Šis fails sasaista roadmap ar reālo source state pēc AUTO-FULL #5.

## Gatavs source līmenī

- FastAPI application + privacy-safe provider metadata.
- SQLite tables + migration helper + immutable `forecast_runs` / `forecast_values` triggers.
- Runtime-only `HOME_LAT` / `HOME_LON`.
- DWD MOSMIX-L `10416` KMZ parser/adapter ar provenance un unit normalization.
- DWD WMO `10416` observation adapter caur Bright Sky/DWD Open Data.
- ICON-D2, ECMWF IFS HRES un ECMWF AIFS adapters caur Open-Meteo, saglabājot upstream model identity.
- `/api/hourly` provider series un provider freshness state.
- WeatherNext 3 BigQuery query builder 0.05° + 0.1°, schema probe, `mean/p10/p25/p50/p75/p90`, current dissemination-latency model un live adapter contract.
- Shared normalized variable semantics.
- Verification v1: temperature MAE/RMSE/bias, lead buckets, rolling window, model-version dimension un p10–p90 coverage.
- Mobile-first PWA skeleton: Overview / Models / Accuracy / Warnings-Radar.
- DWD warnings/radar transport adapters, DWD authority explicit.
- Docker/systemd deployment templates un operator guide.

## Ārējie/live blockeri

1. WeatherNext real-time allowlist joprojām jāapstiprina Google pusē.
2. `HOME_LAT` / `HOME_LON` jāievada tikai privātajā runtime.
3. Google Cloud project/dataset un credentials jāuzstāda tikai privātajā runtime.
4. RPi5 deployment + Cloudflare private access ir atsevišķs LIVE gate.
5. Accuracy skaitļi kļūst nozīmīgi tikai pēc tam, kad ir uzkrāts reāls forecast + observation corpus.

## WeatherNext fair-comparison piezīme

WeatherNext saglabā upstream `init_time` no BigQuery. Open-Meteo current forecast API ne vienmēr dod stabilu upstream init timestamp katrā response; tādēļ V1 adapters to skaidri marķē ar `init_time_quality=retrieval_hour_proxy`. Precīzai run-to-run analīzei nākamais uzlabojums ir izmantot Open-Meteo Single Runs/Previous Model Runs vai tiešo provider run metadata.
