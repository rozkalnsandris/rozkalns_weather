import json
from pathlib import Path

from rozkalns_weather.runtime_config import validate_runtime_config


def test_public_deployment_passes() -> None:
    payload = validate_runtime_config({
        "WEATHER_RUNTIME_MODE": "public-only",
        "WEATHER_CONFIG_PROFILE": "deployment",
        "DATABASE_INIT_MODE": "require-existing",
        "DATABASE_URL": "sqlite:///data/weather.db",
    })
    assert payload["state"] == "PASS"
    assert payload["home_configured"] is False


def test_private_home_deployment_passes_without_google_contracts() -> None:
    payload = validate_runtime_config({
        "WEATHER_RUNTIME_MODE": "private-home",
        "WEATHER_CONFIG_PROFILE": "deployment",
        "DATABASE_INIT_MODE": "require-existing",
        "DATABASE_URL": "sqlite:///data/weather.db",
        "HOME_LAT": "51.500001",
        "HOME_LON": "7.600001",
    })
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["state"] == "PASS"
    assert payload["home_configured"] is True
    assert "51.500001" not in serialized
    assert "7.600001" not in serialized


def test_deployment_auto_init_is_blocked() -> None:
    payload = validate_runtime_config({
        "WEATHER_RUNTIME_MODE": "public-only",
        "WEATHER_CONFIG_PROFILE": "deployment",
        "DATABASE_INIT_MODE": "auto",
    })
    assert payload["state"] == "BLOCKED"
    assert "IMPLICIT_DATABASE_INITIALIZATION_UNSAFE" in payload["reason_codes"]


def test_invalid_runtime_is_blocked_without_echoing_coordinate() -> None:
    secret = "51.500001"
    payload = validate_runtime_config({
        "WEATHER_RUNTIME_MODE": "private-home",
        "HOME_LAT": secret,
    })
    assert payload["state"] == "BLOCKED"
    assert secret not in json.dumps(payload, sort_keys=True)


def test_container_runs_config_check_before_uvicorn() -> None:
    command = next(line for line in Path("Dockerfile").read_text().splitlines() if line.startswith("CMD "))
    assert command.index("runtime_config") < command.index("uvicorn")
