# rozkalns_weather

Privāts weather dashboard + forecast-verification projekts Dortmund-Wickede apkārtnei ar **WeatherNext 3** kā `primary_research` modeli.

Galvenais cikls:

```text
forecast snapshot -> observation -> verification -> WeatherNext comparison
```

WeatherNext 3 nav warning authority. Severe-weather brīdinājumos Vācijā autoritatīvs avots ir **DWD**.

## Current canonical state

Pirmais reāli lietojamais public-only Weather Web UI milestone (#136) ir pabeigts.

- ordinary application releases izmanto shared **SIMPLE-DEPLOY v1**;
- generic RPi5 pull reconciler ir standing deployment path;
- `/health`, `/ready` un `/api/readiness` ir production acceptance contract;
- production SQLite schema un public corpus ir inicializēti;
- recurring public ingest ir aktivizēts;
- Overview / Models / Accuracy / Warnings-Radar darbojas ar reāliem public datiem;
- DWD paliek official warning authority;
- private home un WeatherNext private access nav pirmā public-only UI prerequisite.

Mutable runtime SHA/digest/provider-health stāvokli neglabā šajā README kā authority. Fresh continuity/runtime receipts ir controller issue #9 un attiecīgajos completed LIVE/source issues.

## Canonical benchmark

Current measured public benchmark ir:

- location id: `station_05480`;
- DWD CDC station: `05480` (Werl);
- truth authority: DWD CDC observations;
- deterministic comparison providers: ICON-D2, ECMWF IFS, ECMWF AIFS;
- current fixed common benchmark window: `2026-08-13..2026-08-26`;
- exact deterministic run hours: `00/06/12/18 UTC`.

`station_10416` ir **legacy/MOSMIX reference compatibility**. Tas nav current measured benchmark jauniem verification contracts.

Vecais `2026-04-02..2026-09-10` bootstrap mēģinājums un ar to saistītais 10416 corpus ir historical evidence. Tas netiek dzēsts vai pārrakstīts un nav current fixed common-window readiness contract.

Private `home` ir runtime-only forecast location. Home prognozes netiek sauktas par measured home accuracy, kamēr nav atsevišķs defensible home observation truth avots.

## Public corpus and verification

Forecast snapshots ir immutable un saglabā provider/model provenance: model version, init, retrieval, valid time, lead time, statistic/member un source surface.

Public deterministic exact-run corpus izmanto Open-Meteo Single Runs transportu ICON-D2 / IFS / AIFS avotiem. DWD CDC `05480` ir measured observation truth.

`corpus-report` un verification slānis pārbauda provider/run-hour/lead-bucket coverage, immutable revisions, provenance un benchmark-truth coverage. IFS cycle-dependent horizon ir explicit: 00/12 ir long cycles, 06/18 īsāki cikli; coverage expectations ir cycle-aware.

Deterministic precipitation amount (`mm`) un precipitation probability ir atšķirīgas quantities. Probability/CRPS/Brier netiek fabricēti no deterministic amount vai summary quantiles.

## WeatherNext 3 continuation

WeatherNext 3 paliek first-class `primary_research`, bet real private access vēl ir atsevišķs trust-boundary darbs.

Current sequence:

1. #168 — source-only migrēt first-access canary no legacy `station_10416` uz canonical `station_05480`;
2. #122 — tikai pēc #168 un fresh preflight veikt explicit owner-authorized private read-only BigQuery first-access gate;
3. first real WeatherNext snapshot write — atsevišķa production-data authorization;
4. sustained private collection — tikai pēc proven access/provenance/cost/runtime contracts.

Current `deploy/weathernext-first-access.json` legacy v1 binding uz 10416 nedrīkst tikt izmantots private query, kamēr #168 nav pabeigts. WeatherNext real values nekad netiek fabricētas.

## Deployment — SIMPLE-DEPLOY v1

Weather ir shared deployment platform **consumer/canary**, nevis platformas īpašnieks.

Canonical ordinary release path:

```text
AUTO-RUN FULL
-> CI PASS
-> guarded merge
-> shared ops-workflows SIMPLE-DEPLOY
-> GHCR exact source SHA + immutable digest
-> generic RPi5 pull reconciler
-> Compose application replacement
-> /health + /ready verification
-> LIVE
```

Weather consumer config: `.simple-deploy.json` un `.github/workflows/simple-deploy.yml`.
Accepted shared workflow revision: `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`.

One-time SIMPLE-DEPLOY cutover, first standing AUTO_DEPLOY_SAFE release (#146), production public corpus bootstrap (#148) un recurring-ingest activation ir **completed**.

Ordinary application merge nedod authority DB/schema/corpus mutation, systemd/timer changes, secrets/permissions, Cloudflare/network, private-home vai private WeatherNext operations.

Historical Weather broker/operator/queue/JIT/Composite artifacts ir retained audit/regression evidence only un ir **superseded ordinary releases**.

## API / PWA

Public-only UI bez private home defaultē uz `station_05480`.

- `/api/current` — DWD CDC 05480 observation view;
- `/api/hourly` / `/api/daily` — selected-location provider forecast data;
- `station_05480` — canonical public model-comparison location;
- `station_10416` — legacy MOSMIX reference option;
- `/api/verification/*` — location-matched measured benchmark state;
- `/api/warnings` — DWD official warning authority;
- `/api/radar` — observed/nowcast context, nevis model warning output;
- `/api/health/providers` — provider ingest/freshness/error provenance;
- `/ready` un `/api/readiness` — machine-readable runtime readiness.

Public-only Warnings/Radar izmanto privacy-safe public reference location, ja private home nav konfigurēts. Exact private coordinates API/UI/GitHub netiek eksponētas.

## CLI

```bash
rozkalns-weather init-database
rozkalns-weather readiness
rozkalns-weather ingest-public
rozkalns-weather ingest-weathernext
rozkalns-weather smoke-public
rozkalns-weather corpus-stats
rozkalns-weather corpus-check
rozkalns-weather corpus-report --start YYYY-MM-DD --end YYYY-MM-DD
rozkalns-weather diagnose-weathernext
rozkalns-weather report-monthly --month YYYY-MM
rozkalns-weather verification-drilldown --month YYYY-MM
```

`init-database` un production corpus/backfill commands ir explicit write operations. Production runtime izmanto `DATABASE_INIT_MODE=require-existing`; app startup pats neizveido schema un neveic hidden backfill/migration.

## Privacy and safety invariants

- necommitot exact home address, `HOME_LAT`, `HOME_LON`, `.env`, credentials, tokens, Cloudflare secrets vai private runtime logs;
- WeatherNext real values nedrīkst fabricēt;
- provider/model provenance nedrīkst zaudēt;
- DWD warning authority nedrīkst aizvietot ar model output;
- production data writes un private-provider access paliek atsevišķi exact owner gates.

## Historical continuity

Svarīgākie historical source/rollout receipts paliek discoverable closed issues/PRs un Git history. Historical 10416, pre-SIMPLE-DEPLOY un first-rollout operator/JIT statements nav current runtime authority.

Canonical current continuity: issue #9.

## Dokumentācija

- `docs/BENCHMARK_METHODOLOGY.md`
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md`
- `docs/ROADMAP.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/WEATHERNEXT3.md`
- `docs/WEATHERNEXT_FIRST_ACCESS.md`
- `docs/WEATHERNEXT_SUSTAINED_COLLECTION.md`
- `docs/WEATHERNEXT_VERSION_EVOLUTION.md`
- `docs/VERIFICATION.md`
- `docs/OPERATIONS.md`
