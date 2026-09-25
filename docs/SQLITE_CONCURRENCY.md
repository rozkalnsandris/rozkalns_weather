# SQLite concurrency readiness contract

Contract: `sqlite-concurrency-wal-v1`

This gate proves source-side SQLite concurrency semantics against disposable synthetic databases. It is not a production performance benchmark and it does not change the production database configuration.

## Scope and authority

The runner in `rozkalns_weather.sqlite_concurrency` creates its own `TemporaryDirectory` and SQLite files. It never accepts a production database path. Issue #95 grants no authority to read or mutate production SQLite, change production `PRAGMA` values, tune the host/filesystem, restart services, or perform any LIVE/runtime mutation.

The gate therefore answers a narrow question: given the expected SQLite concurrency contract, do transaction visibility, contention classification, atomicity and retry semantics behave deterministically in source-level fixtures?

It does **not** prove RPi5 I/O latency, production lock frequency, real ingest duration or host capacity. Those are runtime observations and remain separate from this source-only evidence.

## Expected SQLite semantics

Disposable fixtures use:

- `journal_mode = WAL`;
- `busy_timeout = 100 ms`;
- explicit write acquisition with `BEGIN IMMEDIATE`;
- `PRAGMA foreign_keys = ON`;
- the repository's current `SCHEMA_SQL`, including forecast immutability triggers.

The short busy timeout is a deterministic test bound, not a production tuning recommendation. A future production setting decision must be reviewed separately against runtime evidence.

## Required scenarios

### One writer, many readers

A writer opens an explicit transaction and changes mutable provider-status evidence. Concurrent readers must continue to read the last committed state and must not see the uncommitted row. After commit, all readers must see the committed state.

Failure reasons include `PARTIAL_TRANSACTION_VISIBLE` and `COMMITTED_WRITE_NOT_VISIBLE`.

### Competing writers

A holder acquires the write transaction. A second writer must hit the bounded lock timeout rather than wait without bound. `WRITE_LOCK_TIMEOUT` is clean-retry eligible only after the conflicting lock is released and the retry starts a new transaction.

If the retry still cannot acquire the writer after release, the gate emits `WRITER_STARVATION`.

### Long reader plus writer

A reader holds a snapshot transaction. Under WAL, another connection must be able to commit an independent write. The original reader must keep its original snapshot until it ends the transaction, then observe the committed row in a new read.

Failures are classified as `LONG_READER_BLOCKED_WRITER`, `READER_SNAPSHOT_CHANGED_MID_TRANSACTION`, or `COMMITTED_WRITE_NOT_VISIBLE`.

### Failed and contended write atomicity

The gate hashes the immutable forecast-run/value identity before contention. A blocked competing writer must not alter it. A separate multi-statement write intentionally violates the existing uniqueness constraint; the full transaction must roll back and leave the immutable identity unchanged.

Failures are classified as `CONTENDED_WRITE_CHANGED_IMMUTABLE_IDENTITY` or `FAILED_WRITE_CHANGED_IMMUTABLE_IDENTITY`. The expected synthetic constraint failure is recorded as `TRANSACTION_CONSTRAINT_FAILURE`.

### Missing schema / implicit initialization

Worker-side inspection never initializes a missing schema. An empty disposable database must fail closed with both `REQUIRED_SCHEMA_MISSING` and `UNSAFE_IMPLICIT_SCHEMA_INIT_REQUIRED`, and inspection must not create tables as a side effect.

## Readiness interpretation

`PASS` means all deterministic fixture scenarios satisfied the source contract. `BLOCKED` means one or more scenarios violated the contract and includes stable reason codes plus the failing scenario names.

The evidence always declares:

- `source_only: true`;
- `host_performance_assessed: false`;
- `production_paths_read: false`;
- `production_mutation_performed: false`.

Do not reinterpret a source PASS as proof that production contention or storage latency is healthy. Production/runtime evidence requires a separate authorized work item when such evidence is actually needed.
