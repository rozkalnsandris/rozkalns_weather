from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from rozkalns_weather.config import Settings
from rozkalns_weather.models import ForecastRun, ForecastValue
from rozkalns_weather.providers.weathernext import EXPECTED_SCHEMA, STATS, rows_to_run
from rozkalns_weather.weathernext_access import (
    MAX_ALLOWED_BYTES_BILLED,
    WeatherNextCostLimit,
    build_canary_plan,
    build_first_snapshot_write_envelope,
    classify_access_error,
    dry_run_canary_queries,
    expected_required_schema_fingerprint,
    preflight_access,
    schema_summary,
    validate_canary_rows,
    validate_first_access_evidence,
    validate_provenance,
)


def _schema_rows():
    return [
        {"table_name": table, "field_path": path}
        for table, paths in EXPECTED_SCHEMA.items()
        for path in paths
    ]


class FakeJob:
    def __init__(self, *, total_bytes_processed=0, rows=None):
        self.total_bytes_processed = total_bytes_processed
        self._rows = rows or []

    def result(self):
        return self._rows


class FakeClient:
    def __init__(self, estimates=(100, 200)):
        self.estimates = list(estimates)
        self.calls = []

    def query(self, sql, job_config=None):
        self.calls.append((sql, job_config))
        if getattr(job_config, "dry_run", False):
            return FakeJob(total_bytes_processed=self.estimates.pop(0))
        return FakeJob(rows=[])


class FakeAdapter:
    def __init__(self, rows, client=None):
        self.rows = rows
        self.client = client or FakeClient()

    def schema_probe(self):
        return self.rows

    def _client_or_create(self):
        return self.client


def _config(**kwargs):
    return SimpleNamespace(**kwargs)


def test_first_access_descriptor_is_source_only() -> None:
    payload = json.loads(Path("deploy/weathernext-first-access.json").read_text())
    assert payload["contract"] == "weathernext3-first-access.v1"
    assert payload["query_guardrails"]["dry_run_required_before_canary"] is True
    assert payload["query_guardrails"]["initial_location_id"] == "station_10416"
    assert payload["authority"]["source_auto_full_authorizes_real_bigquery_query"] is False
    assert payload["authority"]["source_auto_full_authorizes_first_snapshot_write"] is False


def test_schema_fingerprint_uses_required_public_contract_only() -> None:
    summary = schema_summary(_schema_rows())
    assert summary["state"] == "linked_dataset_ready"
    assert summary["observed_required_fingerprint"] == expected_required_schema_fingerprint()
    assert summary["observed_required_path_count"] == summary["required_path_count"]


def test_schema_drift_is_detected_before_canary() -> None:
    rows = _schema_rows()
    rows.pop()
    summary = schema_summary(rows)
    assert summary["state"] == "schema_changed"
    assert summary["schema_errors"]


def test_access_error_classes_do_not_mask_permission_or_link_state() -> None:
    assert classify_access_error(RuntimeError("403 Permission denied")) == "permission_denied"
    assert classify_access_error(RuntimeError("Dataset linked_weather not found: 404")) == "dataset_unlinked"
    assert classify_access_error(RuntimeError("Unrecognized name station_head_x")) == "schema_changed"


def test_canary_plan_is_one_init_bounded_and_station_only() -> None:
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    init = datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc)
    plan = build_canary_plan(
        now=now,
        init_time=init,
        hours_limit=6,
        maximum_bytes_billed=500_000_000,
    )
    assert plan["location_id"] == "station_10416"
    assert plan["hours_limit"] == 6
    assert plan["selected_init_time_utc"] == "2026-09-08T07:00:00Z"
    assert plan["dry_run_required"] is True
    assert plan["real_query_performed"] is False
    with pytest.raises(ValueError):
        build_canary_plan(
            now=now,
            init_time=init,
            hours_limit=25,
            maximum_bytes_billed=500_000_000,
        )
    with pytest.raises(ValueError):
        build_canary_plan(
            now=now,
            init_time=init,
            hours_limit=6,
            maximum_bytes_billed=MAX_ALLOWED_BYTES_BILLED + 1,
        )


def test_dry_run_estimates_both_surfaces_before_real_query() -> None:
    client = FakeClient(estimates=(111, 222))
    evidence = dry_run_canary_queries(
        client=client,
        project="demo-project",
        dataset="linked_weather",
        lat=51.5,
        lon=7.6,
        init_time=datetime(2026, 9, 8, 6, tzinfo=timezone.utc),
        hours_limit=6,
        maximum_bytes_billed=1000,
        job_config_factory=_config,
    )
    assert [item.estimated_bytes for item in evidence] == [111, 222]
    assert all(item.within_cap for item in evidence)
    assert all(call[1].dry_run is True for call in client.calls)
    assert all("SELECT *" not in call[0] for call in client.calls)


def test_dry_run_cost_cap_rejects_before_canary() -> None:
    client = FakeClient(estimates=(1001, 1))
    with pytest.raises(WeatherNextCostLimit):
        dry_run_canary_queries(
            client=client,
            project="demo-project",
            dataset="linked_weather",
            lat=51.5,
            lon=7.6,
            init_time=datetime(2026, 9, 8, 6, tzinfo=timezone.utc),
            hours_limit=6,
            maximum_bytes_billed=1000,
            job_config_factory=_config,
        )
    assert len(client.calls) == 1


def test_preflight_is_sanitized_and_does_not_need_sqlite() -> None:
    settings = Settings.from_env(
        {
            "GOOGLE_CLOUD_PROJECT": "demo-project",
            "WEATHERNEXT_BIGQUERY_DATASET": "linked_weather",
            "DATABASE_URL": "sqlite:///unused.db",
        }
    )
    client = FakeClient(estimates=(10, 20))
    payload = preflight_access(
        settings=settings,
        now=datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc),
        hours_limit=6,
        maximum_bytes_billed=1000,
        adapter=FakeAdapter(_schema_rows(), client),
        job_config_factory=_config,
    )
    assert payload["state"] == "ready_for_canary"
    assert payload["coordinates_exposed"] is False
    assert payload["credentials_exposed"] is False
    assert payload["production_write_performed"] is False
    rendered = json.dumps(payload)
    assert "demo-project" not in rendered
    assert "linked_weather" not in rendered


def test_canary_presence_requires_both_weather_next_surfaces() -> None:
    result = validate_canary_rows(
        [
            {
                "station_head_temperature_2m_mean": 293.0,
                "station_head_dewpoint_temperature_2m_mean": 287.0,
            }
        ],
        [{"total_precipitation_1hr_mean": 0.001}],
    )
    assert result["product_surfaces_complete"] is True
    assert result["values_exposed"] is False
    assert validate_canary_rows([], [{"total_precipitation_1hr_mean": 0.001}])["product_surfaces_complete"] is False


def test_provenance_validator_requires_real_stats_and_no_fabricated_publication_time() -> None:
    init = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)
    valid = init + timedelta(hours=1)
    values = tuple(
        ForecastValue(
            valid_time_utc=valid,
            lead_hours=1,
            variable="temperature_2m",
            statistic=stat,
            value=20.0,
            unit="degC",
        )
        for stat in STATS
    ) + tuple(
        ForecastValue(
            valid_time_utc=valid,
            lead_hours=1,
            variable="precipitation_1h",
            statistic=stat,
            value=0.0,
            unit="mm",
            accumulation_window_minutes=60,
        )
        for stat in STATS
    )
    run = ForecastRun(
        provider="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        model_version="3.0.0",
        init_time_utc=init,
        retrieved_at_utc=init + timedelta(hours=9),
        source_surface="BigQuery WeatherNext 3 0.05° station + 0.1° surface",
        transport_provider="Google BigQuery",
        values=values,
        source_metadata={
            "statistics": list(STATS),
            "run_class": "synoptic_360h",
            "forecast_horizon_hours": 360,
            "expected_available_at_utc": "2026-09-08T14:10:00Z",
            "upstream_available_at_observed": False,
        },
    )
    assert validate_provenance(run)["complete"] is True
    bad = ForecastRun(
        provider=run.provider,
        model_provider=run.model_provider,
        model_name=run.model_name,
        model_version=run.model_version,
        init_time_utc=run.init_time_utc,
        retrieved_at_utc=run.retrieved_at_utc,
        source_surface=run.source_surface,
        transport_provider=run.transport_provider,
        values=run.values,
        source_metadata=run.source_metadata,
        upstream_available_at_utc=init + timedelta(hours=8, minutes=10),
    )
    assert "unverified_upstream_available_at" in validate_provenance(bad)["errors"]


def test_rows_to_run_does_not_fabricate_expected_dissemination_as_observed_publication() -> None:
    init = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)
    run = rows_to_run(
        [
            {
                "forecast_time": init + timedelta(hours=1),
                "forecast_hour": 1,
                "station_head_temperature_2m_mean": 293.15,
            }
        ],
        resolution="0p05",
        init_time=init,
        retrieved_at=init + timedelta(hours=9),
    )
    assert run.upstream_available_at_utc is None
    assert run.source_metadata["upstream_available_at_observed"] is False
    assert run.source_metadata["expected_available_at_utc"] == "2026-09-08T14:10:00Z"


def test_first_snapshot_write_envelope_requires_sanitized_complete_canary() -> None:
    schema = schema_summary(_schema_rows())
    evidence = {
        "state": "canary_ready_for_snapshot",
        "selected_init_time_utc": "2026-09-08T06:00:00Z",
        "schema": schema,
        "dry_run": [
            {"resolution": "0p05", "within_cap": True},
            {"resolution": "0p1", "within_cap": True},
        ],
        "canary": {"product_surfaces_complete": True},
        "provenance": {"complete": True},
    }
    validated = validate_first_access_evidence(evidence)
    assert validated["state"] == "canary_ready_for_snapshot"
    envelope = build_first_snapshot_write_envelope(evidence)
    assert envelope["state"] == "first_snapshot_write_eligible"
    assert envelope["requires_exact_private_live_data_authority"] is True
    assert envelope["write_performed"] is False
    evidence["google_cloud_project"] = "private-project"
    with pytest.raises(ValueError):
        validate_first_access_evidence(evidence)
