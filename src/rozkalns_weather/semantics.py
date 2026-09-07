from __future__ import annotations

from typing import Any

PRECIP_EVENT_VERSION = "precip-occurrence-v1"
DEFAULT_PRECIP_EVENT_THRESHOLD_MM = 0.1

VARIABLES: dict[str, dict[str, Any]] = {
    "temperature_2m": {"unit": "degC", "kind": "instantaneous"},
    "dew_point_2m": {"unit": "degC", "kind": "instantaneous"},
    "relative_humidity_2m": {"unit": "%", "kind": "instantaneous"},
    "pressure_msl": {"unit": "hPa", "kind": "instantaneous"},
    "wind_speed_10m": {"unit": "m/s", "kind": "instantaneous"},
    "wind_gust_10m": {"unit": "m/s", "kind": "instantaneous"},
    "cloud_cover": {"unit": "%", "kind": "instantaneous"},
    "precipitation_1h": {"unit": "mm", "kind": "accumulation", "window_minutes": 60},
    "precipitation_probability_1h": {
        "unit": "%",
        "kind": "probability",
        "window_minutes": 60,
        "event_version": PRECIP_EVENT_VERSION,
    },
}

PROVIDER_NATIVE_MAPS = {
    "dwd_mosmix_l": {"TTT": "temperature_2m", "Td": "dew_point_2m", "FF": "wind_speed_10m", "FX1": "wind_gust_10m", "PPPP": "pressure_msl", "N": "cloud_cover", "RR1c": "precipitation_1h"},
    "open_meteo": {"temperature_2m": "temperature_2m", "dew_point_2m": "dew_point_2m", "wind_speed_10m": "wind_speed_10m", "wind_gusts_10m": "wind_gust_10m", "pressure_msl": "pressure_msl", "cloud_cover": "cloud_cover", "precipitation": "precipitation_1h", "precipitation_probability": "precipitation_probability_1h"},
    "weathernext3": {"station_head_temperature_2m": "temperature_2m", "station_head_dewpoint_temperature_2m": "dew_point_2m", "wind_speed_10m": "wind_speed_10m", "mean_sea_level_pressure": "pressure_msl", "total_cloud_cover": "cloud_cover", "total_precipitation_1hr": "precipitation_1h"},
}


def validate_semantics(*, variable: str, value: float, unit: str, accumulation_window_minutes: int | None) -> list[str]:
    definition = VARIABLES.get(variable)
    if definition is None:
        return [f"unknown_variable:{variable}"]
    errors: list[str] = []
    if unit != definition["unit"]:
        errors.append(f"invalid_unit:{variable}:{unit}")
    expected_window = definition.get("window_minutes")
    if expected_window is not None and accumulation_window_minutes != expected_window:
        errors.append(f"invalid_window:{variable}:{accumulation_window_minutes}")
    if definition["kind"] == "probability" and not 0.0 <= value <= 100.0:
        errors.append(f"invalid_probability:{variable}")
    return errors
