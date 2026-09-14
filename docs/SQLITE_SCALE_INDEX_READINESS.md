# SQLite scale and index readiness benchmark

Issue #59 adds a source-only benchmark for the growing immutable SQLite corpus. It does not read a production database and it does not change the production schema.

## Contract

Machine contract: `contracts/sqlite-scale-index-readiness-v1.json`

Runner:

```bash
python -m rozkalns_weather.sqlite_scale
python -m rozkalns_weather.sqlite_scale --scales large
```

The runner builds deterministic in-memory corpora for `small`, `medium`, and `large` scales. Every scale uses only synthetic forecast/observation rows and the current `SCHEMA_SQL`; it never opens a configured runtime database path.

The fixture grows from 8 to 64 to 256 run cycles per public provider. The benchmark records stable fixture row counts and a checksum over forecast runs, values, observations and provider status rows so candidate-index evaluation cannot silently change corpus identity.

## Query classes

The benchmark covers the six source query classes required by Issue #59:

- readiness/provider-status reads;
- bounded `corpus-report` forecast-run slices;
- provider freshness/latest-run lookup;
- station common-sample temperature verification joins;
- monthly verification aggregation;
- API-style latest forecast slices.

The SQL shapes mirror the current `db.py` / `corpus_reporting.py` access patterns. They use fixed fixture dates rather than `now`, so the source evidence is reproducible.

## Why plan shape, not wall-clock time

CI hardware and load make microsecond thresholds noisy. The regression gate therefore uses `EXPLAIN QUERY PLAN` and a deterministic plan score:

- `+4` for a scan of a large corpus table/alias;
- `+1` for another non-trivial scan;
- `+1` for each temporary B-tree sort/group operation;
- `WARN` at score `4`;
- `BLOCKED` at score `9`.

Wall-clock duration may be inspected separately later, but it is not a source CI gate.

The current schema is expected to produce `WARN`, not `BLOCKED`, for several growing-corpus access patterns. That warning is intentional evidence for the proposal below. The same synthetic corpus with proposal-only candidate indexes must have no plan regression, and every candidate plan must remain below the warning threshold.

## Proposal-only indexes

The machine contract proposes three indexes:

1. `idx_proposed_forecast_runs_location_provider_retrieved` for provider-health and latest API slices;
2. `idx_proposed_forecast_runs_location_provider_init` for bounded corpus-report windows;
3. `idx_proposed_forecast_values_variable_valid_run` for verification/monthly/API variable-time slices.

The benchmark may create these indexes only inside its in-memory synthetic database in order to compare plans. They are deliberately absent from `SCHEMA_SQL`.

The proposal includes exact `CREATE INDEX` and matching `DROP INDEX IF EXISTS` statements, expected query-class benefits, preconditions and rollback semantics.

## Production boundary

A `PASS`/`WARN` benchmark result is not production migration authority. Before any future production index change, a separate exact LIVE/data authorization must bind:

- current reviewed schema/source identity;
- production backup/readiness evidence;
- exact index names and SQL;
- maintenance/mutation budget;
- post-change `EXPLAIN QUERY PLAN` and integrity checks;
- explicit rollback authority/semantics.

This issue performs no production SQLite access, `VACUUM`, `ANALYZE`, filesystem mutation, host/runtime mutation, cleanup or destructive migration.
