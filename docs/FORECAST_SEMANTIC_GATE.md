# Forecast semantic and unit consistency gate

Issue #56 defines the source-side `forecast-semantic-v1` contract. The gate is
network-independent and runs before a `ForecastValue` can enter the normal
forecast corpus path.

## Canonical identity

A normalized semantic identity is the tuple of:

- canonical variable,
- normalized unit,
- quantity kind,
- accumulation window,
- statistic family,
- event-definition version where applicable.

Provider/model identity and native provenance remain separate. `native_value`,
`native_unit`, provider, model, model version, init/retrieval/valid/lead metadata
are not rewritten by the semantic gate.

Supported statistic families are:

- `deterministic` for deterministic provider values;
- `summary_mean` for a provider/model mean used as a point forecast;
- `summary_quantile` for WeatherNext-style `p10/p25/p50/p75/p90` summaries;
- `ensemble_member` for genuine member/control values;
- `event_probability` for an explicit event-probability quantity.

Raw statistic labels remain preserved. For example, `member_00` normalizes to
the `ensemble_member` family but is not renamed in the stored corpus.

## Precipitation separation

`precipitation_1h` is an amount in `mm` with a 60-minute accumulation window.
It is not a probability.

`precipitation_probability_1h` is a separate probability quantity tied to
`precip-occurrence-v1`. A deterministic precipitation amount may not be
reinterpreted as an event probability. The existing ensemble reporting path
derives precipitation event probability only as the fraction of stored
`member_*` values crossing the event threshold.

## Metric eligibility

The source contract is fail-closed:

- MAE/RMSE/bias/event-threshold metrics accept deterministic or summary-mean
  point forecasts.
- CRPS/interval/WIS eligibility requires genuine ensemble-member semantics.
  WeatherNext summary quantiles are not ensemble members and are not CRPS input.
- Brier/reliability accepts either an explicit event-probability quantity or a
  genuine precipitation ensemble member fraction. Deterministic precipitation
  amount and summary quantiles are ineligible.

`enforce_semantic_slice()` rejects slices that mix variable, unit, quantity
kind, accumulation window, statistic family, or event definition.

## Safety boundary

This gate does not rewrite the existing corpus, fabricate provider values,
derive probabilities from deterministic amounts, create Combined weights,
query WeatherNext, or perform any LIVE/RPi5/runtime mutation. It adds no schema
migration. Existing provider/native provenance remains immutable.
