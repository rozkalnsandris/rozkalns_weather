from datetime import datetime, timezone

from rozkalns_weather.providers.weathernext import (
    WeatherNextBigQueryAdapter,
    WeatherNextDataLatency,
    available_init_candidates,
    build_point_query,
    expected_available_at,
    forecast_horizon_hours,
    latest_available_init,
    rows_to_run,
    run_class,
)


def test_query_uses_current_weather_next_tables_and_statistics() -> None:
    init = datetime(2026, 9, 7, 0, tzinfo=timezone.utc)
    query = build_point_query(project="demo-project", dataset="weather", lat=51.5, lon=7.6, init_time=init, resolution="0p05")
    assert "weathernext_3_0_0_0p05deg" in query.table
    assert "station_head_temperature_2m_mean" in query.sql
    assert "station_head_temperature_2m_p90" in query.sql
    assert "t.init_time = TIMESTAMP" in query.sql


def test_weather_next_rows_normalize_units() -> None:
    init = datetime(2026, 9, 7, 0, tzinfo=timezone.utc)
    retrieved = datetime(2026, 9, 7, 8, 15, tzinfo=timezone.utc)
    station = rows_to_run([
        {"forecast_time": datetime(2026, 9, 7, 12, tzinfo=timezone.utc), "forecast_hour": 12, "station_head_temperature_2m_mean": 293.15, "station_head_temperature_2m_p10": 291.15, "station_head_temperature_2m_p90": 295.15}
    ], resolution="0p05", init_time=init, retrieved_at=retrieved)
    mean = next(value for value in station.values if value.statistic == "mean")
    assert round(mean.value, 2) == 20.0


def test_hourly_interim_runs_are_not_discarded() -> None:
    now = datetime(2026, 9, 7, 14, 30, tzinfo=timezone.utc)
    latest = latest_available_init(now)
    assert latest == datetime(2026, 9, 7, 7, tzinfo=timezone.utc)
    assert run_class(latest) == "interim_48h"
    assert forecast_horizon_hours(latest) == 48
    assert latest_available_init(now, synoptic_only=True) == datetime(2026, 9, 7, 6, tzinfo=timezone.utc)
    assert expected_available_at(datetime(2026, 9, 7, 6, tzinfo=timezone.utc)) == datetime(2026, 9, 7, 14, 10, tzinfo=timezone.utc)


def test_latency_fallback_tries_previous_disseminated_hourly_run(monkeypatch) -> None:
    now = datetime(2026, 9, 7, 14, 30, tzinfo=timezone.utc)
    candidates = available_init_candidates(now, limit=3)
    assert candidates[:2] == (
        datetime(2026, 9, 7, 7, tzinfo=timezone.utc),
        datetime(2026, 9, 7, 6, tzinfo=timezone.utc),
    )
    adapter = WeatherNextBigQueryAdapter(project="demo-project", dataset="weather", client=object())
    attempted = []
    sentinel = object()

    def fake_fetch(*, lat, lon, now, init_time):
        attempted.append(init_time)
        if len(attempted) == 1:
            raise WeatherNextDataLatency("delayed")
        return sentinel

    monkeypatch.setattr(adapter, "fetch", fake_fetch)
    result = adapter.fetch_latest_with_fallback(lat=51.5, lon=7.6, now=now, max_candidates=3)
    assert result is sentinel
    assert attempted == list(candidates[:2])


def test_synoptic_runs_have_360h_horizon() -> None:
    init = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    assert run_class(init) == "synoptic_360h"
    assert forecast_horizon_hours(init) == 360
