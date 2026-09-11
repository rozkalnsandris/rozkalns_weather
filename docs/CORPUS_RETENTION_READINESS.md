# Corpus retention, storage budget and backup readiness

Issue #46 defines a **source-only** contract for deciding whether the immutable public weather corpus is operationally ready to keep growing. It does not inspect production storage and it does not authorize or perform pruning, backup, restore, filesystem, SQLite, Docker/systemd or other LIVE mutations.

## Retention classes

`src/rozkalns_weather/retention.py` defines the machine-readable `corpus-retention-readiness-v1` contract.

| Artifact class | Policy | Minimum |
| --- | --- | --- |
| `deterministic_runs` | immutable benchmark snapshots | no automatic expiry |
| `ensemble_members` | bounded raw-member retention | 3 days |
| `observations` | immutable verification truth | no automatic expiry |
| `verification_artifacts` | reproducibility evidence | no automatic expiry |
| `reports` | published/audit evidence | no automatic expiry |

The three-day ensemble-member boundary matches the existing public-ensemble source contract. It is **not** automatic deletion authority. Any pruning requires a separately reviewed destructive LIVE/data gate, must preserve the provenance/manifest chain and must never silently rewrite benchmark history.

Unknown artifact classes fail closed. A proposed retention override also fails closed when it attempts silent pruning, shortens the ensemble-member minimum below three days, or assigns an expiry to an immutable class.

## Deterministic storage estimate

The contract estimates storage without reading a host path, filesystem free-space value or production database:

```text
estimated_total_bytes = Σ(count[class] × fixed_estimated_bytes_per_item[class])
utilization_fraction = estimated_total_bytes / declared_storage_budget_bytes
```

Per-item estimates are fixed source constants so the same input yields the same result in CI and in later sanitized evidence validation. They are planning estimates, not measurements of the production filesystem.

State thresholds:

- `< 0.75` → no storage-budget reason;
- `>= 0.75` and `< 0.90` → `WARN` / `STORAGE_BUDGET_WARN`;
- `>= 0.90` → `BLOCKED` / `STORAGE_BUDGET_BLOCKED`.

A later policy change to estimates or thresholds is a normal reviewed source change. It must not be inferred from current RPi5 disk usage.

## Backup readiness evidence

Backup readiness is proven only from sanitized caller-supplied evidence:

- `backup_present=true`;
- 64-hex `backup_sha256`;
- 64-hex `corpus_manifest_sha256`;
- exact 40-hex reviewed `source_sha`;
- `integrity_check="ok"`;
- `required_tables_present=true`.

Private paths, credentials/tokens/secrets, raw logs and home-coordinate fields are rejected. The evaluator never opens the backup or production database itself.

A PASS only means that the supplied sanitized evidence satisfies the source contract. Restore still requires all of the following preconditions to be bound by a separate owner-authorized LIVE/data operation:

1. exact LIVE/data authorization;
2. exact reviewed source SHA;
3. matching corpus-manifest checksum;
4. verified backup checksum;
5. SQLite integrity check success;
6. required tables present;
7. explicit restore target identity;
8. pre-restore snapshot or explicit owner recovery decision.

## Destructive actions remain separate gates

Issue #46 grants **no** authority for:

- production corpus delete/prune;
- production backup creation;
- restore or rollback;
- filesystem mutation;
- SQLite schema/data mutation;
- RPi5, Docker, systemd or timer mutation.

The readiness payload therefore always reports these authority flags as `false`. Cleanup, retention enforcement, backup execution and restore execution must be separately authorized against a freshly identified production target and reviewed source SHA.
