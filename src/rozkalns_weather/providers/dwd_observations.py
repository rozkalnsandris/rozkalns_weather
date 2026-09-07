from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..models import Observation, parse_time
from .base import JsonFetcher, fetch_json

BRIGHTSKY_WEATHER_URL = "https://api.brightsky.dev/weather"
WMO_STATION_ID = "10416"

VARIABLES = {
    "temperature": ("temperature_2m", "degC"),
    "dew_point": ("dew_point_2m", "degC"),
    "pressure_msl": ("pressure_msl", "hPa"),
    "relative_humidity": ("relative_humidity_2m", "%"),
    "wind_speed": ("wind_speed_10m", "m/s"),
    "wind_gust_speed": ("wind_gust_10m", "m/s"),
    "precipitation": ("precipitation_1h", "mm"),
    "cloud_cover": ("cloud_cover", "%"),
}


def parse_brightsky_observations(payload: dict[str, Any]) -> list[Observation]:
    sources = {source.get("id"): source for source in payload.get("sources", []) if isinstance(source, dict)}
    output: list[Observation] = []
    for row in payload.get("weather", []):
        if not isinstance(row, dict) or not row.get("timestamp"):
            continue
        source = sources.get(row.get("source_id"), {})
        wmo = str(source.get("wmo_station_id") or WMO_STATION_ID)
        for source_key, (variable, unit) in VARIABLES.items():
            raw = row.get(source_key)
            if raw is None:
                continue
            output.append(
                Observation(
                    source_provider="DWD",
                    station_id=wmo,
                    observed_at_utc=parse_time(str(row["timestamp"])),
                    variable=variable,
                    value=float(raw),
                    unit=unit,
                    quality_status="observed",
                    source_metadata={
                        "transport": "Bright Sky",
                        "source_id": row.get("source_id"),
                        "station_name": source.get("station_name"),
                        "dwd_station_id": source.get("dwd_station_id"),
                        "wmo_station_id": source.get("wmo_station_id"),
                    },
                )
            )
    return output


class DwdObservationAdapter:
    provider_id = "dwd_observations"

    def __init__(self, *, fetcher: JsonFetcher = fetch_json) -> None:
        self.fetcher = fetcher

    def fetch(self, *, hours: int = 48, now: datetime | None = None) -> list[Observation]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        start = now - timedelta(hours=hours)
        params = {
            "date": start.date().isoformat(),
            "last_date": now.date().isoformat(),
            "wmo_station_id": WMO_STATION_ID,
            "tz": "UTC",
            "units": "si",
        }
        return parse_brightsky_observations(self.fetcher(BRIGHTSKY_WEATHER_URL, params))
