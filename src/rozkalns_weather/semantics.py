from __future__ import annotations

VARIABLES = {
    "temperature_2m": {"unit": "degC", "kind": "instantaneous"},
    "dew_point_2m": {"unit": "degC", "kind": "instantaneous"},
    "relative_humidity_2m": {"unit": "%", "kind": "instantaneous"},
    "pressure_msl": {"unit": "hPa", "kind": "instantaneous"},
    "wind_speed_10m": {"unit": "m/s", "kind": "instantaneous"},
    "wind_gust_10m": {"unit": "m/s", "kind": "instantaneous"},
    "cloud_cover": {"unit": "%", "kind": "instantaneous"},
    "precipitation_1h": {"unit": "mm", "kind": "accumulation", "window_minutes": 60},
}

PROVIDER_NATIVE_MAPS = {
    "dwd_mosmix_l": {"TTT": "temperature_2m", "Td": "dew_point_2m", "FF": "wind_speed_10m", "FX1": "wind_gust_10m", "PPPP": "pressure_msl", "N": "cloud_cover", "RR1c": "precipitation_1h"},
    "open_meteo": {"temperature_2m": "temperature_2m", "dew_point_2m": "dew_point_2m", "wind_speed_10m": "wind_speed_10m", "wind_gusts_10m": "wind_gust_10m", "pressure_msl": "pressure_msl", "cloud_cover": "cloud_cover", "precipitation": "precipitation_1h"},
    "weathernext3": {"station_head_temperature_2m": "temperature_2m", "station_head_dewpoint_temperature_2m": "dew_point_2m", "wind_speed_10m": "wind_speed_10m", "mean_sea_level_pressure": "pressure_msl", "total_cloud_cover": "cloud_cover", "total_precipitation_1hr": "precipitation_1h"},
}
