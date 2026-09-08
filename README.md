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
rozkalns-weather init-database
rozkalns-weather readiness
rozkalns-weather ingest-public
rozkalns-weather ingest-weathernext
rozkalns-weather smoke-public
rozkalns-weather corpus-stats
rozkalns-weather corpus-check
rozkalns-weather rollout-preflight --source-sha <MERGED_SHA> --start YYYY-MM-DD --end YYYY-MM-DD --models icon_d2,ecmwf_ifs,ecmwf_aifs --run-hours 0,6,12,18 --recovery-decision <DECISION>
rozkalns-weather rollout-evidence-validate < sanitized-evidence.json
rozkalns-weather diagnose-weathernext
rozkalns-weather report-monthly --month YYYY-MM
python -m rozkalns_weather.weathernext_access plan --now <UTC_TIMESTAMP> --hours-limit 6 --max-bytes-billed <CAP>
python -m rozkalns_weather.weathernext_access preflight --schema-only --max-bytes-billed <CAP>
python -m rozkalns_weather.weathernext_access preflight --hours-limit 6 --max-bytes-billed <CAP>
python -m rozkalns_weather.weathernext_access validate-evidence < sanitized-first-access-evidence.json
python -m rozkalns_weather.weathernext_collection plan --now <UTC_TIMESTAMP> --limit 24
python -m rozkalns_weather.weathernext_collection validate-evidence < sanitized-first-month-evidence.json
```

`rollout-preflight` ir **source-checkout-only read-only** validators: tas neveic tīkla pieprasījumus, nelasa production runtime un neko nemutē. Tas pārbauda fixed descriptor/Compose/schedule identities, exact 40-char SHA formu, WMO `10416`, exact `icon_d2/ecmwf_ifs/ecmwf_aifs` + `00/06/12/18` scope, ne vairāk kā 180 inclusive dienas, ordered checkpoint prefix un explicit recovery decision. Tas pats neapstiprina, ka SHA patiešām ir current merged `main` vai ka exact-SHA CI ir green — to vēlāk svaigi pierāda GitHub/LIVE gate.

`rollout-evidence-validate` no stdin pieņem tikai privacy-safe pēc-rollout evidence un fail-closed, ja nav `/health`, `/ready`, provider-health, schema/storage/corpus integrity postconditions vai ja evidence satur private path/log/coordinate/credential laukus.

WeatherNext first-access source contract ir `deploy/weathernext-first-access.json` + `docs/WEATHERNEXT_FIRST_ACCESS.md`. Network-free `weathernext_access plan` izvēlas vienu target-disseminated init un bounded forecast-hour/cost envelope. `preflight --schema-only` un dry-run preflight ir paredzēti tikai vēlākai atsevišķi autorizētai private BigQuery read-only pārbaudei; source AUTO-FULL tos neizpilda. Dry-run evidence ir obligāta pirms bounded canary query, un production SQLite first-snapshot write paliek atsevišķa mutation class.

WeatherNext sustained-collection source contract ir `deploy/weathernext-sustained-collection.json` + `docs/WEATHERNEXT_SUSTAINED_COLLECTION.md`. Network-free `weathernext_collection plan` izveido target-disseminated hourly/synoptic init plānu, izmet jau zināmos init un pats neveic BigQuery query, SQLite write vai scheduler activation. Missing-run recovery, model/schema boundary un freshness health ir deterministiski source contracti. Pirmā mēneša mērītā verifikācija paliek tikai `station_10416` common valid-times, atsevišķi pa model version un lead bucket; MAE/RMSE/bias tiek uzskatīti par meaningful tikai pie `n >= 30` attiecīgajā slice. Reāla recurring WeatherNext collection, production corpus accumulation un scheduler activation paliek atsevišķi exact LIVE/data gates.

WeatherNext dokumentētais dissemination target tiek glabāts kā `expected_available_at_utc`, nevis kā novērots publication timestamp. `upstream_available_at_utc` paliek `null`, kamēr upstream nav devis defensible observed publication evidence.

`init-database` ir explicit SQLite write operācija. RPi5 production candidate izmanto `DATABASE_INIT_MODE=require-existing`, tāpēc aplikācijas startup pats neizveido production DB. `readiness` ir privacy-safe un neveic tīkla pieprasījumus vai implicit schema creation.

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

Runtime health/readiness:

- `/health` — process/app liveness + local DB state summary;
- `/ready` and `/api/readiness` — machine-readable schema/storage/provider/privacy readiness contract.

Public-provider failure ir redzama provider state, bet izolēta no citiem provider. WeatherNext `access_pending` nav public-only runtime blocker.

## Public-only RPi5 candidate

Pirmais RPi5 rollout kandidāts ir intentionally public-only un neprasa WeatherNext credentials vai private home coordinates:

- `deploy/docker-compose.public.yml` — fixed application/bootstrap/job service identities;
- `deploy/runtime-descriptor.json` — machine-readable trusted deploy handoff;
- `deploy/rollout-readiness.json` — canonical bounded rollout/state/recovery/evidence/failure contract;
- `deploy/public-ingest-schedule.json` — explicit systemd timer identity, 30-minute cadence, `Persistent=true`, bounded jitter, overlap semantics un enable-last ordering;
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md` — trust-boundary, corpus retention un reviewed `RPi5_main` adapter/bootstrap handoff contract.

Fixed runtime mode ir `WEATHER_RUNTIME_MODE=public-only`; application service izmanto `DATABASE_INIT_MODE=require-existing`. Compose `weather` service nav `depends_on` saites uz schema/backfill jobiem. `schema-init`, historical corpus writes, backup/restore un recurring schedule activation ir redzami atsevišķas mutation classes — tās nav app startup vai application replacement side effects.

## Deployment

`Dockerfile`, `deploy/` un `docs/OPERATIONS.md` ir source-level deploy preparation. `rozkalns_weather` pats neiegūst RPi5 root/sudo/deploy authority. `RPi5_main` static weather operation/adapter source darbs un deterministic first-bootstrap source composition ir merged (`RPi5_main` Issue #408 / PR #409 un Issue #410 / PR #415), bet trusted execution un host wiring paliek disabled līdz atsevišķam exact LIVE gate.

RPi5, systemd/Docker, Cloudflare, credentials, private Google Cloud/BigQuery access, production SQLite/corpus writes un runtime mutation prasa atsevišķu LIVE autorizāciju.

## Dokumentācija

- `docs/BENCHMARK_METHODOLOGY.md`
- `docs/PUBLIC_BACKFILL_PROBABILISTIC_V3.md`
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md`
- `docs/WEATHERNEXT3.md`
- `docs/WEATHERNEXT_FIRST_ACCESS.md`
- `docs/WEATHERNEXT_SUSTAINED_COLLECTION.md`
- `docs/VERIFICATION.md`
- `docs/ROADMAP.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/OPERATIONS.md`
