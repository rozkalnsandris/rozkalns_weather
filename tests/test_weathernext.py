from datetime import datetime, timezone

from rozkalns_weather.providers.weathernext import build_point_query, expected_available_at, latest_available_init, rows_to_run


def test_query_uses_current_weather_next_tables_and_statistics() -> None:
    init = datetime(2026, 9, 7, 0, tzinfo=timezone.utc)
    query = build_point_query(project="demo-project", dataset="weather", lat=51.5, lon=7.6, init_time=init, resolution="0p05")
    assert "weathernext_3_0_0_0p05deg" in query.table
    assert "station_head_temperature_2m_mean" in query.sql
    assert "station_head_temperature_2m_p90" in query.sql
    assert "ST_COVERS" in query.sql


def test_weather_next_rows_normalize_station_and_surface_units() -> None:
    init = datetime(2026, 9, 7, 0, tzinfo=timezone.utc)
    retrieved = datetime(2026, 9, 7, 8, 15, tzinfo=timezone.utc)
    station = rows_to_run([
        {"forecast_time": datetime(2026, 9, 7, 12, tzinfo=timezone.utc), "forecast_hour": 12,
         "station_head_temperature_2m_mean": 293.15, "station_head_temperature_2m_p10": 291.15, "station_head_temperature_2m_p90": 295.15}
    ], resolution="0p05", init_time=init, retrieved_at=retrieved)
    mean = next(v for v in station.values if v.statistic == "mean")
    assert round(mean.value, 2) == 20.0

    surface = rows_to_run([
        {"forecast_time": datetime(2026, 9, 7, 12, tzinfo=timezone.utc), "forecast_hour": 12,
         "total_precipitation_1hr_mean": 0.0012, "total_cloud_cover_mean": 0.75}
    ], resolution="0p1", init_time=init, retrieved_at=retrieved)
    rain = next(v for v in surface.values if v.variable == "precipitation_1h")
    cloud = next(v for v in surface.values if v.variable == "cloud_cover")
    assert rain.value == 1.2
    assert cloud.value == 75.0


def test_documented_dissemination_windows() -> None:
    init = datetime(2026, 9, 7, 0, tzinfo=timezone.utc)
    assert expected_available_at(init) == datetime(2026, 9, 7, 8, 10, tzinfo=timezone.utc)
    latest = latest_available_init(datetime(2026, 9, 7, 14, 30, tzinfo=timezone.utc))
    assert latest == datetime(2026, 9, 7, 6, tzinfo=timezone.utc)


def test_schema_probe_targets_current_tables() -> None:
    from rozkalns_weather.providers.weathernext import build_schema_probe_query
    sql = build_schema_probe_query(project="demo-project", dataset="weather")
    assert "INFORMATION_SCHEMA.COLUMN_FIELD_PATHS" in sql
    assert "weathernext_3_0_0_0p05deg" in sql
    assert "weathernext_3_0_0_0p1deg" in sql
