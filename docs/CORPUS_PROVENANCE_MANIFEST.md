# Corpus provenance manifest

Issue #57 defines `corpus-provenance-manifest-v1`, a deterministic, privacy-safe, read-only identity for a bounded slice of the immutable forecast and observation corpus.

## Purpose

The manifest makes report and verification inputs reproducible without exporting private runtime configuration or mutating the SQLite corpus. It binds a bounded date window to:

- the exact SQLite user-table/column schema identity;
- forecast snapshot identity: provider, model provider/name/version, location identity, init/retrieval time, init-time quality, source surface, raw payload SHA-256 and immutable revision;
- observation identity: source/station/location/time/variable/unit/quality plus a deterministic record SHA-256 that commits to the observation value without exposing it in the manifest entry;
- separate common-window and historical IFS-only sections;
- stable section checksums and one aggregate SHA-256 fingerprint.

The manifest is evidence. It does not grant production-data, runtime or LIVE authority.

## Read-only command

```bash
python -m rozkalns_weather.corpus_manifest \
  --start YYYY-MM-DD \
  --end YYYY-MM-DD
```

`DATABASE_URL` must point at an already existing SQLite corpus. The reader opens the file with SQLite `mode=ro` and `PRAGMA query_only = ON`. It never initializes or migrates a schema, repairs rows, rewrites hashes, changes revisions, or creates a backup.

The requested range is inclusive by date and limited to 180 days. Output state is `PASS`, `WARN`, or `BLOCKED`. `BLOCKED` exits with status 3.

## Determinism

Entries are sorted by semantic identity rather than insertion order. JSON used for fingerprints has sorted object keys, compact separators, UTF-8 encoding, a terminating newline and `allow_nan=False`.

Each section exposes:

```json
{
  "count": 0,
  "entries": [],
  "checksum_sha256": "..."
}
```

`aggregate_checksum_sha256` binds the schema identity, requested window, common-window sections and historical IFS-only sections. Logically identical frozen inputs therefore produce the same checksum even if rows were inserted in a different order. A material change to snapshot provenance, observation content, schema identity or the bounded window changes the fingerprint.

## Forecast revision-chain rules

For one `(provider, model_name, location_id, init_time_utc)` chain:

- revisions start at 1 and must be contiguous;
- the same revision identity may not appear twice;
- raw payload hashes may not repeat across different revisions;
- retrieval timestamps must remain ordered with revision progression;
- `raw_payload_hash` must be exactly 64 lowercase hexadecimal characters;
- required provider/model/init/retrieval/source provenance may not be missing.

Unknown provider identities or a provider whose stored `model_provider` / `model_name` no longer matches the registered source identity are `BLOCKED` rather than silently accepted.

A missing `model_version` is retained as missing and classified `WARN`; it is never fabricated.

## Observation identity

Observation entries retain source provider, station, location identity, UTC observation time, variable, unit and quality status. The value participates in `record_sha256`, but the raw value and `source_metadata_json` are not emitted by this manifest.

For `station_10416`, truth identity must remain DWD WMO `10416`. Duplicate observation identities, missing provenance, non-finite values or an incompatible station/source identity are `BLOCKED`.

## Schema identity

The reader compares the existing corpus against the current expected user tables and column types and produces a deterministic schema checksum. Unexpected/missing tables or changed column sets/types are `BLOCKED` with stable schema reason codes. This is validation only; no migration is attempted.

## Historical IFS separation

The public common comparison window starts on `2026-04-02`. Forecast snapshots before that boundary are placed only in `historical_ifs_only`, which has `excluded_from_common_readiness=true`.

Any pre-common forecast provider other than `ecmwf_ifs` is `BLOCKED` as `NON_IFS_PRE_COMMON_PROVIDER`. Historical evidence therefore cannot silently contaminate the common model-comparison identity.

## Stable reason codes

Representative blocking reasons include:

- `SCHEMA_TABLE_SET_MISMATCH`
- `SCHEMA_COLUMNS_MISMATCH:<table>`
- `MISSING_FORECAST_PROVENANCE`
- `UNEXPECTED_PROVIDER_IDENTITY`
- `PROVIDER_IDENTITY_MISMATCH`
- `INVALID_RAW_PAYLOAD_HASH`
- `INVALID_FORECAST_TIMESTAMP`
- `INVALID_REVISION`
- `DUPLICATE_SNAPSHOT_IDENTITY`
- `BROKEN_REVISION_CHAIN`
- `DUPLICATE_SNAPSHOT_PAYLOAD`
- `BROKEN_REVISION_RETRIEVAL_ORDER`
- `MISSING_OBSERVATION_PROVENANCE`
- `INVALID_OBSERVATION_PROVENANCE`
- `DUPLICATE_OBSERVATION_IDENTITY`
- `UNEXPECTED_OBSERVATION_SOURCE_IDENTITY`
- `NON_IFS_PRE_COMMON_PROVIDER`

`MODEL_VERSION_MISSING` is a warning rather than a fabricated replacement value.

## Privacy and authority boundary

The manifest does not emit exact coordinates, credentials, database paths, raw logs or `source_metadata_json`. It carries explicit false authority flags for production-data and runtime LIVE mutation.

Generating or validating this source contract does **not** authorize production corpus repair, rehash/rewrite, pruning, backup/restore, schema migration, RPi5 mutation, Docker/systemd changes, credentials, Cloudflare changes or WeatherNext private queries. Those remain separate owner-gated operations under the repository trust boundary.
