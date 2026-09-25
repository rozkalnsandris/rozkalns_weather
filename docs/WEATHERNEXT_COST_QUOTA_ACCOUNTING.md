# WeatherNext cost and quota accounting

Issue #97 adds a **source-only planning gate** for future sustained WeatherNext 3 BigQuery collection. It evaluates sanitized dry-run byte estimates against explicit per-query, period-budget and quota evidence before any private read may be considered.

It does not execute BigQuery, change quotas, read billing data, mutate credentials, write the corpus, activate a scheduler or grant LIVE authority.

## Contract

Machine-readable policy: `contracts/weathernext-cost-quota-accounting-v1.json`.

Evaluator: `rozkalns_weather.weathernext_cost_accounting.evaluate_cost_quota_envelope()`.

The evaluator consumes only source/test evidence:

- run class (`interim_48h` or `synoptic_360h`);
- sanitized query role;
- expected WeatherNext model version and schema fingerprint;
- dry-run `estimated_bytes`;
- explicit `maximum_bytes_billed`;
- booleans proving an exact-partition-bounded query and selected-columns-only query shape;
- configured planned runs per day;
- configured daily/weekly/monthly warning and blocking byte budgets;
- explicit quota evidence.

It deliberately accepts no SQL, project ID, dataset ID, credential, account/billing identifier, home coordinates or raw provider payload.

## Google BigQuery semantics used by this gate

The design follows current Google Cloud BigQuery guidance:

- dry runs validate a query and provide bytes-processing estimates without executing the query;
- dry-run byte estimates are planning/cost-control evidence, not proof of actual billed bytes or an invoice amount;
- `maximum bytes billed` is a fail-closed per-query control for on-demand queries;
- selecting only required columns and pruning partitions reduces bytes processed;
- query quotas can be configured and are operational state, so this repository does not hard-code a mutable Google quota default as the user's real quota.

Canonical references:

- https://cloud.google.com/bigquery/docs/running-queries
- https://cloud.google.com/bigquery/docs/best-practices-costs
- https://cloud.google.com/bigquery/docs/querying-partitioned-tables
- https://cloud.google.com/bigquery/quotas

The source contract therefore records `actual_billed_cost_known=false` and does not convert bytes into EUR/USD. A future operator may bind separately reviewed pricing/billing evidence, but this gate never fabricates currency cost from a dry-run estimate.

## Fail-closed query requirements

Every eligible plan item must prove all of the following:

1. the evidence is from a dry run;
2. `estimated_bytes` exists and is non-negative;
3. `maximum_bytes_billed` exists;
4. the per-query cap does not exceed the repository's existing WeatherNext source ceiling (`MAX_ALLOWED_BYTES_BILLED`, currently 1 GiB/query);
5. the dry-run estimate does not exceed that item's explicit cap;
6. the query is partition bounded;
7. only selected columns are requested;
8. model version and schema fingerprint match the frozen accounting policy.

Missing estimate evidence does **not** become zero. If any required estimate is missing, daily/weekly/monthly `projected_bytes` remain `null` and the result is `BLOCKED`.

## Run-class and period accounting

The accounting policy defines planned runs per day for both WeatherNext run classes. For each run class, the evaluator sums all required sanitized query-role dry-run estimates into `estimated_bytes_per_run`.

When evidence is complete:

```text
daily projected bytes
  = sum(estimated bytes per run class × planned runs per day)

weekly projected bytes
  = daily projected bytes × 7

monthly planning envelope
  = daily projected bytes × 31
```

The 31-day monthly value is intentionally a conservative deterministic planning envelope. It is not a statement of actual calendar-month billed usage.

Each period has separately configured warning and blocking thresholds:

- below warning -> `PASS` for the period;
- at/above warning but not above blocking -> `WARN`;
- above blocking -> `BLOCKED`.

A blocking result prevents the accounting gate from declaring the plan eligible. It does not change BigQuery settings and it does not stop or start a runtime scheduler because none is authorized here.

## Quota evidence

Quota state is explicit input. The contract accepts:

- `known_within_limit` with an explicit byte limit and current used-byte evidence;
- `known_exceeded`;
- `unknown`.

`unknown` is `QUOTA_STATE_UNKNOWN` and fails closed. `known_exceeded` is `QUOTA_EXCEEDED`. When a known remaining byte envelope is smaller than the projected next daily collection envelope, the result also blocks with `QUOTA_EXCEEDED`.

No Google default quota is treated as the user's actual current quota. A later private-access preflight must bind fresh quota evidence appropriate to the exact project/runtime before a real read is authorized.

## Stable reason codes

Blocking/query reasons:

- `DRY_RUN_REQUIRED`
- `DRY_RUN_ESTIMATE_MISSING`
- `MAXIMUM_BYTES_BILLED_MISSING`
- `MAXIMUM_BYTES_BILLED_POLICY_OVERFLOW`
- `PER_QUERY_CAP_OVERFLOW`
- `PARTITION_BOUND_REQUIRED`
- `SELECTED_COLUMNS_REQUIRED`
- `RUN_CLASS_ESTIMATE_MISSING`
- `QUOTA_STATE_UNKNOWN`
- `QUOTA_EXCEEDED`
- `PERIOD_BUDGET_EXCEEDED`
- `MODEL_VERSION_PLAN_CHANGED`
- `SCHEMA_FINGERPRINT_PLAN_CHANGED`
- `DUPLICATE_QUERY_PLAN_ITEM`

Warning-only reason:

- `PERIOD_BUDGET_WARNING`

Reason codes are machine-readable and deterministic. Model/schema drift is never silently merged into the previous cost envelope.

## Receipt identity

`plan_fingerprint` is SHA-256 over canonical sanitized policy/evidence/quota identity. Raw plan item IDs are hashed before entering the fingerprint material and are never emitted in the output.

Reordering the same evidence therefore preserves the fingerprint, while material changes in estimates, model/schema identity, caps, cadence, budgets or quota evidence change it.

## Safety boundary

A `PASS` means only that the supplied source-side planning evidence satisfies this accounting contract. It does **not** prove:

- real private WeatherNext access;
- actual billed cost;
- actual BigQuery quota state beyond the supplied evidence;
- permission to execute a query;
- permission to change a quota/budget;
- permission to write the production corpus;
- permission to activate recurring collection.

Those remain separate exact owner gates under the repository trust boundary. In particular, the parked WeatherNext private first-access issue #122 remains a separate authorization class.

## Tests

`tests/test_weathernext_cost_accounting.py` covers:

- normal deterministic envelope;
- one expensive query exceeding its explicit cap;
- monthly accumulation overflow;
- missing dry-run estimate evidence;
- missing run-class evidence;
- unknown/exhausted quota evidence;
- model/schema plan change;
- partition/selected-column/dry-run/cap requirements;
- the existing 1 GiB source ceiling;
- privacy-safe output and the absence of real query/write/scheduler side effects.
