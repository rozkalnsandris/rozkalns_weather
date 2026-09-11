from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.models import Observation
from rozkalns_weather.truth_quality import assess_dwd_truth


def _metadata(
    *,
    station_name: str = "Dortmund",
    dwd_station_id: str = "01234",
) -> dict[str, object]:
    return {
        "source_authority": "DWD",
        "wmo_station_id": "10416",
        "reference_location_id": "station_10416",
        "station_identity_pinned": True,
        "station_name": station_name,
        "dwd_station_id": dwd_station_id,
    }


def _obs(
    hour: int,
    *,
    station_id: str = "10416",
    variable: str = "temperature_2m",
    value: float = 20.0,
    unit: str = "degC",
    quality_status: str | None = "observed",
    metadata: dict[str, object] | None = None,
) -> Observation:
    return Observation(
        source_provider="DWD",
        station_id=station_id,
        location_id="station_10416",
        observed_at_utc=datetime(2026, 9, 11, hour, tzinfo=timezone.utc),
        variable=variable,
        value=value,
        unit=unit,
        quality_status=quality_status,
        source_metadata=metadata or _metadata(),
    )


def test_valid_truth_is_verification_ready() -> None:
    result = assess_dwd_truth([_obs(8), _obs(9), _obs(10)])
    assert result["state"] == "valid"
    assert result["verification_ready"] is True
    assert result["reason_codes"] == []
    assert result["station_id"] == "10416"
    assert result["max_temperature_gap_hours"] == 1.0


def test_station_mismatch_and_conflicting_duplicate_block() -> None:
    first = _obs(8)
    conflicting = {
        "source_provider": "DWD",
        "station_id": "99999",
        "location_id": "station_10416",
        "observed_at_utc": "2026-09-11T08:00:00Z",
        "variable": "temperature_2m",
        "value": 25.0,
        "unit": "degC",
        "quality_status": "observed",
        "source_metadata": {
            "source_authority": "DWD",
            "wmo_station_id": "99999",
            "reference_location_id": "station_10416",
            "station_identity_pinned": True,
        },
    }
    result = assess_dwd_truth([first, conflicting, _obs(9)])
    assert result["state"] == "blocking"
    assert result["verification_ready"] is False
    assert "STATION_ID_MISMATCH" in result["reason_codes"]
    assert "SOURCE_WMO_MISMATCH" in result["reason_codes"]
    assert "CONFLICTING_DUPLICATE" in result["reason_codes"]


def test_identical_duplicate_is_suspect() -> None:
    duplicate = _obs(8)
    result = assess_dwd_truth([duplicate, duplicate, _obs(9)])
    assert result["state"] == "suspect"
    assert result["verification_ready"] is False
    assert "DUPLICATE_OBSERVATION" in result["reason_codes"]


def test_gap_makes_truth_incomplete_without_imputation() -> None:
    result = assess_dwd_truth([_obs(8), _obs(12)])
    assert result["state"] == "incomplete"
    assert result["verification_ready"] is False
    assert result["max_temperature_gap_hours"] == 4.0
    assert "TEMPERATURE_COVERAGE_GAP" in result["reason_codes"]


def test_malformed_or_naive_timestamp_and_unit_drift_block() -> None:
    records = [
        {
            "source_provider": "DWD",
            "station_id": "10416",
            "location_id": "station_10416",
            "observed_at_utc": "2026-09-11 08:00:00",
            "variable": "temperature_2m",
            "value": 20.0,
            "unit": "K",
            "quality_status": "observed",
            "source_metadata": {},
        },
        _obs(9),
    ]
    result = assess_dwd_truth(records)
    assert result["state"] == "blocking"
    assert "TIMESTAMP_NAIVE" in result["reason_codes"]
    assert "UNIT_MISMATCH" in result["reason_codes"]


def test_impossible_value_blocks() -> None:
    result = assess_dwd_truth([_obs(8, value=20.0), _obs(9, value=95.0)])
    assert result["state"] == "blocking"
    assert "VALUE_OUT_OF_BOUNDS" in result["reason_codes"]


def test_quality_flag_and_station_metadata_drift_are_suspect() -> None:
    first = _obs(8)
    second = _obs(
        9,
        quality_status="provisional",
        metadata=_metadata(station_name="Dortmund changed", dwd_station_id="56789"),
    )
    result = assess_dwd_truth([first, second])
    assert result["state"] == "suspect"
    assert "QUALITY_STATUS_UNKNOWN" in result["reason_codes"]
    assert "QUALITY_STATUS_DRIFT" in result["reason_codes"]
    assert "STATION_METADATA_DRIFT" in result["reason_codes"]


def test_out_of_order_truth_is_suspect() -> None:
    result = assess_dwd_truth([_obs(9), _obs(8)])
    assert result["state"] == "suspect"
    assert "TIMESTAMP_OUT_OF_ORDER" in result["reason_codes"]


def test_verification_api_exposes_truth_readiness(tmp_path) -> None:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    observations = [
        Observation(
            source_provider="DWD",
            station_id="10416",
            location_id="station_10416",
            observed_at_utc=now - timedelta(hours=1),
            variable="temperature_2m",
            value=19.0,
            unit="degC",
            quality_status="observed",
            source_metadata=_metadata(),
        ),
        Observation(
            source_provider="DWD",
            station_id="10416",
            location_id="station_10416",
            observed_at_utc=now,
            variable="temperature_2m",
            value=20.0,
            unit="degC",
            quality_status="observed",
            source_metadata=_metadata(),
        ),
    ]
    database.insert_observations(observations)

    quality = client.get("/api/verification/truth-quality?days=2")
    assert quality.status_code == 200
    assert quality.json()["state"] == "valid"
    assert quality.json()["verification_ready"] is True

    summary = client.get("/api/verification/summary?days=2").json()
    assert summary["verification_ready"] is True
    assert summary["truth_quality"]["contract"] == "dwd-truth-quality-v1"
