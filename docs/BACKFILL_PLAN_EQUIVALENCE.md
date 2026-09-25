# Backfill plan-to-execution equivalence

`backfill-plan-equivalence-v1` freezes the reviewed source-only backfill plan before any separately authorized production execution.

The deterministic plan identity includes the exact source SHA, date window, provider/model set, run hours, truth chunks, rate limits, checkpoint namespace and recovery decision. Its canonical JSON SHA-256 digest is the binding carried into sanitized execution evidence.

`validate_execution_equivalence()` is read-only. It returns `PASS` only when the execution evidence remains inside the exact frozen plan envelope. Widening dates, adding providers/models or run hours, changing chunking or rate limits, changing checkpoint namespace/recovery semantics, or presenting a non-prefix/reordered checkpoint is `BLOCKED`.

Operational timestamps, counters, attempt number and free-form note are progress metadata and do not change plan identity. Progress metadata cannot be used to smuggle material scope fields; unsupported progress keys are blocked.

The validator also rejects private paths, credentials, raw logs, HOME_LAT/HOME_LON and related private evidence fields without echoing their values.

A `PASS` result proves **scope equivalence only**. It does not authorize a production SQLite/corpus write, runtime/LIVE mutation, network fetch, checkpoint mutation, retry, restore, delete or cleanup. Those remain under separate exact owner authority.

The existing `production_bootstrap.py` and `production_bootstrap_evidence.py` contracts continue to own bootstrap correctness and execution-evidence validation. This contract adds the missing reviewed-plan binding in front of them; it does not execute backfill work or mutate their checkpoint/data paths.
