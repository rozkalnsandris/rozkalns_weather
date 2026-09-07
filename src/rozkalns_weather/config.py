from __future__ import annotations

from dataclasses import dataclass
import os


def _optional_float(name: str, value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    home_lat: float | None
    home_lon: float | None
    home_timezone: str
    home_label: str
    google_cloud_project: str | None
    weathernext_bigquery_dataset: str | None
    database_url: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        lat = _optional_float("HOME_LAT", source.get("HOME_LAT"))
        lon = _optional_float("HOME_LON", source.get("HOME_LON"))
        if lat is not None and not -90 <= lat <= 90:
            raise ValueError("HOME_LAT must be between -90 and 90")
        if lon is not None and not -180 <= lon <= 180:
            raise ValueError("HOME_LON must be between -180 and 180")
        if (lat is None) != (lon is None):
            raise ValueError("HOME_LAT and HOME_LON must be configured together")
        return cls(
            home_lat=lat,
            home_lon=lon,
            home_timezone=source.get("HOME_TIMEZONE", "Europe/Berlin"),
            home_label=source.get("HOME_LABEL", "Dortmund-Wickede"),
            google_cloud_project=source.get("GOOGLE_CLOUD_PROJECT") or None,
            weathernext_bigquery_dataset=source.get("WEATHERNEXT_BIGQUERY_DATASET") or None,
            database_url=source.get("DATABASE_URL", "sqlite:///data/weather.db"),
        )

    @property
    def home_configured(self) -> bool:
        return self.home_lat is not None and self.home_lon is not None

    @property
    def weathernext_configured(self) -> bool:
        return bool(self.home_configured and self.google_cloud_project and self.weathernext_bigquery_dataset)
