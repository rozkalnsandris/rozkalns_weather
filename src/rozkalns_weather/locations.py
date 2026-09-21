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


# Legacy public WMO/airport reference retained for UI/history compatibility only.
# It is no longer the production verification benchmark because an exact
# historical DWD truth transport for WMO 10416 could not be verified (#151).
DWD_10416 = ReferenceLocation(
    id="station_10416",
    label="DWD Dortmund/Wickede 10416",
    lat=51.5167,
    lon=7.6167,
    elevation_m=127.0,
    timezone="Europe/Berlin",
)


# Owner-approved production verification benchmark selected under #155.
# These are public DWD CDC station metadata, not a private/home point.
# DWD CDC station 01303 is Essen-Bredeney. The current geography record is
# pinned so forecast extraction and observation truth use the same location.
DWD_CDC_01303 = ReferenceLocation(
    id="station_dwd_cdc_01303",
    label="DWD CDC Essen-Bredeney 01303",
    lat=51.4041,
    lon=6.9677,
    elevation_m=150.0,
    timezone="Europe/Berlin",
)

BENCHMARK_LOCATION = DWD_CDC_01303
BENCHMARK_TRUTH_STATION_ID = "01303"
