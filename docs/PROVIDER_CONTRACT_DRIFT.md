# Public provider contract-drift sentinel

Issue #55 freezes the source-side response identities used by the public DWD and
Open-Meteo adapters. The sentinel is deterministic and network-independent in
mandatory CI. It does not rewrite provider values or repair payloads.

## Classification

`COMPATIBLE` means the fields used by the adapter still match the frozen
contract. `WARN` records additive upstream fields that do not change current
semantics. `BLOCKED` rejects drift that could change station identity, run
identity, units, timestamp alignment, requested field identity, or ensemble
member shape.

Every finding has a stable machine-readable reason code. Blocking reports raise
`ProviderContractDriftError` before normalization. Compatible/warning reports
are retained in `source_metadata.provider_contract_drift`; raw provider
provenance and payload hashing remain unchanged.

## Frozen surfaces

- DWD observations transported through Bright Sky: `sources`/`weather`
  structure, WMO station `10416`, timestamp/source linkage, and the observation
  fields consumed by the project.
- DWD MOSMIX-L KMZ/KML: readable KML archive, `IssueTime`, `TimeStep`, supported
  DWD `elementName` identifiers, and one value token per forecast timestep.
- Open-Meteo Single Runs: explicit requested hourly field names, hourly units,
  ISO timestamps, plus separate model metadata for initialization and API
  availability.
- Open-Meteo Ensemble: requested member columns, units, timestamps, and a
  consistent member identity set across variables in the same snapshot.

The Open-Meteo metadata contract keeps initialization and availability separate.
The adapter's existing 10-minute replication safety window remains unchanged.
Individual Open-Meteo ensemble member history remains short-retention; the
sentinel does not fabricate expired members or infer exact initialization where
the surface does not provide it.

## Stable blocking reason codes

Representative blocking codes include `FIELD_MISSING`, `UNIT_DRIFT`,
`TIMESTAMP_INVALID`, `RUN_METADATA_INVALID`, `STATION_MISMATCH`,
`SERIES_LENGTH_MISMATCH`, `MEMBER_COLUMN_INVALID`, and
`MEMBER_SHAPE_MISMATCH`. Additive fields use `FIELD_ADDED` at warning level.

## Safety boundary

This contract performs no provider polling by itself, no production ingest or
corpus mutation, no credential/account changes, no automatic adapter rewrite,
and no LIVE/RPi5 mutation. Optional public smoke checks, if added later, must
remain sanitized and read-only.
