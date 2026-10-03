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
