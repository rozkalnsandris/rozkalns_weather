# Data sources

## DWD

### Current observation and verification truth
DWD CDC station 05480 is the single measured reference used by this project.

### Official warnings
DWD official warnings/CAP are the authoritative severe-weather warning source.

### Radar
DWD/Bright Sky radar data is used for observed precipitation and nowcast context.

## Forecast models

### ICON-D2
Short-range German high-resolution model, transported through Open-Meteo.

### ECMWF IFS
Traditional global medium-range baseline, transported through Open-Meteo.

### ECMWF AIFS
ECMWF AI forecast baseline, transported through Open-Meteo.

### WeatherNext 3
Optional research provider. Preferred simple first-access surface is the precomputed GCS statistics/Zarr dataset.

## Provenance

Stored forecasts retain provider/model, model version when available, init time, retrieval time, valid time, lead time, statistic and source/transport identity.

Transport identity must not replace upstream model identity.
