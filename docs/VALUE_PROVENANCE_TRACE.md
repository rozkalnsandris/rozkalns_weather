# Value provenance trace

`value-provenance-trace-v1` is the source-side contract for tracing a displayed or verified weather value back to the exact stored provider snapshot and its normalization/verification identity.

## Forecast identity

Every admissible forecast trace binds:

- `provider`, `model_provider`, `model_name`, and exact `model_version`;
- immutable snapshot identity from `forecast_runs.raw_payload_hash` plus `revision`;
- `source_surface` and optional transport provider;
- `init_time_utc`, `retrieved_at_utc`, defensible upstream availability when present, `valid_time_utc`, and `lead_hours`;
- normalized `variable`, `statistic`, `value`, `unit`, accumulation window and quality state;
- native value/unit when retained by the adapter.

The trace identity is a SHA-256 of canonical JSON over those fields. A missing or malformed snapshot hash is BLOCKED rather than replaced by a synthetic identifier.

## Privacy boundary

Private-home traces expose only the logical location identity:

```json
{"id":"home","scope":"private_home","coordinates_exposed":false}
```

They never return `HOME_LAT`, `HOME_LON`, latitude/longitude, database paths, credentials or raw logs. The canonical measured benchmark is `station_05480` / DWD CDC 05480. Historical `station_10416` remains legacy compatibility evidence and is not rewritten.

## API surfaces

`GET /api/hourly` keeps its existing provider-level row surface and adds one additive field, `provenance_trace`, per value. Missing provenance blocks the trace only; it does not fabricate or hide the stored provider value.

`GET /api/provenance/verification` resolves one `station_05480` forecast value and the exact DWD CDC 05480 observation at the same valid time/variable. The response binds forecast trace identity, truth trace identity and metric identity. Missing forecast/truth inputs return privacy-safe BLOCKED evidence with stable reason codes.

No endpoint creates a Combined/blended value.

## PWA drilldown

`static/provenance_v1.js` is additive to the existing overview. Hourly cards remain provider values. Selecting a card shows:

- provider/model/version;
- snapshot hash and revision;
- init, valid, lead and retrieval time;
- variable/statistic/unit;
- source surface.

When `station_05480` is selected, the same drilldown requests the verification trace and additionally shows DWD truth identity, observation time, metric identity and verification trace identity. Failure to load provenance does not hide the forecast card.

## Fail-closed reason codes

The machine-readable contract is `contracts/value-provenance-trace-v1.json`. Important reasons include `MISSING_SNAPSHOT_ID`, `BROKEN_LINEAGE`, `MIXED_MODEL_VERSIONS`, `VERIFICATION_RECEIPT_MISMATCH`, `FORECAST_VALUE_NOT_FOUND` and `TRUTH_VALUE_NOT_FOUND`.

## Authority

This contract is read-only. It grants no production corpus write, historical repair/rewrite, private coordinate disclosure, runtime deployment or LIVE mutation authority.
