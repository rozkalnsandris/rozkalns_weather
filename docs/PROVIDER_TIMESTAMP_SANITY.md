# Provider timestamp sanity contract

`provider-timestamp-sanity-v1` is a source-side, read-only gate for deciding whether provider/provenance timing evidence is structurally safe to use in latency, freshness and verification analysis.

It does **not** prove that the runtime host clock is correct and it never changes system time, NTP state or stored provenance.

## Evidence classes

The gate keeps distinct timing concepts distinct:

- `init_time_utc` — model initialization identity;
- `expected_available_at_utc` — documented/planned dissemination target, not observed publication evidence;
- `upstream_available_at_utc` — observed upstream availability only when a defensible source supplied it;
- `ingest_attempt_at_utc` — local scheduler/ingest attempt evidence;
- `retrieved_at_utc` — retrieval evidence;
- `valid_time_utc` — forecast validity used to prove non-negative lead time;
- `observation_time_utc` — measured observation time;
- explicit reference time — caller-supplied comparison instant for bounded future-date checks;
- optional runtime-clock evidence — caller-supplied measured offset evidence, never inferred from repository source.

All persisted/provenance timestamps consumed by the gate must be canonical UTC. Timezone-naive or non-canonical local-offset timestamps fail closed.

## Clock evidence separation

Provider-clock suspicion is based only on contradictory observed provider evidence, for example observed upstream availability after retrieval or beyond the explicit future tolerance. A documented dissemination target is never treated as provider clock evidence.

Local-clock suspicion is reported only when explicit runtime clock evidence supplies an offset outside the source contract tolerance. When runtime clock evidence is absent, the state is `UNKNOWN` with `RUNTIME_CLOCK_EVIDENCE_UNAVAILABLE`; source code never upgrades that to proof of clock correctness.

Local scheduler delay remains the latency contract's separate concern. Timestamp sanity does not infer scheduler delay and does not turn timing anomalies into provider-outage claims.

## Stable fail-closed reasons

Representative BLOCKED reasons include:

- `TIMESTAMP_TIMEZONE_NAIVE`
- `TIMESTAMP_NOT_CANONICAL_UTC`
- `EXPECTED_AVAILABILITY_BEFORE_INIT`
- `UPSTREAM_AVAILABILITY_BEFORE_INIT`
- `UPSTREAM_AVAILABILITY_AFTER_RETRIEVAL`
- `INGEST_ATTEMPT_BEFORE_INIT`
- `INGEST_ATTEMPT_AFTER_RETRIEVAL`
- `RETRIEVAL_BEFORE_INIT`
- `NEGATIVE_LEAD_TIME`
- `OBSERVATION_AFTER_RETRIEVAL`
- `RETRIEVAL_FUTURE_BEYOND_TOLERANCE`
- `OBSERVATION_FUTURE_BEYOND_TOLERANCE`
- `UPSTREAM_AVAILABILITY_FUTURE_BEYOND_TOLERANCE`
- `RUNTIME_CLOCK_EVIDENCE_INVALID`

`LOCAL_CLOCK_SKEW_EVIDENCE` and `UPSTREAM_AVAILABILITY_UNOBSERVED` are explicit WARN evidence rather than fabricated timestamps or automatic outage conclusions.

## Latency/provider-health integration

`provider_latency_report()` keeps its existing latency classifications and reason codes for compatibility, while exposing a nested `timestamp_sanity` report and `latency_eligible` flag. A `BLOCKED` timestamp-sanity result makes that timing evidence ineligible even if a numerical latency could otherwise be calculated.

`provider_health_latency_summary()` carries the provider-scoped timestamp-sanity surface into provider health. It does not reclassify the provider's freshness state and does not claim an outage.

## Runtime boundary

This contract is source evidence only. Runtime clock correctness requires fresh trusted runtime evidence from the `RPi5_main` boundary when a later work item actually needs it. Repository source, CI success, a documented timezone or an expected NTP configuration are not runtime clock proof.

No operation in this contract authorizes system clock/NTP mutation, production timestamp rewrite, provider polling, fabricated publication timestamps or LIVE/runtime mutation.
