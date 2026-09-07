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

## Public archive + ensemble benchmark v3

Kamēr WeatherNext 3 private allowlist ir pending, public-data lane var veidot reproducējamu benchmark corpus bez privāta home punkta:

- bounded/resumable exact-run backfill ar explicit model/date/UTC run-hour ranges, `--dry-run`, rate limit un atomic checkpoint;
- common deterministic archive window sākas `2026-04-02`; vecāks IFS history paliek atsevišķs non-common series;
- DWD truth backfill ir stingri pinned uz WMO `10416`; Bright Sky ir tikai transport, missing values netiek imputētas;
- integrity reconciliation rāda expected/present/missing/unexpected runus un revisions, neizmainot immutable snapshotus;
- public ensemble adapters: ICON-D2-EPS, IFS ENS 0.25° un AIFS ENS 0.25° ar control/member identity un short-retention semantics;
- CRPS, interval coverage/width, WIS-style score, precipitation member-fraction probability, Brier un reliability izmanto tikai genuine ensemble input;
- WeatherNext 2 ir tikai `legacy_ai_context`, nekad WeatherNext 3 aizvietotājs un nav strict run-to-run leaderboard modelis, ja exact provenance nav pieejams;
- common-sample leaderboard saglabā comparison mode, lead bucket, model-version boundary, explicit `n` un bootstrap CI tikai pie pietiekama sample (`n >= 30`).

Detalizēts source/runbook: `docs/PUBLIC_BACKFILL_PROBABILISTIC_V3.md`.

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

Public backfill ir atsevišķs source module, lai nejauši nesajauktu to ar parasto runtime ingest:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<path> forecast ... --dry-run
python -m rozkalns_weather.backfill --database-url sqlite:///<path> truth ... --dry-run
python -m rozkalns_weather.backfill --database-url sqlite:///<path> integrity ...
```

Production corpus write joprojām ir atsevišķs LIVE/data gate; source availability nav write autorizācija.

Mandatory CI ir fixture-driven un network-independent. `smoke-public` ir operatora izvēles read-only live contract check.

## API / PWA

`/api/current` rāda DWD 10416 reference observation, `/api/hourly` un `/api/daily` rāda private-home forecast comparison, bet `/api/verification/*` ir station-location matched benchmark. Accuracy v3 UI atdala deterministic/ensemble/legacy provider roles, rāda lead-bucket sample size/confidence un genuine precipitation calibration atsevišķi. Combined weighting joprojām ir bloķēts līdz pietiekamam corpus.

## Deployment

`Dockerfile`, `deploy/` un `docs/OPERATIONS.md` ir source-level deploy preparation. RPi5, systemd/Docker, Cloudflare, credentials un runtime mutation prasa atsevišķu LIVE autorizāciju.

## Dokumentācija

- `docs/BENCHMARK_METHODOLOGY.md`
- `docs/PUBLIC_BACKFILL_PROBABILISTIC_V3.md`
- `docs/WEATHERNEXT3.md`
- `docs/VERIFICATION.md`
- `docs/ROADMAP.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/OPERATIONS.md`
