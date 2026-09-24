# Forecast cycle and horizon coverage gate

Issue #73 adds a source-side gate that prevents verification/reporting from silently treating provider cycles or forecast horizons as interchangeable.

The machine-readable contract is `contracts/forecast-cycle-coverage-v1.json`; Python enforcement lives in `rozkalns_weather.cycle_coverage`.

## Contract identity

Every coverage result carries `forecast-cycle-coverage-v1`. Historical outputs must retain that registry version together with the source `model_version`; a newly observed provider horizon must not silently rewrite an older expectation. `HORIZON_CONTRACT_CHANGE` means the registry needs an explicit reviewed version change before the new horizon can be mixed into comparison evidence.

Current exact-init contracts preserve the already-reviewed source semantics:

- `icon_d2`: 00/06/12/18 UTC, 48 h;
- `ecmwf_ifs`: 00/12 UTC to 240 h and 06/18 UTC to 144 h;
- `ecmwf_aifs`: 00/06/12/18 UTC, 360 h;
- `weathernext3`: provider-native hourly init partitions, with 00/06/12/18 synoptic runs to 360 h and interim hours to 48 h.

The Open-Meteo ensemble surface used by `icon_d2_eps`, `ecmwf_ifs_ens`, `ecmwf_aifs_ens` and `weathernext2_legacy` does not expose an exact initialization identity. The registry therefore records those cycles as **unobservable** rather than inventing native init classes. Their request horizon remains bounded to the adapter's reviewed 1..16 day request envelope, and they are not eligible for exact-cycle comparison claims from this surface.

## Stable reason codes

`evaluate_run_coverage` fails closed with stable codes:

- `UNEXPECTED_CYCLE_CLASS` — an exact-init run uses a cycle outside the registered contract;
- `EARLY_TRUNCATION` — the observed lead envelope stops before the registered horizon;
- `UNEXPECTED_EXTRA_LEAD` — the observed lead envelope exceeds the registered horizon;
- `DUPLICATE_LEAD` — the same lead appears more than once in a run slice;
- `HORIZON_CONTRACT_CHANGE` — provider/source metadata declares a horizon that differs from the frozen registry;
- `INVALID_LEAD` / `NEGATIVE_LEAD` — unusable lead metadata;
- `INIT_CYCLE_UNOBSERVABLE` — exact cycle claims are unavailable on the reviewed ensemble surface.

`cycle_class_coverage` emits `MISSING_CYCLE_CLASS` when an expected class is absent from a comparison window. The public corpus report integrates this gate and emits provider-prefixed blockers such as `ICON_D2_MISSING_CYCLE_CLASS` while preserving its existing missing-run and lead-bucket blockers.

## Comparison intersection

`comparison_lead_intersection` computes the maximum defensible common lead for a specified init hour. A requested slice beyond that common horizon returns `UNSUPPORTED_LONG_LEAD_COMPARISON`; unsupported cycle combinations return `UNSUPPORTED_CYCLE_COMPARISON`. Callers must use the returned common horizon rather than extrapolating the longer provider into a shorter provider's unsupported range.

This is especially important for public comparisons: at 00 UTC, for example, `icon_d2` and `ecmwf_ifs` have a common exact-run horizon of 48 h even though IFS continues farther.

## Corpus/report integration

`public_corpus_report` now derives provider horizon expectations from this registry, records registry/model-version boundary provenance, and includes cycle-class coverage in readiness. It remains read-only and does not repair, backfill, relabel, truncate, interpolate or otherwise mutate snapshots.

The strict run evaluator is intentionally fixture-driven and reusable by future ingest/admission/report paths. No provider polling, production corpus mutation, Combined weighting, WeatherNext query, runtime action or LIVE mutation is performed by this gate.
