# WeatherNext 3

WeatherNext 3 is an optional research provider, not a dependency of the operational home weather app.

## Preferred simple path

Use the precomputed Google Cloud Storage statistics/Zarr surface.

The source adapter is bounded around:
- one explicit init;
- station_05480 for the first canary;
- a small lead-hour slice;
- precomputed mean/p10/p25/p50/p75/p90 statistics;
- point selection before materialization;
- no production write during the first read.

## Runtime rule

Private WeatherNext access requires a separate exact authorization. Credentials stay outside GitHub.

After a successful read-only canary, a separate data-write decision is required before inserting real WeatherNext snapshots into production SQLite.

## BigQuery

The earlier BigQuery cost-control chain is historical implementation evidence in Git history. It is not the active first-access path for the simple app.

WeatherNext output is experimental forecast data. DWD remains the official warning authority.
