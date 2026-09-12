from datetime import datetime, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database


def _client(tmp_path) -> tuple[TestClient, Database]:
    settings = Settings.from_env(
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}",
            "HOME_LAT": "51.5",
            "HOME_LON": "7.6",
        }
    )
    database = Database(settings.database_url)
    return TestClient(create_app(settings=settings, database=database)), database


def test_pwa_has_accessible_explicit_degraded_state_regions(tmp_path) -> None:
    client, _ = _client(tmp_path)
    root = client.get("/").text
    css = client.get("/static/app.css").text

    for state_id in (
        "networkState",
        "currentState",
        "overviewTempState",
        "overviewPrecipState",
        "dailyState",
        "providerState",
        "modelsTempState",
        "modelsPrecipState",
        "warningsState",
        "radarState",
    ):
        assert f'id="{state_id}"' in root

    assert 'role="status"' in root
    assert 'aria-live="polite"' in root
    assert 'class="panel warning"' in root
    assert 'data-warning-authority="DWD"' in root
    assert "DWD official warnings" in root
    for state in ("fresh", "stale", "error", "offline"):
        assert f".state-{state}" in css
    assert "@media(max-width:560px)" in css
    assert ".provider-grid{grid-template-columns:1fr}" in css


def test_pwa_cached_api_fallback_is_explicitly_timestamped_and_not_current(tmp_path) -> None:
    client, _ = _client(tmp_path)
    script = client.get("/static/app.js").text

    assert 'DATA_CACHE_PREFIX = "rozkalns-weather:pwa-cache:v1:"' in script
    assert "cached_at_utc" in script
    assert 'fetch(url, { cache: "no-store" })' in script
    assert '"stale-cache"' in script
    assert '"offline-cache"' in script
    assert "Data is not current." in script
    assert "last-known" in script
    assert 'window.addEventListener("offline"' in script
    assert 'window.addEventListener("online"' in script
    assert "refresh();" in script


def test_partial_provider_outage_is_isolated_and_recovery_is_visible(tmp_path) -> None:
    client, database = _client(tmp_path)
    now = datetime.now(timezone.utc)

    database.set_provider_status(
        "icon_d2",
        state="error",
        now=now,
        detail="upstream_or_transport:fixture",
        model_name="ICON-D2",
        init_time=now,
    )
    database.set_provider_status(
        "ecmwf_ifs",
        state="ok",
        now=now,
        detail="fixture",
        model_name="IFS HRES",
        init_time=now,
    )

    degraded = client.get("/api/health/providers").json()
    states = {item["id"]: item for item in degraded["providers"]}
    assert states["icon_d2"]["freshness_state"] == "error"
    assert states["ecmwf_ifs"]["freshness_state"] == "fresh"

    database.set_provider_status(
        "icon_d2",
        state="ok",
        now=now,
        detail="recovered",
        model_name="ICON-D2",
        init_time=now,
    )
    recovered = client.get("/api/health/providers").json()
    recovered_states = {item["id"]: item for item in recovered["providers"]}
    assert recovered_states["icon_d2"]["freshness_state"] == "fresh"
    assert recovered_states["ecmwf_ifs"]["freshness_state"] == "fresh"

    script = client.get("/static/app.js").text
    assert "Healthy providers remain visible" in script
    assert "Partial provider degradation" in script


def test_dwd_warning_authority_remains_explicit_when_cached_or_offline(tmp_path) -> None:
    client, _ = _client(tmp_path)
    root = client.get("/").text
    script = client.get("/static/app.js").text

    assert "DWD warning slānis ir autoritatīvs" in root
    assert "DWD official warning" in script
    assert "NOT current official warning status" in script
    assert "DWD remains the authority; reconnect and refresh before relying on warnings." in script
    assert "WeatherNext" not in root.split('<section id="safety"', 1)[1].split("</section>", 1)[0]


def test_service_worker_caches_shell_only_not_api_payloads(tmp_path) -> None:
    client, _ = _client(tmp_path)
    service_worker = client.get("/static/sw.js").text

    assert "const ASSETS=" in service_worker
    assert "/static/app.js" in service_worker
    assert "/static/app.css" in service_worker
    assert "/api/" not in service_worker
    assert "cache.put(" not in service_worker
