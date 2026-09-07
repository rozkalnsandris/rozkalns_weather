# Public backfill + probabilistic benchmark v3

This source lane builds a reproducible public benchmark while WeatherNext 3 private access remains pending. It does not authorize or perform a production corpus backfill.

## Deterministic archive scope

Open-Meteo Single Runs is used with an explicit `run=` parameter for:

- DWD ICON-D2;
- ECMWF IFS HRES;
- ECMWF AIFS 0.25° Single.

The common comparison window starts at `2026-04-02`. IFS history before that date is retained only as a separate non-common series. Historical exact runs intentionally record unknown upstream availability as `null`; retrieval time is never fabricated as publication time.

## Backfill command

Use the dedicated module against an explicitly selected SQLite database:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<path> forecast \
  --model icon_d2 --start 2026-04-02 --end 2026-04-03 \
  --run-hours 0,6,12,18 --checkpoint <checkpoint.json> --dry-run
```

Remove `--dry-run` only when the selected corpus is authorized for writes. The runner is bounded by explicit date/model/run ranges, rate-limited, checkpointed after each successful run and idempotent against immutable forecast hashes.

Historical DWD truth is pinned to WMO `10416`:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<path> truth \
  --start 2026-04-02 --end 2026-04-30 \
  --checkpoint <truth-checkpoint.json> --chunk-days 14 --dry-run
```

Bright Sky is transport only; DWD remains source authority. Rows without explicit WMO 10416 source identity are rejected instead of silently falling back to a nearest station. Missing values remain missing and are not imputed.

Integrity reconciliation:

```bash
python -m rozkalns_weather.backfill --database-url sqlite:///<path> integrity \
  --model icon_d2 --start 2026-04-02 --end 2026-04-30 --run-hours 0,6,12,18
```

The report exposes expected/present/missing/unexpected runs and revised immutable snapshots.

## Ensemble surface

Public ensemble adapters use Open-Meteo Ensemble API for:

- DWD ICON-D2-EPS;
- ECMWF IFS ENS 0.25°;
- ECMWF AIFS ENS 0.25°.

The parser preserves the unsuffixed control member and each `_memberNN` identity across variables. Individual-member historical access is deliberately bounded to three days. Expired members are never fabricated.

WeatherNext 2 may be fetched only as `legacy_ai_context`. Its source metadata states that this Open-Meteo surface does not provide defensible exact-run provenance for strict run-to-run ranking, so it never replaces or impersonates WeatherNext 3.

## Genuine probabilistic verification

Probabilistic metrics accept ensemble member arrays, not deterministic forecast amounts:

- ensemble CRPS;
- empirical quantiles;
- interval coverage, width and interval score;
- WIS-style weighted interval score;
- precipitation event probability as the fraction of members meeting the explicit threshold, default `>= 0.1 mm/h`;
- Brier score and reliability bins from those member-derived probabilities.

Deterministic precipitation `mm` and WeatherNext summary quantiles cannot be converted into event probability by this code path.

## Fair leaderboard

`common_sample_leaderboard` intersects provider sample identifiers inside each comparison mode and lead bucket before computing metrics. Model versions remain separate. Each result reports `n`; bootstrap MAE 95% intervals are emitted only for `n >= 30`, otherwise uncertainty remains explicitly unavailable.

Supported comparison-mode semantics are distinct inputs such as `run_to_run` and `user_available`. They must never be pooled into one leaderboard.

## Event verification

Matched event summaries support temperature extremes, precipitation events and wind/gust events only when forecast/truth variable semantics and thresholds match. Reports expose hits, misses, false alarms, correct negatives, hit rate, false-alarm ratio and critical success index.

## UI v3

The existing PWA now surfaces provider role/transport classes, deterministic lead-bucket sample sizes/confidence and precipitation calibration separately. Ensemble providers are visibly distinct from deterministic providers, and WeatherNext 2 is labeled legacy context.

## Safety boundary

This document and the source implementation do not authorize:

- WeatherNext 3 allowlist/private BigQuery access or a first real WN3 snapshot;
- private home coordinates or credentials;
- RPi5/Docker/systemd/timer deployment;
- production SQLite/corpus writes or migrations;
- Cloudflare, host/network, secrets or permissions changes.
