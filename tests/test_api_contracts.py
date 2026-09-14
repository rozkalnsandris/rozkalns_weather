from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient

from rozkalns_weather.api_contracts import (
    API_CONTRACTS,
    CONTRACT_INVARIANTS,
    classify_contract_change,
    contract_snapshot,
    privacy_violations,
    validate_payload,
)
from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation


def _client_with_contract_data(tmp_path) -> TestClient:
    settings = Settings.from_env(
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}",
            "HOME_LAT": "51.5",
            "HOME_LON": "7.6",
        }
    )
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))

    valid = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    database.insert_observations(
        [
            Observation(
                source_provider="DWD",
                station_id="10416",
                location_id=DWD_10416.id,
                observed_at_utc=valid,
                variable="temperature_2m",
                value=10.0,
                unit="degC",
            )
        ]
    )
    run = ForecastRun(
        provider="icon_d2",
        model_provider="DWD",
        model_name="ICON-D2",
        model_version="fixture-v1",
        init_time_utc=valid - timedelta(hours=6),
        retrieved_at_utc=valid - timedelta(hours=5),
        source_surface="fixture",
        values=(
            ForecastValue(
                valid_time_utc=valid,
                lead_hours=6,
                variable="temperature_2m",
                statistic="deterministic",
                value=11.0,
                unit="degC",
            ),
        ),
    )
    database.insert_forecast_run(run, location_id="home")
    database.insert_forecast_run(run, location_id=DWD_10416.id)
    return client


def test_machine_contract_snapshot_matches_registry_and_is_privacy_safe() -> None:
    path = Path(__file__).parents[1] / "contracts" / "api-contract-v1.json"
    frozen = json.loads(path.read_text())
    assert frozen == contract_snapshot()
    assert privacy_violations(frozen) == []
    assert frozen["invariants"]["severe_weather_warning_authority"] == "DWD"
    assert frozen["invariants"]["weathernext_warning_authority"] is False
    assert frozen["invariants"]["pwa_data_states"] == ["fresh", "stale", "error", "offline"]
    assert len(set(frozen["invariants"]["pwa_data_states"])) == 4


def test_current_api_payloads_conform_to_frozen_contracts(tmp_path) -> None:
    client = _client_with_contract_data(tmp_path)
    routes = [
        ("/health", "/health"),
        ("/ready", "/ready"),
        ("/api/readiness", "/api/readiness"),
        ("/api/health/providers", "/api/health/providers"),
        ("/api/current", "/api/current"),
        ("/api/hourly?hours=48&variable=temperature_2m", "/api/hourly"),
        ("/api/daily?days=2", "/api/daily"),
        ("/api/verification/summary?days=30", "/api/verification/summary"),
    ]
    for request_path, contract_path in routes:
        response = client.get(request_path)
        assert response.status_code == 200, (request_path, response.text)
        assert validate_payload(contract_path, response.json()) == [], request_path


def test_contract_classifier_marks_additive_and_breaking_changes() -> None:
    baseline = deepcopy(API_CONTRACTS)

    additive = deepcopy(baseline)
    additive["/health"]["properties"]["build_id"] = {"type": "string", "nullable": True}
    additive_result = classify_contract_change(baseline, additive)
    assert additive_result["classification"] == "ADDITIVE_COMPATIBLE"
    assert {
        (item["code"], item["path"]) for item in additive_result["changes"]
    } == {("PROPERTY_ADDED", "/health.build_id")}

    breaking = deepcopy(baseline)
    breaking["/api/current"]["required"].remove("truth_source")
    breaking["/api/health/providers"]["properties"]["providers"]["items"]["properties"]["freshness_state"]["enum"].remove("stale")
    breaking_result = classify_contract_change(baseline, breaking)
    assert breaking_result["classification"] == "BREAKING"
    codes = {item["code"] for item in breaking_result["changes"]}
    assert "REQUIRED_GUARANTEE_REMOVED" in codes
    assert "ENUM_VALUE_REMOVED" in codes


def test_nullability_timestamp_and_enum_regressions_fail_closed() -> None:
    payload = {
        "status": "ok",
        "runtime_mode": "public",
        "database": "ready",
        "home_configured": True,
        "weathernext_required": False,
    }
    assert validate_payload("/health", payload) == []

    broken = dict(payload)
    broken["database"] = "mystery"
    errors = validate_payload("/health", broken)
    assert errors == [{"code": "ENUM_VALUE_UNKNOWN", "path": "/health.database"}]

    provider_contract = API_CONTRACTS["/api/health/providers"]["properties"]["providers"]["items"]
    sample = {
        "id": "icon_d2",
        "model_name": "ICON-D2",
        "state": "ok",
        "tracked": True,
        "ingest_state": "ok",
        "freshness_state": "fresh",
        "failure_domain": "none",
        "reason_code": "FRESH",
        "last_attempt_at_utc": "not-a-time",
        "last_success_at_utc": None,
        "last_init_time_utc": None,
        "last_retrieved_at_utc": None,
        "latest_valid_time_utc": None,
        "last_observed_at_utc": None,
    }
    errors = []
    from rozkalns_weather.api_contracts import _validate
    _validate(provider_contract, sample, "provider", errors)
    assert {"code": "FORMAT_INVALID", "path": "provider.last_attempt_at_utc"} in errors


def test_privacy_guard_rejects_sensitive_snapshot_material_without_echoing_value() -> None:
    sensitive = {
        "home_lat": "51.500000",
        "nested": {"token": "do-not-echo", "safe": "ok"},
        "db": "sqlite:////private/weather.db",
    }
    violations = privacy_violations(sensitive)
    assert {item["code"] for item in violations} == {"PROHIBITED_FIELD", "PROHIBITED_VALUE_PATTERN"}
    rendered = json.dumps(violations)
    assert "51.500000" not in rendered
    assert "do-not-echo" not in rendered
    assert "/private/weather.db" not in rendered


def test_contract_invariants_are_public_safe() -> None:
    assert CONTRACT_INVARIANTS["private_coordinates_allowed"] is False
