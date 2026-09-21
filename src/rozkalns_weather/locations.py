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


# Legacy public WMO/MOSMIX reference. Existing rows and the current-reference
# display keep this identity; issue #155 does not rewrite historical corpus.
DWD_10416 = ReferenceLocation(
    id="station_10416",
    label="DWD Dortmund/Wickede 10416",
    lat=51.5167,
    lon=7.6167,
    elevation_m=127.0,
    timezone="Europe/Berlin",
)

# Canonical measured public benchmark selected by issue #155. Coordinates are
# public DWD CDC station metadata, never the private home point.
DWD_CDC_05480 = ReferenceLocation(
    id="station_05480",
    label="DWD CDC Werl 05480",
    lat=51.5763,
    lon=7.8879,
    elevation_m=85.0,
    timezone="Europe/Berlin",
)

BENCHMARK_LOCATION = DWD_CDC_05480
