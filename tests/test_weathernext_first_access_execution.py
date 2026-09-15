"""Synthetic fixtures only: no Google requests or empirical forecast claims."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from rozkalns_weather.providers.weathernext import EXPECTED_SCHEMA, STATION_FIELDS, SURFACE_FIELDS, STATS
from rozkalns_weather.weathernext_access import (
    WeatherNextCostLimit, dry_run_canary_queries, execute_canary_queries,
    read_first_access_canary, validate_first_access_evidence,
)

INIT = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)


def row(fields):
    native = {"K": 290.0, "Pa": 101300.0, "m/s": 2.0, "fraction": 0.5, "m": 0.001}
    return {"forecast_time": INIT + timedelta(hours=1), "forecast_hour": 1,
            **{f"{field}_{stat}": native[units[1]] for field, units in fields.items() for stat in STATS}}


class Client:
    def __init__(self, estimates=(100, 200), fail_at=None):
        self.calls = []
        self.estimates = iter(estimates)
        self.fail_at = fail_at
        self.station = row(STATION_FIELDS)
        self.surface = row(SURFACE_FIELDS)

    def query(self, sql, *, job_config, **kwargs):
        assert kwargs == {"retry": None, "job_retry": None, "timeout": 60}
        assert 0 < job_config.maximum_bytes_billed <= 1073741824
        self.calls.append((sql, job_config))
        if len(self.calls) == self.fail_at:
            raise TimeoutError("fixture timeout")
        if job_config.dry_run:
            return SimpleNamespace(total_bytes_processed=next(self.estimates))
        if "INFORMATION_SCHEMA" in sql:
            rows = [{"table_name": table, "field_path": path}
                    for table, paths in EXPECTED_SCHEMA.items() for path in paths]
        else:
            rows = [self.station if "0p05deg" in sql else self.surface]

        def result(**result_kwargs):
            expected = {"retry": None, "job_retry": None, "timeout": 60}
            if "INFORMATION_SCHEMA" not in sql:
                expected["max_results"] = 8
            assert result_kwargs == expected
            return rows
        return SimpleNamespace(result=result)


def args(client):
    return dict(client=client, project="fixture-project", dataset="fixture_dataset",
                lat=51.5, lon=7.6, init_time=INIT, hours_limit=6,
                maximum_bytes_billed=1000, job_config_factory=SimpleNamespace)


def test_exact_query_dry_run_binding_rejects_changed_scope_and_duplicate_surface():
    client = Client()
    original = args(client)
    dry = dry_run_canary_queries(**original)
    for changed in ({"dataset": "other_fixture"}, {"init_time": INIT + timedelta(hours=1)},
                    {"hours_limit": 7}, {"lat": 52.0}):
        with pytest.raises(WeatherNextCostLimit):
            execute_canary_queries(**(original | changed), dry_run_evidence=dry)
    with pytest.raises(WeatherNextCostLimit):
        execute_canary_queries(**original, dry_run_evidence=(dry[0], dry[0]))
    assert len(client.calls) == 2
    # Tightening the real cap after the same exact dry-run is allowed.
    execute_canary_queries(**(original | {"maximum_bytes_billed": 250}), dry_run_evidence=dry)
    assert len(client.calls) == 4


@pytest.mark.parametrize("estimate", [None, -1, True, "100", 1001])
def test_missing_or_invalid_cost_evidence_cannot_become_zero(estimate):
    client = Client(estimates=(estimate, 100))
    with pytest.raises(WeatherNextCostLimit):
        dry_run_canary_queries(**args(client))
    assert len(client.calls) == 1


def collect(client):
    return read_first_access_canary(client=client, project="fixture-project", dataset="fixture_dataset",
        now=INIT + timedelta(hours=9), init_time=INIT, maximum_bytes_billed=1000,
        job_config_factory=SimpleNamespace)


def test_station_first_access_orders_capped_schema_dry_runs_canary_and_no_db(tmp_path, monkeypatch):
    from rozkalns_weather.db import Database
    def forbidden(*args, **kwargs):
        pytest.fail("first-access must not touch SQLite")
    monkeypatch.setattr(Database, "connect", forbidden)
    client = Client()
    evidence, runs = collect(client)
    assert [config.dry_run for _, config in client.calls] == [False, True, True, False, False]
    assert evidence["provenance"]["complete"] is True
    assert len(runs) == 2
    assert all(value.native_value is not None for run in runs for value in run.values)
    assert all("f.hours <= 6" in sql and "t.init_time = TIMESTAMP(" in sql
               for sql, _ in client.calls[1:])
    assert "fixture-project" not in str(evidence)
    assert "fixture_dataset" not in str(evidence)
    for corrupted in (
        evidence | {"schema": evidence["schema"] | {"observed_required_fingerprint": "0" * 64}},
        evidence | {"dry_run": [evidence["dry_run"][0]] * 2},
    ):
        with pytest.raises(ValueError):
            validate_first_access_evidence(corrupted)


def test_error_stops_without_second_query_or_fallback():
    client = Client(fail_at=4)
    with pytest.raises(TimeoutError):
        collect(client)
    assert len(client.calls) == 4


@pytest.mark.parametrize("corruption", ["missing_stat", "bad_lead", "zero_lead_mismatch", "missing_lead", "naive_time", "outside_bounds"])
def test_real_response_must_have_complete_statistics_and_temporal_provenance(corruption):
    client = Client()
    if corruption == "missing_stat":
        del client.station["station_head_temperature_2m_p90"]
    elif corruption == "bad_lead":
        client.station["forecast_hour"] = 2
    elif corruption == "zero_lead_mismatch":
        client.station["forecast_hour"] = 0
    elif corruption == "missing_lead":
        del client.station["forecast_hour"]
    elif corruption == "naive_time":
        client.station["forecast_time"] = "2026-09-08T07:00:00"
    else:
        client.station["forecast_hour"] = 7
        client.station["forecast_time"] = INIT + timedelta(hours=7)
    with pytest.raises(ValueError):
        collect(client)
