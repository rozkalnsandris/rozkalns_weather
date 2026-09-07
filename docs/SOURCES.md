# Current implementation sources

Checked against current web documentation during AUTO-FULL #5 (2026-09-07).

## Google WeatherNext 3

- https://developers.google.com/weathernext/guides/models
- https://developers.google.com/weathernext/guides/bigquery
- https://developers.google.com/weathernext/guides/access-forecast
- https://developers.google.com/weathernext/guides/dissemination
- https://developers.google.com/weathernext/release-notes

Implementation assumptions tied to current docs:

- BigQuery tables: `weathernext_3_0_0_0p1deg`, `weathernext_3_0_0_0p05deg`;
- repeated `forecast` record with `time`, `hours`, six precomputed statistics;
- 0.05° station-head temperature/dew point;
- 0.1° surface fields;
- 1-hour precipitation is metres, normalized to mm;
- total cloud cover is fraction 0–1, normalized to percent;
- synoptic BigQuery target availability about init + 8h10; interim about init + 7h25.

## DWD

- MOSMIX-L station 10416: https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/10416/kml/
- DWD Open Data: https://opendata.dwd.de/weather/
- DWD observations/CDC: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/

## Bright Sky

- https://brightsky.dev/
- https://github.com/jdemaeyer/brightsky

Bright Sky is used only as a convenient transport over DWD data for observations/warnings/radar; source authority remains DWD.

## Open-Meteo

- DWD ICON: https://open-meteo.com/en/docs/dwd-api
- ECMWF: https://open-meteo.com/en/docs/ecmwf-api
- Single Runs: https://open-meteo.com/en/docs/single-runs-api
- model enum source: https://github.com/open-meteo/open-meteo/blob/main/openapi/forecast.yml

Pinned model identity strings used by source:

- `icon_d2`
- `ecmwf_ifs`
- `ecmwf_aifs025_single`
