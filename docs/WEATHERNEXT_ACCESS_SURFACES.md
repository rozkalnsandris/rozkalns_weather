# WeatherNext 3 access-surface evaluation

This is a **source-only** decision record for issue #122. It does not authorize a Google request, credential/IAM/quota mutation, RPi5/runtime change, WeatherNext canary, or production SQLite/corpus write.

Canonical machine record: `deploy/weathernext-access-surface-evaluation.json`.

## Why this evaluation exists

The existing BigQuery first-access contract correctly uses an exact `init_time` partition filter, selected columns, a bounded forecast-hour window and a spatial predicate. The private dry-run characterization nevertheless returned multi-TiB **pre-execution upper bounds** for the two clustered WeatherNext tables.

Those estimates are not proof of actual billed bytes after cluster block pruning. They are also not a defensible reason to widen the repository's 1 GiB real-query guard to multi-TiB. Therefore:

- BigQuery remains the existing first-access implementation surface;
- the BigQuery **real query is blocked** under #122;
- the 1 GiB real-query ceiling is retained;
- no retry, alternate SQL path or cap increase is authorized by this document.

## Surface comparison

| Surface | Fit for bounded `station_05480` first access | Cost/control characteristic | Decision |
| --- | --- | --- | --- |
| BigQuery | Existing adapter and provenance path already exist | Clustered-table pre-execution upper bound conflicts with retained 1 GiB `maximum_bytes_billed` guard | **Blocked for real query** |
| GCS precomputed statistics Zarr | Precomputed 0.05°/0.1° surface statistics, lazy chunked access, continuous hourly lead axis | Google documents the statistics bucket as Requester Pays OFF and its example does not require a billing-project header | **Preferred source candidate** |
| Earth Engine | 0.05°/0.1° ImageCollections, init/hour filters, spatial filtering and point/region reduction | Requires an Earth Engine-registered Cloud project/API and has a separate EECU/quota governance model | **Secondary candidate; new gate required** |

## Why GCS statistics Zarr is the preferred candidate

The statistics store is the smallest semantic change from the existing first-access objective:

- it exposes the same six required statistics: `mean/p10/p25/p50/p75/p90`;
- it covers the 0.05° station-oriented and 0.1° gridded surface products;
- its `lead_time` axis is already flattened to continuous 1-hour steps;
- Zarr/Xarray access is lazy and Google explicitly recommends slicing variables, region and time before loading;
- unlike the full 64-member ensemble bucket, the statistics bucket is documented as **Requester Pays OFF**;
- the project does not need the raw ensemble or pressure-level fields for the first bounded benchmark canary.

Requester Pays OFF does **not** mean "no infrastructure cost exists anywhere". It means this source candidate does not require the requester-billing header that the full-ensemble bucket requires. No billing or private-access claim is made until a separately authorized real access test exists.

## Why Earth Engine is not first choice

Earth Engine can express the same bounded conceptual query using `start_time`, `forecast_hour`, `filterBounds()`, selected bands and `reduceRegion()`. It also exposes `ingestion_time_utc`, which could be useful future provenance.

However, choosing it now would add a new control plane:

- the Cloud project must be registered for Earth Engine;
- the Earth Engine API and appropriate access must be configured;
- Earth Engine has its own EECU/quota rules;
- any registration/API/role/billing change is outside this source-only evaluation and needs a separate owner gate.

That is unnecessary while the GCS statistics surface matches the current first-access data contract more directly.

## Frozen invariants

Any later GCS-source implementation must preserve:

- canonical first-access location `station_05480`;
- one explicit WeatherNext 3 init;
- bounded lead hours;
- 0.05° station temperature/dew point plus 0.1° surface variables;
- all six precomputed statistics;
- provider/model/init/retrieval/valid/lead/statistic/source-surface provenance;
- no private-home scope for the first canary;
- no fabricated WeatherNext values or publication timestamps;
- DWD as the official severe-weather warning authority;
- no production write until a separate exact data authorization.

The full-ensemble Requester Pays bucket is **not** part of this first-access candidate.

## Next source-only step

The preferred follow-up is a fixture-driven GCS statistics adapter contract that proves, without cloud access:

1. deterministic construction/validation of one run path;
2. selection of only the required variables;
3. point/nearest-grid selection for the canonical benchmark without emitting coordinates;
4. bounded continuous hourly `lead_time` selection;
5. mapping into the existing `ForecastRun` provenance model;
6. fail-closed schema/dimension checks;
7. no full-dataset `.load()` path and no full-ensemble bucket fallback.

Only after that source contract is reviewed and merged should a new exact private read-only GCS access gate be designed.

## Official references

- https://developers.google.com/weathernext/guides/access-forecast
- https://developers.google.com/weathernext/guides/gcs
- https://developers.google.com/weathernext/guides/earth-engine
- https://developers.google.com/earth-engine/guides/access
- https://developers.google.com/earth-engine/guides/noncommercial_tiers
- https://docs.cloud.google.com/storage/docs/requester-pays


## Fixture-driven GCS adapter contract

The preferred-candidate follow-up is now represented by the source-only contract
`deploy/weathernext-gcs-statistics-first-access.json` and the transport-free
adapter helpers in `src/rozkalns_weather/weathernext_gcs.py`.

The contract follows the official GCS guide closely:

- statistics data stays on `weathernext3_statistics_spatial`; the full-ensemble
  Requester Pays bucket is not an allowed fallback;
- the operational run directory must be supplied explicitly and match the
  documented `YYYYMMDD_HHhr_XX_preds` shape plus the selected init date/hour;
- the source does **not** assign meaning to the undocumented `XX` token and does
  not guess `01_preds`;
- `lead_time` is treated as one continuous hourly axis; `sample` and
  `lead_subtime` are rejected for this statistics-product contract;
- required 0.05° station and 0.1° surface statistic fields are schema-checked
  before point records can map into `ForecastRun`;
- first-access selection stays bounded to at most 24 lead hours and must slice
  variables/time/point before any later materialization;
- no live opener, bucket listing, Google request, runtime transport switch or
  production write is authorized by this source contract.

Fixture tests contain schema identities and synthetic numeric values only. They do
not contain WeatherNext provider values or private coordinates.

After this contract is reviewed and merged, the next step is not a BigQuery retry.
It is a separately designed private read-only GCS gate that supplies one explicit
run-directory token, performs bounded lazy selection and returns sanitized
presence/provenance evidence before any production snapshot write is considered.
