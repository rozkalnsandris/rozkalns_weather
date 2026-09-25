# Forecast quantile admissibility

`forecast-quantile-admissibility-v1` is the source-side structural gate for summary-quantile forecast slices such as WeatherNext `p10`, `p25`, `p50`, `p75`, and `p90`.

## Boundary

The gate is network-free and does not query WeatherNext, mutate the corpus, repair provider data, or authorize runtime/LIVE work. It evaluates already-described source evidence only.

Summary quantiles are a distinct forecast representation. They are **not** ensemble members and are **not** event probabilities. The gate therefore never synthesizes members from quantiles and never derives CRPS, Brier score, reliability, or member-fraction probabilities from summary quantiles.

## Required identity

Every quantile in one compared set must share the same:

- provider;
- model name and model version;
- init time and retrieval time;
- valid time and lead;
- variable and unit;
- location identity;
- source surface and declared resolution.

A drift in any of these fields blocks the set with a stable reason code. In particular, the WeatherNext 0.05-degree station-head surface and a 0.1-degree surface cannot be combined into one quantile set.

## Completeness and ordering

The default supported set is:

`p10 <= p25 <= p50 <= p75 <= p90`

Equal adjacent quantiles are valid. Missing statistics are reported as `INCOMPLETE_QUANTILE_SET`; duplicates as `DUPLICATE_QUANTILE_STATISTIC`; any lower quantile greater than its next upper quantile produces `QUANTILE_CROSSING`. Missing quantiles are never fabricated.

The canonical reason-code registry is in `contracts/forecast-quantile-admissibility-v1.json`.

## Verification integration

`evaluate_quantile_set()` returns `PASS` only for a complete, provenance-aligned, monotonic summary-quantile set. `verification.summary_quantile_coverage()` then accepts only that PASS evidence and obtains the requested interval through `interval_bounds()`.

This is intentionally separate from `probabilistic.py`, which computes member-based CRPS/interval/WIS/Brier behavior from genuine ensemble members. Existing generic `verification.summarize()` remains backward-compatible for historical report paths; new WeatherNext summary-quantile interval/coverage work must use the admissibility-backed path.

## Fixtures

`tests/fixtures/forecast_quantile_admissibility.json` covers:

- valid quantiles;
- equal quantiles;
- one crossing pair;
- incomplete set;
- duplicate statistic identity;
- mixed model-version provenance;
- mixed units;
- mixed source surfaces;
- mixed resolution.

All fixtures use the public benchmark label `station_05480`; no private home coordinates or provider credentials are part of the evidence.
