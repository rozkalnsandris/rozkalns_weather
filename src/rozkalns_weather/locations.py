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


# Public WMO/airport station used as the verification reference. This is not the
# private home point. Coordinates are public station metadata and intentionally
# kept separate from HOME_LAT/HOME_LON.
DWD_10416 = ReferenceLocation(
    id="station_10416",
    label="DWD Dortmund/Wickede 10416",
    lat=51.5167,
    lon=7.6167,
    elevation_m=127.0,
    timezone="Europe/Berlin",
)
