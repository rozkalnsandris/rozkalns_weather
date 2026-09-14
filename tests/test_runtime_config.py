import json
from pathlib import Path

from rozkalns_weather.runtime_config import RUNTIME_CONFIG_CONTRACT, validate_runtime_config


PUBLIC_DEPLOYMENT = {
    "WEATHER_RUNTIME_MODE": "public-only",
    "WEATHER_CONFIG_PROFILE": "deployment",
    "WEATHER_CONFIG_SCHEMA_VERSION": "1",
    "DATABASE_INIT_MODE": "require-existing",
    "DATABASE_URL": "sqlite:///data/weather.db",
}


def test_contract_snapshot_matches_executable_registry() -> None:
    snapshot = json.loads(Path("contracts/runtime-config-v1.json").read_text())
    assert snapshot == RUNTIME_CONFIG_CONTRACT


def test_public_deployment_passes_without_private_inputs() -> None:
    payload = validate_runtime_config(PUBLIC_DEPLOYMENT)
    assert payload["state"] == "PASS"
    assert payload["runtime_mode"] == "public-only"
    assert payload["presence"]["home_coordinates"] is False
    assert payload["presence"]["google_auth"] is False
    assert payload["authority"]["live_authority_granted"] is False


def test_deployment_implicit_database_init_is_blocked() -> None:
    env = {**PUBLIC_DEPLOYMENT, "DATABASE_INIT_MODE": "auto"}
    payload = validate_runtime_config(env)
    assert payload["state"] == "BLOCKED"
    assert "IMPLICIT_DATABASE_INITIALIZATION_UNSAFE" in payload["reason_codes"]


def test_unknown_schema_and_runtime_mode_fail_closed() -> None:
    payload = validate_runtime_config(
        {
            **PUBLIC_DEPLOYMENT,
            "WEATHER_CONFIG_SCHEMA_VERSION": "999",
            "WEATHER_RUNTIME_MODE": "mystery",
        }
    )
    assert payload["state"] == "BLOCKED"
    assert "CONFIG_SCHEMA_UNSUPPORTED" in payload["reason_codes"]
    assert "RUNTIME_MODE_INVALID" in payload["reason_codes"]


def test_incomplete_private_home_pair_is_blocked_without_echoing_value() -> None:
    secret_coordinate = "51.500001"
    payload = validate_runtime_config(
        {
            "WEATHER_RUNTIME_MODE": "private-research",
            "WEATHER_CONFIG_PROFILE": "deployment",
            "WEATHER_CONFIG_SCHEMA_VERSION": "1",
            "DATABASE_INIT_MODE": "require-existing",
            "DATABASE_URL": "sqlite:///private/weather.db",
            "HOME_LAT": secret_coordinate,
        }
    )
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["state"] == "BLOCKED"
    assert "HOME_COORDINATE_PAIR_INCOMPLETE" in payload["reason_codes"]
    assert secret_coordinate not in serialized
    assert "sqlite:///private/weather.db" not in serialized


def test_private_research_requires_home_cloud_and_auth_presence() -> None:
    payload = validate_runtime_config(
        {
            "WEATHER_RUNTIME_MODE": "private-research",
            "WEATHER_CONFIG_PROFILE": "deployment",
            "WEATHER_CONFIG_SCHEMA_VERSION": "1",
            "DATABASE_INIT_MODE": "require-existing",
            "DATABASE_URL": "sqlite:///data/weather.db",
        }
    )
    assert payload["state"] == "BLOCKED"
    assert set(payload["reason_codes"]) == {
        "GOOGLE_AUTH_PRESENCE_REQUIRED",
        "PRIVATE_HOME_REQUIRED",
        "PROJECT_DATASET_CONFIG_REQUIRED",
    }


def test_private_research_passes_with_presence_only_evidence() -> None:
    env = {
        "WEATHER_RUNTIME_MODE": "private-research",
        "WEATHER_CONFIG_PROFILE": "deployment",
        "WEATHER_CONFIG_SCHEMA_VERSION": "1",
        "DATABASE_INIT_MODE": "require-existing",
        "DATABASE_URL": "sqlite:///private/weather.db",
        "HOME_LAT": "51.500001",
        "HOME_LON": "7.600001",
        "GOOGLE_CLOUD_PROJECT": "private-project-name",
        "WEATHERNEXT_BIGQUERY_DATASET": "private-dataset-name",
        "GOOGLE_AUTH_PRESENT": "true",
    }
    payload = validate_runtime_config(env)
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["state"] == "PASS"
    assert payload["presence"] == {
        "database_url": True,
        "home_coordinates": True,
        "google_project_and_dataset": True,
        "google_auth": True,
    }
    for private_value in (
        "51.500001",
        "7.600001",
        "private-project-name",
        "private-dataset-name",
        "sqlite:///private/weather.db",
    ):
        assert private_value not in serialized


def test_public_runtime_rejects_private_inputs() -> None:
    payload = validate_runtime_config(
        {
            **PUBLIC_DEPLOYMENT,
            "HOME_LAT": "51.5",
            "HOME_LON": "7.6",
        }
    )
    assert payload["state"] == "BLOCKED"
    assert "PUBLIC_RUNTIME_PRIVATE_HOME_UNSUPPORTED" in payload["reason_codes"]


def test_development_auto_init_is_warn_not_deployment_pass() -> None:
    payload = validate_runtime_config({})
    assert payload["state"] == "WARN"
    assert payload["warning_codes"] == ["DEVELOPMENT_IMPLICIT_DATABASE_INITIALIZATION"]


def test_container_startup_runs_config_gate_before_uvicorn() -> None:
    dockerfile = Path("Dockerfile").read_text()
    command = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))
    assert "python -m rozkalns_weather.runtime_config" in command
    assert command.index("runtime_config") < command.index("uvicorn")
