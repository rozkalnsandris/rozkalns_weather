# Recovery-readiness fault-injection gate

Contract: `recovery-readiness-fault-injection-v1`

This source gate proves that recovery evidence fails closed when deliberately damaged **synthetic disposable** SQLite/manifest/backup artifacts are presented to the existing readiness validators. It does not verify a real backup and it never restores, repairs, deletes or rewrites production data.

## Scope

`run_recovery_readiness_fault_injection()` accepts no database path, backup path, host path or restore target. Every execution creates a private `TemporaryDirectory`, builds one deterministic reference SQLite fixture, and copies that fixture into one independent candidate per fault scenario. Fault injection is performed only on those candidate copies.

The reference fixture is hashed before and after all scenarios. A suite run cannot PASS if the reference fixture changed. No temporary path is emitted in the returned evidence.

The gate reuses existing repository contracts rather than inventing replacement validators:

- `corpus-retention-readiness-v1` validates backup presence, SHA-256/source metadata, SQLite integrity evidence and required-table readiness;
- `corpus-provenance-manifest-v1` reads the candidate database read-only and validates schema identity, provider/model provenance and forecast revision chains;
- `sqlite-schema-evolution-v1` remains the canonical compatibility contract for any future schema transition. This issue does not execute a migration.

## Scenarios

The deterministic suite contains:

| Scenario | Expected recovery classification | Key evidence |
| --- | --- | --- |
| `valid_backup` | `VALID_BACKUP` / PASS | matching candidate checksum, manifest checksum, one unambiguous source SHA, SQLite quick-check OK, required tables present |
| `truncated_sqlite` | `INVALID_BACKUP` / BLOCKED | unreadable/corrupt or failed integrity evidence plus checksum mismatch |
| `checksum_mismatch` | `INVALID_BACKUP` / BLOCKED | `BACKUP_CHECKSUM_MISMATCH` |
| `missing_required_table` | `INVALID_BACKUP` / BLOCKED | `REQUIRED_TABLES_MISSING`, retention table-readiness blocker, manifest schema blocker |
| `broken_provenance_chain` | `INVALID_BACKUP` / BLOCKED | existing manifest validator emits `BROKEN_REVISION_CHAIN` |
| `incompatible_schema_identity` | `INCOMPATIBLE_SCHEMA` / BLOCKED | manifest schema identity differs from the reference identity |
| `ambiguous_source_identity` | `AMBIGUOUS_SOURCE_IDENTITY` / BLOCKED | multiple source-SHA candidates cannot be defaulted to one source |
| `missing_metadata` | BLOCKED | empty/missing checksum and source metadata remains invalid; no fallback default can produce PASS |

The suite itself reports PASS only when `valid_backup` passes, every injected-fault scenario blocks, and the reference fixture is unchanged. A suite PASS therefore means **the safety checks behaved correctly**; it is not a statement that any damaged backup is recoverable.

## Stable reason codes

The wrapper preserves reason codes emitted by the existing validators and adds only recovery-specific normalization where needed:

- `BACKUP_CHECKSUM_MISMATCH`
- `CORPUS_MANIFEST_CHECKSUM_MISMATCH`
- `SQLITE_UNREADABLE_OR_CORRUPT`
- `SQLITE_INTEGRITY_FAILED`
- `REQUIRED_TABLES_MISSING`
- `SOURCE_IDENTITY_AMBIGUOUS`
- `SCHEMA_IDENTITY_INCOMPATIBLE`
- `CORPUS_MANIFEST_UNREADABLE`
- `REFERENCE_FIXTURE_MUTATED`
- `UNEXPECTED_SCENARIO_OUTCOME`

Examples of reused lower-level blockers include `BACKUP_SHA256_INVALID`, `BACKUP_REQUIRED_TABLES_INCOMPLETE`, `BROKEN_REVISION_CHAIN`, `SCHEMA_TABLE_SET_MISMATCH` and `SCHEMA_COLUMNS_MISMATCH:<table>`.

## Recovery-readiness interpretation

`VALID_BACKUP` means only that the **synthetic fixture** satisfied the source-side evidence contract. It grants no authorization to inspect a production backup, select a restore target or perform a restore.

`INVALID_BACKUP` means one or more integrity/checksum/provenance/readability prerequisites failed. It must not be promoted by missing metadata, default values or best-effort recovery logic.

`AMBIGUOUS_SOURCE_IDENTITY` means the evidence cannot bind the backup to exactly one reviewed source identity. Recovery planning stops until an owner resolves the identity outside this source-only gate.

`INCOMPATIBLE_SCHEMA` means the candidate schema identity does not match the reviewed reference contract. This gate does not migrate or repair the candidate.

## Future owner gates

Issue #96 activates none of the following gates. They are documented so a future real recovery remains explicit and reviewable.

### 1. `REAL_BACKUP_VERIFICATION`

Read-only evidence gate. It must bind at minimum:

- exact host;
- exact backup identity;
- backup SHA-256;
- reviewed source SHA;
- corpus-manifest SHA-256.

This gate may verify evidence but does not select a restore target and does not mutate production data.

### 2. `RESTORE_TARGET_SELECTION`

Owner decision gate. It must bind at minimum:

- exact restore-target identity;
- previously verified backup identity;
- reviewed source SHA;
- explicit accepted recovery decision.

Selecting a target still does not authorize a restore.

### 3. `PRODUCTION_RECOVERY_MUTATION`

Separate LIVE/data authorization. Before any production mutation it must bind at minimum:

- exact host;
- reviewed source/release SHA;
- exact backup SHA-256;
- exact restore target;
- exact mutation;
- affected resources;
- verification semantics;
- rollback semantics.

Any mutation-time error, timeout, source/target drift, lock conflict, health regression or authorization ambiguity remains fail-closed. No retry, rollback, cleanup, repair, service restart or alternate mutation is implied unless the applicable authorization explicitly predeclares it.

## Explicit non-authority

This contract grants no production backup/restore, no production SQLite corruption test, no schema/data migration, no corpus rewrite, no filesystem cleanup, no runtime/host mutation, no Docker/systemd/timer action, no secret/credential/permission/network/Cloudflare change and no WeatherNext private-data access.
