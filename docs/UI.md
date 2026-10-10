# UI

The private app has five views.

## Overview
- current DWD observation;
- next hours;
- next days;
- temperature/precipitation/wind;
- small model snapshot;
- visible DWD warning state.

## Models
Compare WeatherNext 3, ICON-D2, ECMWF IFS and ECMWF AIFS without blending them into a fake Combined value.

## Radar
Show DWD warning information and precipitation radar/nowcast clearly. Model output must never look like an official warning.

The visual map uses one **official basemap.de Web Raster Grau** WMS background (GeoBasis-DE/BKG) and one **transparent DWD Niederschlagsradar** WMS image, both served through fixed same-origin, bounded PNG endpoints. The map must show readable roads and location names rather than the old pixelated `bluemarble` background. No OpenStreetMap tile traffic or new deployment service is needed. Keep on-map GeoBasis-DE/BKG and DWD attribution. A missing basemap/radar image must show an error instead of implying that precipitation is absent.

Bright Sky can return observed and nowcast timestamps, but the DWD `Niederschlagsradar` GetMap only renders the latest **observed** frames. The simple single-frame map must request a real observed timestamp, not a future nowcast time. A user-facing map is accepted only after a physical Galaxy A55 visual check, not merely HTTP 200 or PNG validation.

Documentation: https://basemap.de/produkte-und-dienste/web-raster/ ; https://gdz.bkg.bund.de/index.php/default/wms-basemapde-webraster-wms-basemapde-webraster.html ; https://www.dwd.de/DE/leistungen/geodienste/help/nutzung_geodienste.html ; https://leafletjs.com/examples/overlays/ .

## Accuracy
Show practical measured verification:
- MAE;
- RMSE;
- bias;
- lead bucket;
- sample count.

## Status
Show whether each provider is fresh, stale, unavailable or not yet ingested.

## Mobile
Galaxy A55-sized mobile layout is the priority. Desktop remains responsive.

## Missing data
Use explicit missing/pending/stale states. Never fabricate a provider value.
