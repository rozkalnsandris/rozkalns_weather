# Source references

Reference snapshot for project bootstrap. Re-check upstream docs before implementation because WeatherNext 3 is new and actively changing.

## Google WeatherNext 3

### Core model

- WeatherNext 3 model guide: https://developers.google.com/weathernext/guides/models
- Release notes: https://developers.google.com/weathernext/release-notes
- Benefits / limitations: https://developers.google.com/weathernext/guides/benefits-limitations

### Access / data surfaces

- Access quick start: https://developers.google.com/weathernext/guides/access-forecast
- BigQuery: https://developers.google.com/weathernext/guides/bigquery
- Dissemination schedule: https://developers.google.com/weathernext/guides/dissemination
- Terms / disclaimers: https://developers.google.com/weathernext/guides/disclaimers
- Open source model status: https://developers.google.com/weathernext/guides/osmodel

### Bootstrap facts verified 2026-09-06

- WeatherNext 3 operational forecasts are exposed through BigQuery, Earth Engine and GCS/Zarr.
- Real-time operational access requires allowlisting; Google states typical review is 5–7 business days.
- Model is initialized every hour.
- `00/06/12/18 UTC` runs provide up to 15 days / 360 h; interim hourly inits provide up to 48 h.
- 64-member ensemble.
- Precomputed statistics include mean and percentiles.
- Consumer dissemination has substantial latency; BigQuery/Earth Engine synoptic availability targets are several hours after init.
- WeatherNext is experimental/informational and not an official severe-weather warning source.

## DWD

- DWD Open Data root: https://opendata.dwd.de/
- MOSMIX-L station 10416 directory: https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/10416/kml/
- DWD Open Data help / documentation: https://www.dwd.de/DE/leistungen/opendata/opendata.html

### Station / local forecast

Bootstrap decision uses DWD MOSMIX station `10416 DORTMUND`. Current directory exposes `MOSMIX_L_LATEST_10416.kmz`.

## Bright Sky

- Project: https://brightsky.dev/
- API docs: https://brightsky.dev/docs/

Bright Sky is an open-source JSON API layer over DWD Open Data. It supports point weather data and advertises radar, precipitation probabilities, solar radiation and alerts.

## Open-Meteo

- DWD ICON API: https://open-meteo.com/en/docs/dwd-api
- ECMWF API: https://open-meteo.com/en/docs/ecmwf-api
- Ensemble API: https://open-meteo.com/en/docs/ensemble-api
- Model updates: https://open-meteo.com/en/docs/model-updates
- General docs: https://open-meteo.com/en/docs

### DWD ICON-D2 facts used for design

Open-Meteo currently documents ICON-D2 as approximately:

- 0.02° / ~2 km;
- up to 15-minute temporal data for supported variables;
- ~2 day forecast horizon;
- updates every 3 h.

Before production implementation, verify against direct DWD model documentation and current API schema.

### ECMWF facts used for design

Open-Meteo currently documents:

- IFS HRES native ~9 km;
- forecast up to 15 days;
- update every 6 h;
- AIFS products available for AI-model comparison.

Before implementing AIFS comparisons, pin exact product semantics and resolution.

## Source-quality policy

1. Prefer upstream provider documentation for meteorological/model semantics.
2. Adapter docs (Open-Meteo/Bright Sky) describe transport/API behavior, not model scientific authority.
3. For official severe-weather warnings in Germany, use DWD official warning data.
4. Re-check WeatherNext docs before every schema/access change because the service is new and active.
5. Do not promote current model latency/version/access facts to permanent assumptions without a fresh source check.
