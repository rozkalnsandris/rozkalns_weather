# DWD observation revision/finality contract v1

Status: source-only contract for `rozkalns_weather#78`.

## Purpose

`dwd-observation-revision-v1` makes changes in DWD CDC benchmark truth explicit across repeated retrievals. The current measured benchmark is DWD CDC station `05480` / `station_05480`; historical station 10416 evidence remains immutable legacy material and is not migrated by this contract.

The contract is read-only. It does not rewrite production observations, delete old truth, mutate provider state, modify SQLite/corpus data, or claim an official DWD publication/finality timestamp.

## Input model

A caller supplies an ordered sequence of retrieval snapshots. Each snapshot has a UTC `retrieved_at_utc` and the observations seen at that retrieval. Each observation is bound to:

- source provider, station, benchmark location, observed UTC time and variable;
- value/unit and quality status;
- DWD CDC provenance including product family/archive/value column, transport, source URL and retrieval timestamp.

Raw values and source URLs participate in deterministic hashing but are not emitted in the evidence object.

## Revision identity

The logical sample key is the deterministic hash of provider, station, location, observed UTC time and variable. Every retrieval also receives a revision identity derived from the sample key, content/provenance hash and retrieval timestamp.

`truth_revision_set_sha256` is the deterministic identity of the latest selected revision for every logical sample together with its contract finality state. `report_lineage.py` requires this identity and the evidence checksum, so a report cannot silently validate against a different DWD truth revision set.

## Contract finality

Finality is repository policy, not an official DWD finality declaration:

- `provisional`: no observed revision yet and insufficient unchanged retrieval history;
- `revised`: at least one content revision exists and the latest revision has not remained unchanged for the configured stability interval;
- `stable`: at least two retrievals exist and the latest content has remained unchanged for `stable_after_hours` while the observation itself is at least that old.

The default stability interval is 48 hours. The default declared revision window is 168 hours. These values are explicit evidence fields and can be overridden by callers without fabricating source timestamps.

## Stable reason codes

Blocking reason codes include `CONFLICTING_REVISION`, `SAMPLE_DISAPPEARED`, `LATE_REVISION_OUTSIDE_WINDOW`, `SOURCE_PROVENANCE_LOST`, source/station/location mismatches, incomplete identity and retrieval-provenance mismatch.

`QUALITY_STATUS_CHANGED` and `SOURCE_PROVENANCE_CHANGED` are warnings. `OBSERVATION_REVISED` is informational but keeps the evidence in `WARN` until the revision becomes stable under the contract.

## Privacy and authority

Evidence exposes hashes, counts, station/location identifiers, UTC retrieval bounds, finality counts and reason codes. It does not expose raw observation values, raw source URLs, coordinates, credentials or runtime logs.

This contract grants no LIVE/runtime authority and no production corpus/SQLite write authority.
