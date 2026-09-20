# rozkalns_weather

Privāts weather dashboard + forecast-verification projekts Dortmund-Wickede apkārtnei ar **WeatherNext 3** kā `primary_research` modeli.

Galvenais cikls:

```text
forecast snapshot -> observation -> verification -> WeatherNext comparison
```

WeatherNext 3 nav warning authority. Severe-weather brīdinājumos Vācijā autoritatīvs avots ir **DWD**.

## WeatherNext aktivizācijas nākamais solis

Issue #125 gala source plāns: `deploy/weathernext-final-live-plan.json` un
`docs/WEATHERNEXT_FINAL_LIVE_PLAN.md`. Nākamais stāvoklis ir
**BLOCKED_BY_EXTERNAL_SOURCE_CAPABILITY**: `RPi5_main` privātais materializer
ir source-ready, bet vēl nav trusted izpildes savienojuma un Google binding/link
izpildes mehānismu. Allowlist apstiprinājums pats nepierāda reālu BigQuery piekļuvi.

## Benchmark metodika

Projektā ir divi atšķirīgi lokācijas režīmi:

- `station_10416` — publiska DWD Dortmund/Wickede WMO 10416 reference location. Šeit tiek veikta **mērīta accuracy verifikācija** pret DWD observations.
- `home` — privāts runtime-only punkts. Šeit tiek glabātas un salīdzinātas prognozes, bet tās netiek sauktas par izmērītu home accuracy, kamēr nav home observation truth avota.

WeatherNext 3 corpus glabā gan 00/06/12/18 UTC `synoptic_360h`, gan interim hourly `interim_48h` runus. BigQuery 0.05° station-head temperatūra/dew point un 0.1° surface lauki saglabā `mean/p10/p25/p50/p75/p90`, init/retrieval/valid/lead/model-version provenance.

ICON-D2, ECMWF IFS HRES un AIFS benchmarkam izmanto Open-Meteo **Single Runs**, nevis retrieval-hour proxy. Upstream init un API availability metadata tiek glabāti atsevišķi.

Deterministisks precipitation amount (`mm`) un precipitation probability ir atšķirīgas quantities. Brier Score tiek aprēķināts tikai tad, ja corpus tiešām satur probability event forecast; probability netiek izdomāta no deterministic mm vai WeatherNext kvantilēm.

## Public archive + ensemble benchmark v3

WeatherNext 3 piekļuve ir apstiprināta (canonical evidence: issue #122); privātā runtime/linkage un pirmā reālā piekļuve vēl ir atsevišķi gate. Public-data lane turpina reproducējamu benchmark corpus bez privāta home punkta:

- bounded/resumable exact-run backfill ar explicit model/date/UTC run-hour ranges, `--dry-run`, rate limit un atomic checkpoint;
- common deterministic archive window sākas `2026-04-02`; vecāks IFS history paliek atsevišķs non-common series;
- DWD truth backfill ir stingri pinned uz WMO `10416`; Bright Sky ir tikai transport, missing values netiek imputētas;
- integrity reconciliation rāda expected/present/missing/unexpected runus un revisions, neizmainot immutable snapshotus;
- public ensemble adapters: ICON-D2-EPS, IFS ENS 0.25° un AIFS ENS 0.25° ar control/member identity un short-retention semantics;
- CRPS, interval coverage/width, WIS-style score, precipitation member-fraction probability, Brier un reliability izmanto tikai genuine ensemble input;
- WeatherNext 2 ir tikai `legacy_ai_context`, nekad WeatherNext 3 aizvietotājs un nav strict run-to-run leaderboard modelis, ja exact provenance nav pieejams;
- common-sample leaderboard saglabā comparison mode, lead bucket, model-version boundary, explicit `n` un bootstrap CI tikai pie pietiekama sample (`n >= 30`).

Detalizēts source/runbook: `docs/PUBLIC_BACKFILL_PROBABILISTIC_V3.md`.

Optional WeatherNext full-member admission and metric eligibility are defined in
`docs/WEATHERNEXT_FULL_ENSEMBLE.md`. The network-free `weathernext_ensemble` module
requires a complete reviewed native roster and exact provenance before using
member metrics; summary-quantile fallback remains separately validated.

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
rozkalns-weather corpus-report --start YYYY-MM-DD --end YYYY-MM-DD
rozkalns-weather rollout-preflight --source-sha <MERGED_SHA> --start YYYY-MM-DD --end YYYY-MM-DD --models icon_d2,ecmwf_ifs,ecmwf_aifs --run-hours 0,6,12,18 --recovery-decision <DECISION>
rozkalns-weather rollout-evidence-validate < sanitized-evidence.json
rozkalns-weather diagnose-weathernext
rozkalns-weather report-monthly --month YYYY-MM
rozkalns-weather verification-drilldown --month YYYY-MM
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

WeatherNext version-evolution source contract ir `deploy/weathernext-version-evolution.json` + `docs/WEATHERNEXT_VERSION_EVOLUTION.md`. Tas fail-closed validē verificētu model/schema boundary, izvēlas performance-independent before/after calendar windows, intersecto tikai semantiski matched `station_10416` samples un veido MAE/RMSE/bias, summary-quantile calibration, event/notable-case un freshness deltas privacy-safe report payloadā. Tas neizdod globālu “winner”, neizdomā CRPS/Brier/probability no WeatherNext summary kvantilēm un pats nelasa production corpus. Reāls version-change report pret privāto SQLite paliek atsevišķs exact read-only owner gate pēc tam, kad abiem model periods ir defensible corpus.

WeatherNext dokumentētais dissemination target tiek glabāts kā `expected_available_at_utc`, nevis kā novērots publication timestamp. `upstream_available_at_utc` paliek `null`, kamēr upstream nav devis defensible observed publication evidence.

`init-database` ir explicit SQLite write operācija. RPi5 production candidate izmanto `DATABASE_INIT_MODE=require-existing`, tāpēc aplikācijas startup pats neizveido production DB. `readiness` ir privacy-safe un neveic tīkla pieprasījumus vai implicit schema creation.

Public backfill ir atsevišķs source module, lai nejauši nesajauktu to ar parasto runtime ingest:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<path> forecast ... --dry-run
python -m rozkalns_weather.backfill --database-url sqlite:///<path> truth ... --dry-run
python -m rozkalns_weather.backfill --database-url sqlite:///<path> integrity ...
```

Production backfill CLI tagad fail-closed prasa jau explicit inicializētu/current schema un pats vairs neizsauc `Database.initialize()` vai implicit migration. Issue #31 source contract ir `deploy/production-public-corpus-bootstrap.json` + `docs/PRODUCTION_PUBLIC_CORPUS_BOOTSTRAP.md`: first window `2026-04-02..2026-09-10`, WMO `10416`, exact `icon_d2/ecmwf_ifs/ecmwf_aifs`, `00/06/12/18 UTC`, 14-day truth chunks, ordered-prefix checkpoints un zero revision drift. `production-bootstrap-plan` un `production-bootstrap-resume-validate` ir network/DB-free source validators.

Production corpus write joprojām ir atsevišķs LIVE/data gate; source availability vai PASS validator output nav write autorizācija. Delete/restore/implicit migration nav deklarēti recovery ceļi.

`corpus-report` atver jau esošu SQLite corpus read-only/query-only režīmā un emitē machine-readable `PASS` / `WARN` / `BLOCKED`. Tas salīdzina expected/present runus pa provider/run-hour, expected/present lead buckets pēc katra modeļa horizon, valid-time robežas, immutable revision/duplicate/provenance anomālijas un DWD WMO `10416` truth coverage. Vecākais IFS-only periods pirms `2026-04-02` tiek uzrādīts atsevišķi un neietekmē common-window readiness. Report pats neveic schema init, backfill, repair vai corpus write.

Mandatory CI ir fixture-driven un network-independent. `smoke-public` ir operatora izvēles read-only live contract check.

## API / PWA

`/api/current` rāda DWD 10416 reference observation, `/api/hourly` un `/api/daily` pēc noklusējuma rāda private-home forecast comparison; `location_id=station_10416` rāda tikai station prognozes, bet `/api/verification/*` ir station-location matched benchmark. Accuracy v3 UI atdala deterministic/ensemble/legacy provider roles, rāda lead-bucket sample size/confidence un genuine precipitation calibration atsevišķi. Combined weighting joprojām ir bloķēts līdz pietiekamam corpus.

Runtime health/readiness:

`/api/health/providers` uses `provider-freshness-v1`: the five recurring public providers expose separate ingest state, freshness state, failure domain, stable reason code and last attempt/success/init/retrieval/valid-or-observed provenance. A stale local attempt is classified separately from a recent upstream/transport error, and one provider failure never hides healthy provider states.

- `/health` — process/app liveness + local DB state summary;
- `/ready` and `/api/readiness` — machine-readable schema/storage/provider/privacy readiness contract.

Public-provider failure ir redzama provider state, bet izolēta no citiem provider. WeatherNext `access_pending` nav public-only runtime blocker.

## Current deployment — SIMPLE-DEPLOY v1 canary

Weather is a **consumer/canary**, not the deployment-platform owner. The current source contract is `docs/SIMPLE_DEPLOY_CANARY.md`, `.simple-deploy.json` and the tiny immutable-pinned `.github/workflows/simple-deploy.yml`. The accepted shared revision is `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`; the reviewed generic host source is `RPi5_main@ff20fcf64ba62c95e5f15eeb481c3c66bb5c9708`.

`deploy/docker-compose.public.yml` is image-based: ordinary application replacement uses the fixed `weather` service, retained `weather_data`, `WEATHER_RUNTIME_MODE=public-only`, `DATABASE_INIT_MODE=require-existing`, `/health` and `/ready`. The generic RPi5 reconciler resolves the `:production` pointer, freezes one immutable digest and deploys that exact digest.

One-time RPi5 install/target activation remains a separate exact LIVE cutover. Production SQLite schema/corpus writes, recurring-ingest scheduler activation, WeatherNext/private-home, secrets/permissions and Cloudflare/network changes remain separate gates.

### Legacy first-rollout control-plane evidence

`deploy/rpi5-source-binding.json`, `deploy/first-public-rollout-preflight.json`, the historical `ops-workflows#46` queue and Weather operator/JIT/Composite contracts are retained for audit/regression compatibility only. They are **superseded for ordinary application releases** and are not prerequisites for SIMPLE-DEPLOY.

## Dokumentācija

- `docs/BENCHMARK_METHODOLOGY.md`
- `docs/PUBLIC_BACKFILL_PROBABILISTIC_V3.md`
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md`
- `docs/PUBLIC_UI_ROLLOUT_READINESS.md`
- `docs/WEATHERNEXT3.md`
- `docs/WEATHERNEXT_FIRST_ACCESS.md`
- `docs/WEATHERNEXT_FINAL_LIVE_PLAN.md`
- `docs/WEATHERNEXT_SUSTAINED_COLLECTION.md`
- `docs/WEATHERNEXT_VERSION_EVOLUTION.md`
- `docs/VERIFICATION.md`
- `docs/ROADMAP.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/OPERATIONS.md`
