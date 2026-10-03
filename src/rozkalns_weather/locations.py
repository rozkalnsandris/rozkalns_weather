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


DWD_CDC_05480 = ReferenceLocation(
    id="station_05480",
    label="DWD CDC Werl 05480",
    lat=51.5763,
    lon=7.8879,
    elevation_m=85.0,
    timezone="Europe/Berlin",
)

BENCHMARK_LOCATION = DWD_CDC_05480
