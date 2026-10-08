"""Consumer-side source contract for the Weather PUBLIC loopback publish (#915)."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/docker-compose.public.yml"
MANIFEST = ROOT / ".simple-deploy.json"
EXPECTED = "127.0.0.1:${WEATHER_PORT:-9180}:8000"


def _weather_block(source: str) -> str:
    assert source.startswith("services:\n  weather:\n")
    assert source.count("\n  weather:\n") == 1
    assert source.count("\n  public-ingest:\n") == 1
    return source.split("\n  weather:\n", 1)[1].split("\n  public-ingest:\n", 1)[0]


def _weather_ports(source: str) -> list[str]:
    weather = _weather_block(source)
    assert weather.count("\n    ports:\n") == 1
    assert weather.count("\n    volumes:\n") == 1
    return weather.split("\n    ports:\n", 1)[1].split(
        "\n    volumes:\n", 1
    )[0].strip("\n").splitlines()


def _is_exact_loopback(source: str) -> bool:
    return _weather_ports(source) == [f'      - "{EXPECTED}"']


def test_weather_consumer_publish_is_loopback_only() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    assert _is_exact_loopback(source)
    assert "0.0.0.0:" not in _weather_block(source)
    assert "[::]:" not in _weather_block(source)


@pytest.mark.parametrize(
    "unsafe",
    [
        "${WEATHER_PORT:-9180}:8000",
        "0.0.0.0:${WEATHER_PORT:-9180}:8000",
        "[::]:${WEATHER_PORT:-9180}:8000",
        "localhost:${WEATHER_PORT:-9180}:8000",
        "192.0.2.1:${WEATHER_PORT:-9180}:8000",
    ],
)
def test_wildcard_or_noncanonical_host_publishes_are_rejected(unsafe: str) -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    assert _is_exact_loopback(source)
    changed = source.replace(f'      - "{EXPECTED}"', f'      - "{unsafe}"')
    assert changed != source
    assert not _is_exact_loopback(changed)


def test_consumer_manifest_keeps_canonical_simple_deploy_target() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["repository"] == "rozkalnsandris/rozkalns_weather"
    assert manifest["target"]["alias"] == "rozkalns-weather-public-rpi5"
    assert manifest["compose"] == {
        "project": "rozkalns-weather-public",
        "file": "deploy/docker-compose.public.yml",
        "service": "weather",
    }
    assert manifest["persistence"]["volumes"] == ["weather_data"]
    assert manifest["health"]["liveness_path"] == "/health"
    assert manifest["health"]["readiness"] == {
        "state": "required",
        "path": "/ready",
    }
    assert "cloudflare-dns-network" in manifest["forbidden_operations"]
    assert "database-schema-data-mutation" in manifest["forbidden_operations"]


def test_ingest_storage_health_and_privacy_boundaries_remain_intact() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    weather = _weather_block(source)
    ingest = source.split("\n  public-ingest:\n", 1)[1].split(
        "\nvolumes:\n", 1
    )[0]
    assert "WEATHER_RUNTIME_MODE: public-only" in weather
    assert "DATABASE_INIT_MODE: require-existing" in weather
    assert "      - weather_data:/app/data" in weather
    assert "http://127.0.0.1:8000/ready" in weather
    assert 'command: ["python", "-m", "rozkalns_weather", "ingest-public"]' in ingest
    assert 'profiles: ["jobs"]' in ingest
    assert "      - weather_data:/app/data" in ingest
    assert "ports:" not in ingest
    assert source.endswith("\nvolumes:\n  weather_data:\n")
    assert "HOME_LAT" not in source
    assert "HOME_LON" not in source
