# Forecast physical-consistency gate

Contract: `forecast-physical-v1`.

This gate is downstream of `forecast-semantic-v1` and upstream of corpus admission,
verification and reporting. It never repairs, clamps, imputes or fabricates provider
values.

## Validation boundary

`ForecastRun` is the point/location snapshot boundary. Cross-variable invariants are
evaluated only inside one run and only when values have the same:

- provider/model/model-version/init (fixed by the run);
- valid time;
- lead time;
- statistic/member identity;
- run-local location scope.

Values from different runs, valid times, lead times or statistics are never
cross-compared. The privacy-safe metadata identity uses `location_id=forecast_run`
rather than coordinates; actual location binding remains the persistence/orchestrator
responsibility.

## Invariants

Blocking and tolerance-level findings use stable reason codes:

| Invariant | SUSPECT tolerance | BLOCKED |
| --- | --- | --- |
| dew point must not exceed temperature | excess `<= 0.5 degC` | `DEWPOINT_ABOVE_TEMPERATURE` |
| gust must not be below sustained wind | deficit `<= 0.5 m/s` | `GUST_BELOW_SUSTAINED_WIND` |
| RH/cloud/probability must be within `0..100%` | outside by `<= 0.5` percentage points | `BOUNDED_FIELD_OUT_OF_RANGE` |
| precipitation/wind magnitudes must be non-negative | negative magnitude `<= 0.05` native canonical units | `NEGATIVE_MAGNITUDE` |

Tolerance findings append `_TOLERANCE` to the base reason code and produce
`state=SUSPECT`. They are preserved unchanged. Any larger contradiction produces
`state=BLOCKED` and raises `PhysicalConsistencyError` before a `ForecastRun` can be
returned to the persistence/verification path.

The probability bound is also enforced by the semantic gate for normal
`ForecastValue` construction. The physical contract keeps the same bound explicitly
so raw/candidate validators and regression fixtures cannot treat probability as an
unbounded physical quantity.

## Provenance and reporting

For `PASS` and `SUSPECT` runs, the run keeps all original forecast/native values and
all provider metadata. A separate `source_metadata.physical_consistency` object records:

- contract version;
- `PASS` / `SUSPECT` state;
- stable reason codes;
- finding count;
- privacy-safe comparison identity and original values involved in each finding.

`BLOCKED` runs fail before corpus admission, so downstream verification/report code
cannot silently consume an impossible slice. Validation is run-local and stateless:
one provider/run failure does not change or invalidate unrelated provider runs; the
existing ingest orchestrator already isolates provider fetch failures.

## Explicit non-goals

- no production corpus rewrite or repair;
- no value correction/clamping;
- no Combined forecast weighting;
- no WeatherNext fabricated data;
- no runtime/LIVE mutation.
