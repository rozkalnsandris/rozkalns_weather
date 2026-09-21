from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReferenceLocation:
    id: str
    label: str
    lat: float
    lon: float
    elevation_m: float | None
    timezone: str


# Legacy WMO/airport reference retained for historical compatibility only.
DWD_10416 = ReferenceLocation(
    id="station_10416",
    label="DWD Dortmund/Wickede 10416",
    lat=51.5167,
    lon=7.6167,
    elevation_m=127.0,
    timezone="Europe/Berlin",
)

# Canonical measured public benchmark from issue #153. Coordinates/elevation are
# public DWD station metadata, not private home coordinates.
DWD_CDC_05480 = ReferenceLocation(
    id="station_dwd_cdc_05480",
    label="DWD CDC Werl 05480",
    lat=51.5763,
    lon=7.8879,
    elevation_m=85.0,
    timezone="Europe/Berlin",
)

PUBLIC_BENCHMARK_LOCATION = DWD_CDC_05480
PUBLIC_BENCHMARK_STATION_ID = "05480"
