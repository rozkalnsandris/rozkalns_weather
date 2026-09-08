# WeatherNext 3 version evolution

Status: **source readiness only**. This runbook does not prove that a real WeatherNext version boundary has occurred locally and does not authorize production corpus access.

Canonical source contract:

- `deploy/weathernext-version-evolution.json`
- `src/rozkalns_weather/weathernext_evolution.py`
- `tests/test_weathernext_evolution.py`

WeatherNext 3 remains `primary_research`. DWD remains the authoritative severe-weather warning source in Germany.

## 1. Boundary identity

A comparable WeatherNext 3 boundary must bind all of:

- `before_model_version`;
- `after_model_version`;
- before/after schema SHA-256 fingerprints;
- provider-effective boundary time in UTC;
- verified release/model metadata source URL;
- explicit proof that release metadata was verified.

Unknown products or non-WeatherNext-3 identities fail closed. WeatherNext 2/Gen/Graph cannot be silently coerced into this comparison.

Provider effective/release time, locally first-observed time and retrieval time are different facts and must remain separate.

## 2. Comparison windows

`plan_comparison_windows()` selects fixed calendar windows around the effective boundary. Default is 30 days on each side; source maximum is 92 days per side.

Window selection is never optimized using forecast performance. If corpus availability clips one side, the payload exposes unequal duration and seasonality limitations instead of silently changing the other side to improve a result.

## 3. Common-sample matching

Measured cross-version skill is restricted to `station_10416` with DWD WMO 10416 truth.

The common-sample identity includes:

```text
location_id
valid_time_utc
variable
lead_bucket
run_class
forecast statistic/semantics
unit
accumulation semantics when applicable
```

Private `home` forecasts are excluded from measured station skill. Before-only and after-only timestamps are reported through sample counts but never used to make one side look better.

## 4. Deterministic skill deltas

For each `(variable, lead_bucket, run_class)` common-sample slice the contract calculates separate before/after:

- `n`;
- MAE;
- RMSE;
- bias;
- sample-confidence state.

The report then exposes `after - before` absolute and relative deltas. It does **not** emit a global version winner.

Uncertainty output remains sample-gated; a slice with `n < 30` is not treated as statistically usable.

## 5. WeatherNext summary-quantile calibration

For matched WeatherNext `p10/p25/p50/p75/p90` samples the contract compares:

- p10-p90 coverage;
- p10-p90 mean width;
- p25-p75 coverage;
- p25-p75 mean width;
- p50 MAE.

Quantiles must be monotonic. `precipitation_1h` keeps 60-minute accumulation semantics.

Summary quantiles are **not** converted into synthetic CRPS, Brier score or precipitation event probability. Those require genuine member/probability data.

## 6. Event and notable-case analysis

Temperature, precipitation and wind/gust event semantics reuse fixed thresholds. A case is classified as improvement/regression/unchanged only from matched before/after station samples.

Notable-case selection is deterministic: largest absolute change in absolute forecast error first, then stable timestamp/variable/lead ordering. There is no manual cherry-picking by observed performance.

## 7. Freshness and latency

Version-period health comparisons may summarize:

- expected run count;
- retrieved count;
- missing/delayed count;
- retrieval lag from expected dissemination;
- observed upstream availability lag when defensible.

`expected_available_at_utc`, observed upstream availability and `retrieved_at_utc` remain separate fields. Missing/delayed state is not forecast skill.

## 8. Sanitized report/API/UI payload

`build_version_evolution_report()` emits the source contract `weathernext3_version_evolution_v1` with:

- boundary identity;
- windows and limitations;
- common sample counts;
- deterministic skill deltas;
- summary-quantile calibration deltas;
- freshness/latency summary;
- event summary;
- deterministic notable cases;
- verified release provenance;
- explicit research-only/DWD-authority labels.

The payload validator rejects private Google project/dataset identity, credentials/tokens, SQL, coordinates, private filesystem paths, raw provider payloads and raw logs. Source fixtures use synthetic numbers only and are not WeatherNext empirical results.

## 9. Publication and provenance

A version-change claim is allowed only when provider/model release metadata is already recorded from a defensible verified source. Locally first observing data after a boundary does not prove provider release time.

Private real-time WeatherNext values and restricted provider payloads are never part of the GitHub evidence contract. Before public use, upstream data terms must be freshly reviewed.

## 10. Later production corpus read-only gate

Running a real version-change report against the private production corpus is a separate exact owner gate. Before any production corpus read bind:

```yaml
weather_sha: <reviewed merged exact SHA>
weather_exact_sha_ci:
  backend_tests: success
  governance_gates: success
sqlite_target: <exact private runtime DB identity; do not commit path>
query_scope: read_only_version_evolution_report
before_model_version: <exact recorded version>
after_model_version: <exact recorded version>
effective_boundary_utc: <verified UTC boundary>
before_window: <start/end UTC>
after_window: <start/end UTC>
minimum_sample_requirement: n>=30 per metric slice for usable uncertainty
privacy_safe_output_contract: weathernext3_version_evolution_v1
failure_semantics: read_only evidence + STOP; no mutation/cleanup fallback
corpus_mutation_allowed: false
```

That gate authorizes only the exact read-only production query scope if explicitly granted. It does **not** authorize schema migration, corpus write/delete/cleanup/restore, BigQuery access, scheduler mutation or RPi5 deployment.

## Current source vs empirical state

After this source contract is merged, the project is prepared to analyze a future real WeatherNext 3 model/schema boundary. It must not claim a real version-change comparison until private corpus contains both defensibly identified periods and the later read-only gate is explicitly authorized and executed.
