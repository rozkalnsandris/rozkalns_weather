# SQLite schema evolution and migration compatibility gate

Issue #75 defines a source-only review gate for future SQLite schema changes. The gate plans and classifies candidate transitions using deterministic in-memory fixtures; it does **not** open or mutate the production database.

Machine contract: `contracts/sqlite-schema-evolution-v1.json`

Planner:

```bash
python -m rozkalns_weather.schema_evolution
```

## Version model

The current reviewed SQLite application schema is labeled schema version `1` for this migration-planning contract. The only supported next transition is `1 -> 2`.

A candidate transition must provide explicit migration metadata:

- `contract_id`;
- `from_version` and `to_version`;
- ordered operations;
- preconditions;
- rollback semantics.

Missing metadata is `BLOCKED`. Later schema versions must extend the machine contract explicitly rather than being inferred from live state.

## Compatibility invariants

Before a candidate migration is planned, the fixture schema must still satisfy the current corpus guarantees:

- `forecast_runs` and `forecast_values` immutability triggers are present;
- forecast-run uniqueness remains provider/model/location/init/retrieval aware;
- forecast-value uniqueness remains run/location/valid-time/variable/statistic/window aware;
- observation identity is preserved;
- provider-health identity remains keyed by provider;
- provider/model, location, init/retrieval, value/statistic and revision provenance columns remain present.

If the baseline already violates one of these guarantees, the planner returns `BLOCKED` before evaluating candidate operations.

## Allowed source-side transition classes

The gate permits planning only two additive classes:

1. `add_column` using a bounded SQLite type set. A non-null column must define a default.
2. `create_index` only when the index is non-unique and all referenced columns already exist or are added by the same contract.

The planner never executes these DDL operations. Tests may materialize the same operations only inside deterministic `:memory:` fixture databases in order to verify partial and already-applied states.

New unique constraints, drops, renames, table rebuilds, constraint rewrites and other destructive/ambiguous operations are `BLOCKED`. A destructive operation touching provider/model/value provenance additionally emits `PROVENANCE_LOSS_RISK`. Such work needs a separate explicit reviewed migration contract and later a separate production mutation authorization.

## Partial and idempotent transitions

Each declared operation is classified as `PENDING`, `APPLIED` or `BLOCKED` against the source fixture:

- all pending -> `PASS` / `PLAN`;
- all applied with the exact declared shape -> `PASS` / `ALREADY_APPLIED` and `IDEMPOTENT_RERUN`;
- a mix of applied and pending -> `BLOCKED` / `PARTIAL_MIGRATION_DETECTED`;
- an existing column/index with a conflicting definition -> `BLOCKED`.

This keeps reruns deterministic while refusing to guess how an incomplete migration should be repaired.

## Privacy-safe evidence

The evidence object contains only schema identities, table/column/index names, operation states, reason codes, preconditions and rollback semantics. It deliberately excludes:

- production database paths;
- corpus rows;
- home/private coordinates;
- credentials or tokens.

The schema identity is represented by a deterministic SHA-256 over normalized schema metadata rather than raw runtime paths or data.

## Rollback semantics

This source gate does not grant rollback authority. Additive column reversal is never automatic because it can require a table rebuild or restore. An index rollback may later drop only the exact newly authorized index, and only under a separate production authorization. Backup/restore, `VACUUM`, `ANALYZE`, filesystem work and production data rewrites remain outside this issue.

## Production boundary

A `PASS` result means only that a candidate migration is reviewable and source-compatible. Before any real production SQLite schema/index change, a separate exact owner authorization must bind the reviewed source/release, target database, exact DDL, backup/readiness evidence, verification steps and rollback authority.

Issue #75 performs no production SQLite file rewrite, schema/index mutation, backup/restore, `VACUUM`, `ANALYZE`, host/filesystem change or runtime/LIVE mutation.
