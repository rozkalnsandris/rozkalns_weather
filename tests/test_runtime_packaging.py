from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database


def test_public_only_runtime_needs_neither_home_nor_weathernext(tmp_path) -> None:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))

    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["runtime_mode"] == "public-only"
    assert payload["home"]["configured"] is False
    assert payload["home"]["required_for_public_runtime"] is False
    assert payload["weathernext"]["configured"] is False
    assert payload["weathernext"]["required_for_public_runtime"] is False
    assert payload["weathernext"]["values_fabricated"] is False
    assert payload["privacy"] == {
        "coordinates_exposed": False,
        "credentials_exposed": False,
        "database_path_exposed": False,
    }
    weathernext = next(item for item in payload["providers"] if item["id"] == "weathernext3")
    assert weathernext["state"] == "access_pending"
    assert weathernext["required_for_runtime"] is False


def test_require_existing_startup_does_not_create_database(tmp_path) -> None:
    database_path = tmp_path / "missing.db"
    settings = Settings.from_env(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "DATABASE_INIT_MODE": "require-existing",
            "WEATHER_RUNTIME_MODE": "public-only",
        }
    )
    client = TestClient(create_app(settings=settings, database=Database(settings.database_url)))

    assert not database_path.exists()
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["database"]["state"] == "missing"
    assert not database_path.exists()


def test_failed_public_provider_is_visible_but_does_not_break_runtime_readiness(tmp_path) -> None:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))
    database.set_provider_status(
        "icon_d2",
        state="error",
        now=datetime(2026, 9, 7, tzinfo=timezone.utc),
        detail="fixture_transport_error",
    )

    payload = client.get("/ready").json()
    assert payload["ready"] is True
    icon = next(item for item in payload["providers"] if item["id"] == "icon_d2")
    assert icon["state"] == "error"


def test_fixed_deploy_descriptor_is_public_safe_and_non_destructive() -> None:
    descriptor = json.loads(Path("deploy/runtime-descriptor.json").read_text())
    assert descriptor["schema_version"] == 1
    assert descriptor["repository"] == "rozkalnsandris/rozkalns_weather"
    assert descriptor["target_alias"] == "rozkalns-weather-public-rpi5"
    assert descriptor["operation_id_candidate"] == "rozkalns-weather.public-runtime-release.v1"
    assert descriptor["runtime_contract"]["runtime_mode"] == "public-only"
    assert descriptor["runtime_contract"]["database_init_mode"] == "require-existing"
    assert descriptor["runtime_contract"]["weathernext_required"] is False
    assert descriptor["runtime_contract"]["home_coordinates_required"] is False
    assert descriptor["persistent_data"]["implicit_backfill_on_start"] is False
    assert descriptor["persistent_data"]["corpus_deletion_allowed"] is False
    assert "sqlite.schema-init" in descriptor["future_rpi5_adapter"]["explicitly_separate_data_mutations"]
    serialized = json.dumps(descriptor)
    assert "HOME_LAT" in serialized  # only appears in the explicit exclusion list
    assert "HOME_LON" in serialized
    assert "51." not in serialized
    assert "7." not in serialized


def test_compose_candidate_has_fixed_jobs_and_no_private_env_file() -> None:
    compose = Path("deploy/docker-compose.public.yml").read_text()
    assert 'command: ["rozkalns-weather", "init-database"]' in compose
    assert 'command: ["rozkalns-weather", "ingest-public"]' in compose
    assert 'command: ["rozkalns-weather", "readiness"]' in compose
    assert 'command: ["rozkalns-weather", "corpus-check"]' in compose
    assert "DATABASE_INIT_MODE: require-existing" in compose
    assert "WEATHER_RUNTIME_MODE: public-only" in compose
    assert "HOME_LAT" not in compose
    assert "HOME_LON" not in compose
    assert "env_file:" not in compose
    assert "depends_on:" not in compose
    assert "ingest-weathernext" not in compose
    assert "/ready" in compose


def test_public_schedule_keeps_weathernext_dormant_and_bootstrap_explicit() -> None:
    schedule = json.loads(Path("deploy/public-ingest-schedule.json").read_text())
    assert schedule["schema_version"] == 2
    assert schedule["public_ingest"]["cadence"] == "PT30M"
    assert schedule["systemd_timer"]["timer_unit"] == "rozkalns-weather-public-ingest.timer"
    assert schedule["systemd_timer"]["service_unit"] == "rozkalns-weather-public-ingest.service"
    assert schedule["systemd_timer"]["on_calendar"] == "*:0/30"
    assert schedule["systemd_timer"]["persistent"] is True
    assert schedule["systemd_timer"]["randomized_delay_seconds"] == 60
    assert schedule["systemd_timer"]["enable_order"] == "last_after_corpus_integrity"
    assert schedule["weathernext"]["enabled"] is False
    assert schedule["bootstrap"]["implicit_on_application_start"] is False
    assert schedule["bootstrap"]["required_order"][0] == "volume_ensure"
    assert schedule["bootstrap"]["required_order"][-1] == "enable_recurring_public_ingest"
