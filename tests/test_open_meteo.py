from datetime import datetime, timezone

from rozkalns_weather.providers.open_meteo import ECMWF_AIFS, ECMWF_IFS, ICON_D2, OpenMeteoAdapter, parse_open_meteo

PAYLOAD = {
    "generationtime_ms": 1.2,
    "hourly_units": {"time": "iso8601", "temperature_2m": "°C", "precipitation": "mm", "wind_speed_10m": "m/s"},
    "hourly": {
        "time": ["2026-09-07T08:00", "2026-09-07T09:00"],
        "temperature_2m": [20.0, 21.0],
        "precipitation": [0.0, 0.5],
        "wind_speed_10m": [2.0, 3.0],
    },
}


def test_model_keys_are_explicit() -> None:
    assert ICON_D2.model_key == "icon_d2"
    assert ECMWF_IFS.model_key == "ecmwf_ifs"
    assert ECMWF_AIFS.model_key == "ecmwf_aifs025_single"


def test_open_meteo_preserves_upstream_identity() -> None:
    run = parse_open_meteo(PAYLOAD, model=ICON_D2, retrieved_at=datetime(2026, 9, 7, 7, 30, tzinfo=timezone.utc))
    assert run.provider == "icon_d2"
    assert run.model_provider == "DWD"
    assert run.transport_provider == "Open-Meteo"
    assert run.source_metadata["model_key"] == "icon_d2"
    rain = next(v for v in run.values if v.variable == "precipitation_1h" and v.value == 0.5)
    assert rain.accumulation_window_minutes == 60


def test_adapter_sends_private_point_only_at_runtime() -> None:
    seen = {}
    def fetcher(url, params):
        seen.update(params)
        return PAYLOAD
    OpenMeteoAdapter(ICON_D2, fetcher=fetcher).fetch(lat=51.5, lon=7.6, retrieved_at=datetime(2026, 9, 7, 7, 30, tzinfo=timezone.utc))
    assert seen["models"] == "icon_d2"
    assert seen["latitude"] == 51.5
    assert seen["longitude"] == 7.6
    assert seen["timezone"] == "UTC"
