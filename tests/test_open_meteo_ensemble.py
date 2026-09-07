from datetime import datetime, timezone

import pytest

from rozkalns_weather.providers.open_meteo_ensemble import (
    ECMWF_AIFS_ENS,
    ECMWF_IFS_ENS,
    ICON_D2_EPS,
    WEATHERNEXT2_LEGACY,
    OpenMeteoEnsembleAdapter,
    parse_ensemble,
)


PAYLOAD = {
    "generationtime_ms": 1.5,
    "hourly_units": {
        "time": "iso8601",
        "temperature_2m": "°C",
        "temperature_2m_member01": "°C",
        "temperature_2m_member02": "°C",
        "precipitation": "mm",
        "precipitation_member01": "mm",
        "precipitation_member02": "mm",
    },
    "hourly": {
        "time": ["2026-09-07T12:00", "2026-09-07T13:00"],
        "temperature_2m": [20.0, 21.0],
        "temperature_2m_member01": [19.0, 20.0],
        "temperature_2m_member02": [22.0, 23.0],
        "precipitation": [0.0, 0.1],
        "precipitation_member01": [0.0, 0.0],
        "precipitation_member02": [0.2, 0.5],
    },
}


def test_official_ensemble_model_keys_and_roles_are_explicit() -> None:
    assert ICON_D2_EPS.model_key == "dwd_icon_d2_eps"
    assert ICON_D2_EPS.documented_member_count == 20
    assert ECMWF_IFS_ENS.model_key == "ecmwf_ifs025_ensemble"
    assert ECMWF_AIFS_ENS.model_key == "ecmwf_aifs025_ensemble"
    assert ECMWF_IFS_ENS.documented_member_count == 51
    assert ECMWF_AIFS_ENS.documented_member_count == 51
    assert WEATHERNEXT2_LEGACY.model_key == "google_weathernext2_ensemble"
    assert WEATHERNEXT2_LEGACY.role == "legacy_ai_context"
    assert WEATHERNEXT2_LEGACY.strict_run_leaderboard_eligible is False


def test_parser_preserves_control_and_member_identity() -> None:
    snapshot = parse_ensemble(
        PAYLOAD,
        model=ICON_D2_EPS,
        retrieved_at=datetime(2026, 9, 7, 14, tzinfo=timezone.utc),
        requested_variables=("temperature_2m", "precipitation"),
    )
    assert snapshot.member_ids == ("control", "member01", "member02")
    assert snapshot.member_count == 3
    temp_member = next(
        point
        for point in snapshot.points
        if point.variable == "temperature_2m" and point.member_id == "member01"
    )
    assert temp_member.value == 19.0
    assert snapshot.source_metadata["documented_member_count"] == 20
    assert snapshot.source_metadata["discovered_member_count"] == 3
    assert snapshot.source_metadata["individual_member_history_retention_days"] == 3
    assert snapshot.source_metadata["strict_run_leaderboard_eligible"] is False


def test_adapter_request_is_member_surface_and_retention_bounded() -> None:
    seen = []

    def fetcher(url, params):
        seen.append((url, dict(params)))
        return PAYLOAD

    adapter = OpenMeteoEnsembleAdapter(ECMWF_IFS_ENS, fetcher=fetcher)
    adapter.fetch(
        lat=51.5,
        lon=7.6,
        forecast_days=3,
        past_days=3,
        variables=("temperature_2m", "precipitation"),
        retrieved_at=datetime(2026, 9, 7, 14, tzinfo=timezone.utc),
    )
    params = seen[0][1]
    assert params["models"] == "ecmwf_ifs025_ensemble"
    assert params["past_days"] == 3
    assert params["hourly"] == "temperature_2m,precipitation"
    with pytest.raises(ValueError, match="0..3"):
        adapter.fetch(lat=51.5, lon=7.6, past_days=4)
