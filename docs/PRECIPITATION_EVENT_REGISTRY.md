# Precipitation event registry

Issue #72 freezes precipitation event semantics as a versioned source contract so verification and reports do not depend on scattered numeric thresholds.

## Canonical v1 event

Machine-readable contract: `contracts/precip-event-registry-v1.json`.

The current registry contains the canonical one-hour precipitation occurrence event:

- event id: `precipitation_1h_ge_0p1mm`;
- registry version: `precip-event-registry-v1`;
- amount variable: `precipitation_1h`;
- threshold: `0.1 mm`;
- accumulation window: `60 minutes`;
- direction: `at_or_above`;
- explicit probability variable: `precipitation_probability_1h`.

The threshold is a source contract, not an outcome-tuned parameter. Historical report artifacts keep the registry version and full event-definition identity that was used when the metric was generated.

## Eligibility

Deterministic precipitation amount and probabilistic event verification remain separate.

Brier and reliability inputs are eligible only when their probability source is one of:

1. `explicit_event_probability`;
2. `ensemble_member_fraction`.

A deterministic precipitation amount, WeatherNext summary quantile, or other point/summary value must not be converted into an event probability. Genuine ensemble member fractions are computed by applying the registered event threshold to each member.

MAE/RMSE/bias and deterministic event contingency metrics continue to use amount values without turning those amounts into probabilities.

## Semantic validation

Before a registered amount event is evaluated, its amount variable, threshold unit and accumulation window must match the event definition. Unit or accumulation-window drift fails closed; values are not converted implicitly.

The v1 boundary rule is inclusive: `0.1 mm` is an event, while values below `0.1 mm` are not.

## Provenance surfaces

`ProbabilityPair` binds explicit probability verification to the registered event id and registry version. `brier_score` emits the full event-definition identity with verification evidence.

Monthly report provenance exposes the same registered identity at report level and alongside ensemble-member precipitation Brier/reliability output. This lets historical report consumers identify exactly which event definition was used.

## Scope boundary

This contract is source-only. It performs no provider polling, production corpus write, schema migration, threshold tuning, runtime deployment or LIVE mutation. WeatherNext summary quantiles remain summary quantiles and are never treated as ensemble members or event probabilities.
