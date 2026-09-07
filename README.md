# rozkalns_weather

Privāts weather dashboard + forecast-verification projekts Dortmund-Wickede apkārtnei ar **WeatherNext 3** kā `primary_research` modeli.

Galvenais cikls:

```text
forecast snapshot -> observation -> verification -> WeatherNext comparison
```

WeatherNext 3 nav warning authority. Severe-weather brīdinājumos Vācijā autoritatīvs avots ir **DWD**.

## Benchmark metodika

Projektā ir divi atšķirīgi lokācijas režīmi:

- `station_10416` — publiska DWD Dortmund/Wickede WMO 10416 reference location. Šeit tiek veikta **mērīta accuracy verifikācija** pret DWD observations.
- `home` — privāts runtime-only punkts. Šeit tiek glabātas un salīdzinātas prognozes, bet tās netiek sauktas par izmērītu home accuracy, kamēr nav home observation truth avota.

WeatherNext 3 corpus glabā gan 00/06/12/18 UTC `synoptic_360h`, gan interim hourly `interim_48h` runus. BigQuery 0.05° station-head temperatūra/dew point un 0.1° surface lauki saglabā `mean/p10/p25/p50/p75/p90`, init/retrieval/valid/lead/model-version provenance.

ICON-D2, ECMWF IFS HRES un AIFS benchmarkam izmanto Open-Meteo **Single Runs**, nevis retrieval-hour proxy. Upstream init un API availability metadata tiek glabāti atsevišķi.

Deterministisks precipitation amount (`mm`) un precipitation probability ir atšķirīgas quantities. Brier Score tiek aprēķināts tikai tad, ja corpus tiešām satur probability event forecast; probability netiek izdomāta no deterministic mm vai WeatherNext kvantilēm.

## Privacy

Precīza mājas adrese, `HOME_LAT`, `HOME_LON`, credentials un Cloudflare secrets repo netiek commitoti. `.env` ir runtime-only.

## CLI

```bash
rozkalns-weather ingest-public
rozkalns-weather ingest-weathernext
rozkalns-weather smoke-public
rozkalns-weather corpus-stats
rozkalns-weather corpus-check
rozkalns-weather diagnose-weathernext
rozkalns-weather report-monthly --month YYYY-MM
```

Mandatory CI ir fixture-driven un network-independent. `smoke-public` ir operatora izvēles read-only live contract check.

## API / PWA

`/api/current` rāda DWD 10416 reference observation, `/api/hourly` un `/api/daily` rāda private-home forecast comparison, bet `/api/verification/*` ir station-location matched benchmark. Combined weighting joprojām ir bloķēts līdz pietiekamam corpus.

## Deployment

`Dockerfile`, `deploy/` un `docs/OPERATIONS.md` ir source-level deploy preparation. RPi5, systemd/Docker, Cloudflare, credentials un runtime mutation prasa atsevišķu LIVE autorizāciju.

## Dokumentācija

- `docs/BENCHMARK_METHODOLOGY.md`
- `docs/WEATHERNEXT3.md`
- `docs/VERIFICATION.md`
- `docs/ROADMAP.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/OPERATIONS.md`
