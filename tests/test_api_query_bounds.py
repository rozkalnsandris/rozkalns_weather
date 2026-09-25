from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.models import ForecastRun, ForecastValue
from rozkalns_weather.query_bounds import CONTRACT, MAX_PROVIDER_SELECTIONS, validate_date_window
from rozkalns_weather.reporting import _month_bounds


def _fixture(tmp_path) -> tuple[TestClient, Database, datetime]:
    settings = Settings.from_env(
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}",
            "HOME_LAT": "51.5",
            "HOME_LON": "7.6",
        }
    )
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))
    init = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    _insert_run(database, init=init, retrieved=init + timedelta(minutes=10), version="fixture-v1")
    return client, database, init


def _insert_run(
    database: Database,
    *,
    init: datetime,
    retrieved: datetime,
    version: str,
    provider: str = "icon_d2",
) -> None:
    values = tuple(
        ForecastValue(
            valid_time_utc=init + timedelta(hours=lead),
            lead_hours=float(lead),
            variable="temperature_2m",
            statistic="deterministic",
            value=10.0 + lead,
            unit="degC",
        )
        for lead in range(1, 6)
    )
    run = ForecastRun(
        provider=provider,
        model_provider="DWD" if provider == "icon_d2" else "ECMWF",
        model_name="ICON-D2" if provider == "icon_d2" else "IFS",
        model_version=version,
        init_time_utc=init,
        retrieved_at_utc=retrieved,
        source_surface="fixture",
        values=values,
    )
    database.insert_forecast_run(run, location_id="home")


def test_hourly_default_preserves_complete_existing_semantics(tmp_path) -> None:
    client, _, _ = _fixture(tmp_path)

    response = client.get("/api/hourly?hours=6")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["series"]) == 5
    assert payload["query"]["contract"] == CONTRACT
    assert payload["query"]["total_rows"] == 5
    assert payload["query"]["returned_rows"] == 5
    assert payload["query"]["complete"] is True
    assert payload["query"]["next_cursor"] is None
    assert payload["query"]["silent_truncation"] is False


def test_hourly_continuation_is_deterministic_and_complete(tmp_path) -> None:
    client, _, _ = _fixture(tmp_path)

    first = client.get("/api/hourly?hours=6&page_size=2")
    assert first.status_code == 200
    first_payload = first.json()
    assert len(first_payload["series"]) == 2
    assert first_payload["query"]["complete"] is False
    cursor = first_payload["query"]["next_cursor"]
    assert cursor

    repeat = client.get("/api/hourly?hours=6&page_size=2")
    assert repeat.status_code == 200
    assert repeat.json() == first_payload

    second = client.get("/api/hourly", params={"hours": 6, "page_size": 2, "cursor": cursor})
    assert second.status_code == 200
    second_payload = second.json()
    third = client.get(
        "/api/hourly",
        params={"hours": 6, "page_size": 2, "cursor": second_payload["query"]["next_cursor"]},
    )
    assert third.status_code == 200
    third_payload = third.json()

    combined = first_payload["series"] + second_payload["series"] + third_payload["series"]
    assert len(combined) == 5
    assert [item["valid_time_utc"] for item in combined] == sorted(
        item["valid_time_utc"] for item in combined
    )
    assert third_payload["query"]["complete"] is True
    assert third_payload["query"]["returned_rows"] == 1
    assert third_payload["query"]["next_cursor"] is None


def test_hourly_cursor_rejects_snapshot_drift(tmp_path) -> None:
    client, database, init = _fixture(tmp_path)
    first = client.get("/api/hourly?hours=6&page_size=2")
    assert first.status_code == 200
    cursor = first.json()["query"]["next_cursor"]

    _insert_run(
        database,
        init=init + timedelta(hours=1),
        retrieved=init + timedelta(hours=1, minutes=10),
        version="fixture-v2",
    )

    continuation = client.get(
        "/api/hourly",
        params={"hours": 6, "page_size": 2, "cursor": cursor},
    )
    assert continuation.status_code == 409
    assert continuation.json()["reason_codes"] == ["CURSOR_SNAPSHOT_MISMATCH"]


def test_over_limit_invalid_and_multi_provider_expansion_use_reason_codes(tmp_path) -> None:
    client, _, _ = _fixture(tmp_path)

    over_window = client.get("/api/hourly?hours=361")
    assert over_window.status_code == 422
    assert over_window.json()["reason_codes"] == ["QUERY_WINDOW_TOO_LARGE"]

    invalid_window = client.get("/api/daily?days=0")
    assert invalid_window.status_code == 422
    assert invalid_window.json()["reason_codes"] == ["INVALID_QUERY_RANGE"]

    providers = ",".join(f"provider_{index}" for index in range(MAX_PROVIDER_SELECTIONS + 1))
    broad = client.get("/api/hourly", params={"providers": providers})
    assert broad.status_code == 422
    assert broad.json()["reason_codes"] == ["SELECTION_TOO_BROAD"]

    verification = client.get("/api/verification/summary?days=367")
    assert verification.status_code == 422
    assert verification.json()["reason_codes"] == ["QUERY_WINDOW_TOO_LARGE"]


def test_provider_and_model_filters_preserve_exact_completeness_metadata(tmp_path) -> None:
    client, database, init = _fixture(tmp_path)
    _insert_run(
        database,
        init=init,
        retrieved=init + timedelta(minutes=20),
        version="ifs-v1",
        provider="ecmwf_ifs",
    )

    response = client.get(
        "/api/hourly",
        params={"hours": 6, "providers": "icon_d2", "model_versions": "fixture-v1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert {item["provider"] for item in payload["series"]} == {"icon_d2"}
    assert {item["model_version"] for item in payload["series"]} == {"fixture-v1"}
    assert payload["query"]["total_rows"] == len(payload["series"]) == 5
    assert payload["query"]["complete"] is True


def test_query_guards_and_health_readiness_do_not_mutate_corpus(tmp_path) -> None:
    client, database, _ = _fixture(tmp_path)
    before = database.corpus_stats()

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert client.get("/api/hourly?hours=361").status_code == 422
    assert client.get("/api/hourly?hours=6&page_size=2").status_code == 200

    after = database.corpus_stats()
    assert after["forecast_runs"] == before["forecast_runs"]
    assert after["observations"] == before["observations"]
    assert after["providers"] == before["providers"]


def test_monthly_reporting_query_window_is_explicitly_bounded() -> None:
    start, end = _month_bounds("2026-09")
    assert validate_date_window(start, end) == 30 * 86400
