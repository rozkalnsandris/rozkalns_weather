# Roadmap

```text
forecast snapshot -> observation -> verification -> WeatherNext comparison
```

## Current project state

The first usable public-only Weather Web UI milestone (#136) is **completed**.

Current public baseline:

- [x] FastAPI + SQLite immutable corpus.
- [x] Shared SIMPLE-DEPLOY v1 ordinary application-release path.
- [x] One-time RPi5 SIMPLE-DEPLOY cutover.
- [x] First standing `AUTO_DEPLOY_SAFE` Weather release proof — #146.
- [x] Production public schema/corpus bootstrap — #148.
- [x] Recurring public ingest enabled and verified.
- [x] Overview / Models / Accuracy / Warnings-Radar usable with real public data.
- [x] `/health`, `/ready`, `/api/readiness` and provider-health runtime contracts.
- [x] DWD official warning authority preserved.

## Current operational P0 — private-home forecast + radar — completed

Audit #315 separates the operational weather product from WeatherNext research. The private-home source, runtime, data and safety acceptance path is now complete.

- [x] Merge source support for `WEATHER_RUNTIME_MODE=private-home` with runtime-only home coordinates and no Google/WeatherNext dependency.
- [x] Make `DATABASE_INIT_MODE=require-existing` application startup DB-read-only; location materialization remains on explicit write/ingest paths.
- [x] Configure private home coordinates under exact LIVE authority without committing or exposing them.
- [x] Run and verify home-scoped ICON-D2 / ECMWF IFS / ECMWF AIFS forecast ingest, then activate recurring ingest under a separate production-data/systemd gate.
- [x] Verify `/api/hourly` and `/api/daily` for `home` with all three public providers.
- [x] Verify DWD official warnings and DWD/Bright Sky observed/nowcast radar centered on the private-home reference with coordinate/geometry/raw-payload exposure disabled.
- [x] Keep `station_05480` as measured verification truth; do not claim measured home accuracy.

WeatherNext #122 remains a separate research lane and is not an operational-home prerequisite.

Canonical measured benchmark:

- `station_05480` / DWD CDC 05480 (Werl);
- fixed common benchmark window `2026-08-13..2026-08-26`;
- ICON-D2 / ECMWF IFS / ECMWF AIFS exact `00/06/12/18 UTC` deterministic runs;
- DWD CDC observations as measured truth.

`station_10416` is legacy/MOSMIX reference compatibility only. The old `2026-04-02..2026-09-10` bootstrap attempt and old 10416 corpus remain historical evidence, not the current readiness contract.

## Phase 0 — public/runtime foundation

- [x] Runtime-only private-home configuration contract.
- [x] Public-only runtime works without WeatherNext credentials or private home coordinates.
- [x] Immutable forecast snapshots + observation truth + verification schema.
- [x] Public provider adapters and provenance.
- [x] Provider failure isolation, freshness and ingest-health observability.
- [x] Corpus integrity, revisions, stats and reproducibility contracts.
- [x] Public-only PWA and safety/radar surfaces.

## Phase 1 — current public benchmark

- [x] DWD CDC 05480 selected and pinned as canonical measured benchmark — #155/#156.
- [x] Dedicated CDC historical/recent truth transport for benchmark variables.
- [x] Forecast/truth co-location at `station_05480`.
- [x] Fixed common exact-run window `2026-08-13..2026-08-26` proven retrievable — #159/#160.
- [x] Production corpus bootstrap completed with preserved historical rows.
- [x] IFS cycle-aware lead-bucket integrity — #161/#162.
- [x] Recurring ingest activated and first scheduled run verified.
- [x] Public-only Warnings/Radar fallback uses privacy-safe public reference — #163/#164.
- [x] Public-only Overview/Models default aligned to `station_05480` — #165/#166.

## Phase 2 — WeatherNext 3 private access

WeatherNext 3 remains the primary research model. Real private access is intentionally separate from the completed public UI milestone.

- [x] WeatherNext access request approved.
- [x] BigQuery schema/query/cost/provenance source contracts.
- [x] Summary statistics `mean/p10/p25/p50/p75/p90` contract.
- [x] Hourly interim + synoptic run-class contracts.
- [x] **#168** migrate first-access canary source contract from legacy `station_10416` to canonical `station_05480`.
- [x] **#224** completed: one WeatherNext Analytics Hub linked dataset and one least-privilege RPi5 runtime authentication path are available; this does not authorize a real WeatherNext query or production-data write.
- [ ] **#122** research-only: resolve clustered-table cost-control semantics before any real WeatherNext query; this lane is non-blocking for private-home forecast/radar.
- [ ] Persist first real WeatherNext snapshot under a separate production-data authorization.
- [ ] Enable sustained private WeatherNext collection only after access/provenance/cost/runtime proof.

SIMPLE target: standard BigQuery client + ADC-compatible runtime credential. Ordinary application code continues through SIMPLE-DEPLOY; credentials/private-provider activation remain separate owner-gated runtime configuration.

No WeatherNext real value may be fabricated. Private Google identity, credentials and home coordinates never belong in GitHub evidence.

## Phase 3 — verification depth

Completed foundations:

- [x] station-only location-matched truth joins;
- [x] MAE/RMSE/bias, lead buckets and model-version dimensions;
- [x] WeatherNext quantile coverage contracts;
- [x] precipitation amount/probability separation;
- [x] public ensemble adapters and genuine ensemble verification primitives;
- [x] common-sample comparison with explicit `n` and confidence handling;
- [x] event verification summaries;
- [x] provider/model provenance and immutable snapshot history.

Next candidates after WeatherNext first-access alignment:

- [ ] #78 DWD observation finality/revision-window contract at `station_05480`.
- [ ] #83 end-to-end value provenance trace.
- [ ] #100 spatial collocation/grid-identity provenance.
- [ ] #76 cross-artifact privacy leakage scanner.
- [ ] first month of real WeatherNext corpus and version-aware measured analysis after enough real samples exist.
- [ ] optional full-member WeatherNext ensemble metrics only if the private source exposes defensible members.

## Phase 4 — deployment / operations

Current ordinary application release path is complete and standing:

```text
AUTO-RUN FULL
-> CI PASS
-> guarded merge
-> shared SIMPLE-DEPLOY
-> immutable GHCR digest
-> generic RPi5 pull reconciler
-> /health + /ready
-> LIVE
```

- [x] shared SIMPLE-DEPLOY v1 accepted at `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`;
- [x] generic trusted pull deployer installed/active;
- [x] Weather canary adoption completed;
- [x] one-time target activation completed;
- [x] first standing ordinary release proof completed (#146);
- [x] public corpus and recurring ingest completed (#148 plus later source fixes/gates).

Historical Weather broker/operator/queue/JIT/Composite paths remain audit evidence only and are superseded for ordinary application releases.

DB/schema/corpus mutation, private-provider access, credentials, Cloudflare/network, filesystem ownership and host/systemd changes are still separate exact owner gates where applicable.

## Phase 5 — safety / radar

- [x] DWD warning lifecycle normalization.
- [x] DWD authority separation.
- [x] public-only Warnings/Radar reference without private coordinates.
- [x] radar observed/nowcast contract.
- [x] private-home centered warnings/radar validation completed after separately authorized private-home activation.

## Phase 6 — WeatherNext evolution

- [x] monthly report generator source contract.
- [x] model-version + lead-bucket dimensions.
- [x] notable-case/report payload foundations.
- [x] version-change comparative-report source readiness.
- [ ] real WeatherNext first-access evidence.
- [ ] first month of real WeatherNext corpus.
- [ ] version-change comparative reports against defensible real corpus.

## Deferred / lower priority

Until enough real verification corpus exists:

- Combined weighting;
- AQI/pollen/UV;
- publication-oriented WeatherNext analytics;
- private-home enhancements not required for the public benchmark.

Issue #9 is legacy/historical AUTO-RUN controller evidence, not current mutable run truth. New explicit AUTO-RUN FULL runs keep mutable state on the target issue under `.github/auto-run-full-v2.json`; fresh `main`, target issue and exact-head CI/reviews determine current source work state.
