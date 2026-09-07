from __future__ import annotations

from dataclasses import dataclass
import os

from .semantics import DEFAULT_PRECIP_EVENT_THRESHOLD_MM

RUNTIME_MODES = frozenset({"public-only", "private-research"})
DATABASE_INIT_MODES = frozenset({"auto", "require-existing"})


def _optional_float(name: str, value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _float(name: str, value: str | None, default: float) -> float:
    parsed = _optional_float(name, value)
    return default if parsed is None else parsed


def _int(name: str, value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    home_lat: float | None
    home_lon: float | None
    home_timezone: str
    home_label: str
    google_cloud_project: str | None
    weathernext_bigquery_dataset: str | None
    database_url: str
    runtime_mode: str = "public-only"
    database_init_mode: str = "auto"
    ingest_timeout_seconds: float = 20.0
    ingest_retries: int = 2
    precipitation_event_threshold_mm: float = DEFAULT_PRECIP_EVENT_THRESHOLD_MM

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
        timeout = _float("INGEST_TIMEOUT_SECONDS", source.get("INGEST_TIMEOUT_SECONDS"), 20.0)
        retries = _int("INGEST_RETRIES", source.get("INGEST_RETRIES"), 2)
        threshold = _float(
            "PRECIP_EVENT_THRESHOLD_MM",
            source.get("PRECIP_EVENT_THRESHOLD_MM"),
            DEFAULT_PRECIP_EVENT_THRESHOLD_MM,
        )
        if not 1.0 <= timeout <= 120.0:
            raise ValueError("INGEST_TIMEOUT_SECONDS must be between 1 and 120")
        if not 1 <= retries <= 5:
            raise ValueError("INGEST_RETRIES must be between 1 and 5")
        if not 0.0 < threshold <= 10.0:
            raise ValueError("PRECIP_EVENT_THRESHOLD_MM must be > 0 and <= 10")
        runtime_mode = source.get("WEATHER_RUNTIME_MODE", "public-only").strip() or "public-only"
        if runtime_mode not in RUNTIME_MODES:
            raise ValueError(f"WEATHER_RUNTIME_MODE must be one of {sorted(RUNTIME_MODES)}")
        database_init_mode = source.get("DATABASE_INIT_MODE", "auto").strip() or "auto"
        if database_init_mode not in DATABASE_INIT_MODES:
            raise ValueError(f"DATABASE_INIT_MODE must be one of {sorted(DATABASE_INIT_MODES)}")
        return cls(
            home_lat=lat,
            home_lon=lon,
            home_timezone=source.get("HOME_TIMEZONE", "Europe/Berlin"),
            home_label=source.get("HOME_LABEL", "Dortmund-Wickede"),
            google_cloud_project=source.get("GOOGLE_CLOUD_PROJECT") or None,
            weathernext_bigquery_dataset=source.get("WEATHERNEXT_BIGQUERY_DATASET") or None,
            database_url=source.get("DATABASE_URL", "sqlite:///data/weather.db"),
            runtime_mode=runtime_mode,
            database_init_mode=database_init_mode,
            ingest_timeout_seconds=timeout,
            ingest_retries=retries,
            precipitation_event_threshold_mm=threshold,
        )

    @property
    def home_configured(self) -> bool:
        return self.home_lat is not None and self.home_lon is not None

    @property
    def weathernext_cloud_configured(self) -> bool:
        return bool(self.google_cloud_project and self.weathernext_bigquery_dataset)

    @property
    def weathernext_configured(self) -> bool:
        return bool(self.home_configured and self.weathernext_cloud_configured)
