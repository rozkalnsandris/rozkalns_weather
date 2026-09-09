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
- [x] Bounded/resumable exact-run public backfill framework with dry-run/rate-limit/checkpoint.
- [x] Common archive window contract from 2026-04-02; older IFS history separated from common series.
- [x] Historical DWD WMO 10416 truth backfill without nearest-station fallback.
- [x] Missing-run/revision/integrity reconciliation for immutable backfill snapshots.
- [x] Explicit SQLite schema-init + privacy-safe readiness commands; RPi5 candidate can require an existing schema instead of creating it on app startup.

## Phase 2 — WeatherNext 3
- [x] BigQuery 0.05°/0.1° schema/query contract.
- [x] `mean/p10/p25/p50/p75/p90`.
- [x] hourly interim + synoptic run classes.
- [x] dissemination latency/readiness diagnostics.
- [x] station benchmark + optional home collection design.
- [x] deterministic first-access source readiness: linked-dataset/schema fingerprint, dry-run cost cap, bounded `station_10416` canary, provenance/evidence validation and explicit first-snapshot write gate separation.
- [x] deterministic sustained-collection source readiness: post-canary snapshot admission, target-disseminated cadence/dedupe, missing-run recovery ledger, model/schema boundaries and privacy-safe freshness health.
- [ ] live BigQuery access verified.
- [ ] first real WeatherNext snapshot stored.

## Phase 3 — verification
- [x] station-only location-matched truth join.
- [x] MAE/RMSE/bias + lead buckets + model versions.
- [x] WeatherNext p10–p90 coverage.
- [x] common-case monthly comparison by lead bucket.
- [x] precipitation amount/probability separation.
- [x] Public ICON-D2-EPS / IFS ENS / AIFS ENS member adapters with retention/provenance semantics.
- [x] Genuine ensemble CRPS, empirical intervals, WIS-style scoring, member-fraction event probability, Brier and reliability primitives.
- [x] Common-sample leaderboard abstraction with explicit comparison mode, `n`, lead bucket and model-version boundaries.
- [x] Bootstrap MAE confidence interval only for statistically usable sample (`n >= 30`).
- [x] Matched temperature/precipitation/wind-gust event verification summaries.
- [x] WeatherNext 2 `legacy_ai_context` comparator contract; never a WN3 substitute or strict-run comparator without exact provenance.
- [ ] populate larger historical public corpus after explicit corpus-write authority.
- [ ] optional full-ensemble WeatherNext 3 CRPS/Brier if private source later exposes defensible members.

## Phase 4 — private PWA / RPi5 runtime
- [x] Overview / Models / Accuracy / Warnings-Radar.
- [x] current DWD station truth clearly labeled.
- [x] home forecast charts/daily cards.
- [x] provider init/freshness states.
- [x] WeatherNext uncertainty surface.
- [x] Accuracy v3 provider classes, lead-bucket sample/confidence and precipitation calibration surface.
- [x] deterministic public-only RPi5 application packaging + fixed machine-readable deploy descriptor.
- [x] public collector schedule and explicit non-destructive corpus-bootstrap contract.
- [x] weather-side trusted-boundary handoff contract for a future `RPi5_main` static adapter.
- [x] `RPi5_main` static source adapter/operation registration reviewed and merged via Issue #408 / PR #409.
- [x] `RPi5_main` deterministic first-bootstrap source composition merged via Issue #410 / PR #415.
- [x] `RPi5_main` source-only Weather LIVE-AUTH/READY pre-activation composition merged via Issue #432 / PR #433.
- [x] `RPi5_main` trusted Weather host-wiring/helper source bridge merged via Issue #435 / PR #436; execution and production mutation remain disabled until a separate exact STRICT LIVE gate.
- [x] deterministic rollout-readiness package: source-only preflight, <=180-day WMO 10416 + ICON-D2/IFS/AIFS bootstrap envelope, ordered checkpoint/resume, recovery decision, explicit systemd timer semantics, post-rollout evidence validator and fail-closed stage matrix.
- [ ] first public-only RPi5 rollout under a separately authorized exact STRICT LIVE gate using freshly bound host/source/CI/helper/bounds/recovery/mutation-budget fields.
- [ ] production public corpus schema/bootstrap/backfill under explicit LIVE/data authority.
- [ ] later private-home / WeatherNext runtime activation after private access and configuration are explicitly ready.
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
- [x] public benchmark runway while WN3 access is pending.
- [x] first-month verification source readiness: station common-times/model-version/lead-bucket eligibility, summary-quantile calibration and sanitized evidence/report contract.
- [x] version-change comparative reporting source readiness: verified model/schema boundary, deterministic before/after windows, strict common station samples, skill/quantile/freshness deltas, deterministic notable cases and privacy-safe report contract.
- [ ] first month of real WeatherNext 3 corpus.
- [ ] version-change comparative reports against real corpus.

AQI/pollen/UV and Combined weighting remain lower priority until enough real corpus exists.
