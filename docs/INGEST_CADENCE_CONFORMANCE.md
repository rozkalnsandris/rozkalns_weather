# Public ingest cadence conformance

Issue #68 adds a source-level, read-only contract for distinguishing scheduler/cycle conformance from provider publication freshness.

## Canonical source contract

`deploy/public-ingest-schedule.json` remains the reviewed deployment schedule contract. The application-side helper in `src/rozkalns_weather/ingest_cadence.py` mirrors the fields needed for deterministic evaluation and tests fail when those values drift:

- cadence: `PT30M`;
- scheduler owner: `RPi5_main`;
- `RandomizedDelaySec=60` plus `AccuracySec=60`, represented as a bounded 120-second scheduling jitter budget;
- persistent catch-up policy: one catch-up after downtime;
- overlap policy: one systemd oneshot plus the application file lock rejects a second overlapping ingest.

The source contract does **not** assert that a timer is installed, enabled, active, or healthy on the live RPi5. Those are runtime facts and require separate read-only LIVE evidence when a future work item explicitly asks for them.

## Sanitized cycle evidence

`public_ingest_cadence_report(...)` accepts explicit sanitized evidence. Each evidence row binds:

- `provider` — one of the public recurring providers;
- `scheduled_for_utc` — an exact `:00` or `:30` UTC schedule slot;
- `attempted_at_utc` — when the cycle attempt actually started;
- optional `completed_at_utc`;
- `outcome` — `success`, `failure`, or `overlap_rejected`.

Raw service logs, filesystem paths, credentials, coordinates and provider payloads are deliberately outside this evidence contract. Unknown extra evidence fields are not exported.

The helper builds one deterministic row for every provider and expected slot in the requested half-open window. It exposes the independent boolean classifications `expected`, `attempted`, `successful`, `missed`, `overlapping`, `delayed`, `failed` and `pending`.

A cycle is delayed only when `attempted_at_utc` is later than the reviewed 120-second jitter budget. An absent attempt is a scheduler/cycle miss only after that slot's jitter deadline has passed. `overlap_rejected` is an observed attempt, but not a successful provider cycle.

## Stable states and reason codes

The cycle-conformance surface uses the following stable states/reasons:

| State | Reason code | Meaning |
| --- | --- | --- |
| `PASS` | `CADENCE_CONFORMANT` | Mature cycles in the window conform and the latest provider cycle is healthy. |
| `PASS` | `NORMAL_OPERATION_RESUMED` | Earlier provider failures are preserved in the ledger and a later normal cycle recovered. |
| `PASS` | `CYCLE_WINDOW_PENDING` | The selected window contains no mature cycle yet. |
| `WARN` | `DELAYED_CYCLE_ATTEMPT` | Latest attempt started outside the bounded schedule jitter. |
| `WARN` | `OVERLAP_REJECTED` | Latest cycle was rejected by overlap protection. |
| `WARN` | `PROVIDER_CYCLE_FAILED` | Latest provider cycle failed once. |
| `WARN` | `REPEATED_PROVIDER_FAILURE` | Latest provider state ends in at least two consecutive failed cycles. |
| `BLOCKED` | `MISSED_EXPECTED_CYCLE` | At least one mature expected cycle has no cycle evidence. |
| `BLOCKED` | `CYCLE_HISTORY_EVIDENCE_UNAVAILABLE` | No historical cycle evidence was supplied; host state is not invented from repository source or latest DB status. |
| `BLOCKED` | `CYCLE_EVIDENCE_INVALID` | Evidence is malformed, duplicated, unaligned, or outside the public provider contract. |

Historical failures remain counted even after recovery. The state describes the current end-of-window conformance while the immutable ledger preserves the earlier failures.

## Separation from provider freshness

Cadence conformance answers: **did the expected local collection cycle run on time and what happened to that provider attempt?**

`provider-freshness-v1` answers a separate question: **how old is the latest provider/source data and what was the latest ingest state?**

The cadence payload therefore explicitly sets:

- `upstream_publication_freshness_evaluated=false`;
- `provider_data_age_evaluated=false`;
- `host_state_assumed=false`.

A provider can have a perfectly conformant local 30-minute cadence while upstream data is lagging, or fresh upstream data while local scheduler cycles are missed. Consumers must not collapse those domains.

## Report and API helpers

- `public_ingest_cadence_report(...)` returns the full deterministic ledger and provider summaries for audit/report use.
- `public_ingest_cadence_api_payload(...)` returns the same privacy-safe state with a bounded recent-cycle ledger suitable for an API surface.
- Supplying `None` as evidence fails closed with `CYCLE_HISTORY_EVIDENCE_UNAVAILABLE`; the application database's latest provider status is not treated as historical scheduler evidence.

Both helpers are pure/read-only. They perform no host lookup, network request, systemd action, ingest retry, database write, scheduler restart, or LIVE mutation.

## Fixture coverage

`tests/test_ingest_cadence.py` covers:

- source/deploy schedule-contract drift;
- normal conformant cycles;
- missed expected cycles;
- delayed attempts outside jitter;
- overlap rejection;
- repeated provider failure;
- resumed normal operation after repeated failure;
- missing history fail-closed behavior;
- privacy-safe API payload truncation and suppression of raw private evidence fields.
