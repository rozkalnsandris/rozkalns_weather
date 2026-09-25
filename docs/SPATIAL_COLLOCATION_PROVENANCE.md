# Spatial collocation and grid-identity provenance

Issue #100 adds a source-only `spatial-collocation-provenance-v1` gate for verification and report lineage. It does not query providers, mutate the corpus, change SQLite schema/indexes, or authorize runtime/LIVE work.

## Canonical benchmark identity

Measured verification is bound to the public DWD CDC benchmark `station_05480` / station `05480`. `station_10416` remains legacy compatibility evidence and is rejected by the canonical spatial gate. The private `home` identity is also rejected from measured benchmark receipts.

Spatial receipts intentionally contain **no coordinates**. A report can state that the benchmark is `station_05480` and preserve station/grid provenance without publishing `HOME_LAT`, `HOME_LON`, or any private point.

## Forecast spatial identity

Each forecast spatial receipt binds:

- benchmark `location_id`;
- provider and model identity;
- exact `source_surface`;
- variable;
- provider-native resolution, or the explicit marker `provider_native_not_exposed` when a transport API does not expose it;
- grid/product role;
- sampling mode;
- interpolation/resampling mode;
- transport provider when applicable.

Missing or vague grid/interpolation identity fails closed. The gate never fills unknown metadata with a guessed resolution.

### WeatherNext 3

The existing WeatherNext adapter exposes two materially different product surfaces and the spatial contract preserves them exactly:

| Source surface | Resolution | Role | Sampling/interpolation identity |
| --- | --- | --- | --- |
| `BigQuery WeatherNext 3 0p05` | `0p05deg` | `station_head` | `station_head` |
| `BigQuery WeatherNext 3 0p1` | `0p1deg` | `surface` | `surface_grid_cell` |

A 0.05° station-head value must never be relabeled as a 0.1° surface value, or vice versa. Resolution, source-surface and interpolation drift have separate stable reason codes.

### Public-provider transport caveat

The current Open-Meteo single-run adapters preserve upstream model identity but already document that transport may interpolate model-native timesteps. #100 adds the spatial equivalent: values transported through `Open-Meteo Single Runs API` must explicitly use `transport_interpolated_or_resampled`; their native grid may be recorded as `provider_native_not_exposed` rather than guessed.

This does **not** claim Open-Meteo is the native model grid. It makes the uncertainty explicit and machine-checkable.

## Verification/common-sample gate

`validate_common_sample_spatial()` requires:

1. exact DWD station 05480 truth identity;
2. every forecast receipt to target `station_05480`;
3. every provider/model/variable group to keep one stable source surface, resolution, sampling mode and interpolation mode;
4. reproducible receipt hashes;
5. coordinate-free evidence.

The gate rejects accidental `home`/station mixing and legacy 10416 evidence. It also rejects source-surface, grid-resolution or interpolation drift instead of silently combining those rows in one metric sample.

Different providers may legitimately have different grids. Compatibility means that each provider declares its own spatial identity while mapping the verification sample to the same canonical station benchmark; it does **not** mean pretending all grids have the same resolution.

## Report lineage

`bind_spatial_sample_to_report_lineage()` follows the existing resampling-lineage pattern. It keeps `verification-report-lineage-v1`, validates the existing lineage hash, adds only a privacy-safe `configuration.spatial_collocation` binding, then deterministically recomputes `configuration_sha256` and `lineage_identity_sha256`.

No report-lineage schema migration is required, and existing receipts without #100 spatial evidence remain byte-for-byte compatible.

## Stable reason codes

- `MISSING_SPATIAL_IDENTITY`
- `PRIVATE_HOME_BENCHMARK_FORBIDDEN`
- `LEGACY_LOCATION_NOT_CANONICAL`
- `LOCATION_IDENTITY_MISMATCH`
- `STATION_IDENTITY_MISMATCH`
- `SOURCE_SURFACE_DRIFT`
- `GRID_RESOLUTION_DRIFT`
- `UNKNOWN_GRID_RESOLUTION`
- `UNKNOWN_INTERPOLATION_IDENTITY`
- `INTERPOLATION_MODE_DRIFT`
- `WEATHERNEXT_SURFACE_MISMATCH`
- `COLLOCATION_INCOMPATIBLE`
- `SPATIAL_RECEIPT_IDENTITY_MISMATCH`
- `EMPTY_SPATIAL_SAMPLE`

## Authority boundary

This contract is source/docs/tests only. It grants no authority to:

- expose or commit private-home coordinates;
- choose a nearest-station fallback;
- rewrite historical `station_10416` evidence;
- rewrite production corpus rows;
- query WeatherNext or another provider;
- change runtime, Docker/systemd, Cloudflare/network, or LIVE state.
