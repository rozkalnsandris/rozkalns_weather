from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from rozkalns_weather.models import ForecastRun, ForecastValue
from rozkalns_weather.providers.weathernext import STATS
from rozkalns_weather.weathernext_snapshot_admission import (
    REASON_CANARY_INVALID,
    REASON_SCHEMA_MISMATCH,
    REASON_SNAPSHOT_DUPLICATE,
    REASON_STALE,
    REASON_STATISTICS_INCOMPLETE,
    REASON_TEMPORAL_INVALID,
    SnapshotAdmissionError,
    validate_first_snapshot_admission,
)


INIT = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)
SCHEMA_FINGERPRINT = "schema-fingerprint-001"


def _first_access_evidence() -> dict[str, object]:
    return {
        "state": "canary_ready_for_snapshot",
        "selected_init_time_utc": "2026-09-08T06:00:00Z",
        "schema": {
            "state": "linked_dataset_ready",
            "observed_required_fingerprint": SCHEMA_FINGERPRINT,
        },
        "dry_run": [
            {"resolution": "0p05", "within_cap": True},
            {"resolution": "0p1", "within_cap": True},
        ],
        "canary": {"product_surfaces_complete": True},
        "provenance": {"complete": True},
    }


def _values(
    *,
    variable: str,
    unit: str,
    base_value: float,
    accumulation_window_minutes: int | None = None,
    statistics: tuple[str, ...] = STATS,
) -> tuple[ForecastValue, ...]:
    valid = INIT + timedelta(hours=1)
    return tuple(
        ForecastValue(
            valid_time_utc=valid,
            lead_hours=1,
            variable=variable,
            statistic=statistic,
            value=base_value,
            unit=unit,
            accumulation_window_minutes=accumulation_window_minutes,
        )
        for statistic in statistics
    )


def _run(
    *,
    resolution: str,
    retrieved_at: datetime | None = None,
    include_incomplete_second_variable: bool = False,
) -> ForecastRun:
    retrieved_at = retrieved_at or datetime(2026, 9, 8, 14, 30, tzinfo=timezone.utc)
    if resolution == "0p05":
        values = _values(variable="temperature_2m", unit="degC", base_value=20.0)
        if include_incomplete_second_variable:
            values += _values(
                variable="dewpoint_2m",
                unit="degC",
                base_value=15.0,
                statistics=tuple(stat for stat in STATS if stat != "p90"),
            )
        surface = "BigQuery WeatherNext 3 0p05"
    else:
        values = _values(
            variable="precipitation_1h",
            unit="mm",
            base_value=0.2,
            accumulation_window_minutes=60,
        )
        surface = "BigQuery WeatherNext 3 0p1"
    return ForecastRun(
        provider="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        model_version="3.0.0",
        init_time_utc=INIT,
        retrieved_at_utc=retrieved_at,
        source_surface=surface,
        transport_provider="Google BigQuery",
        values=values,
        source_metadata={
            "resolution": resolution,
            "statistics": list(STATS),
            "run_class": "synoptic_360h",
            "forecast_horizon_hours": 360,
            "expected_available_at_utc": "2026-09-08T14:10:00Z",
            "upstream_available_at_observed": False,
        },
    )


def _admit(
    *,
    runs: list[ForecastRun] | None = None,
    schema_fingerprint: str = SCHEMA_FINGERPRINT,
    admission_time: datetime | None = None,
    maximum_age_hours: int = 6,
    existing: tuple[str, ...] = (),
) -> dict[str, object]:
    return validate_first_snapshot_admission(
        first_access_evidence=_first_access_evidence(),
        runs=runs or [_run(resolution="0p05"), _run(resolution="0p1")],
        candidate_schema_fingerprint=schema_fingerprint,
        admission_time_utc=admission_time or datetime(2026, 9, 8, 15, tzinfo=timezone.utc),
        maximum_candidate_age_hours=maximum_age_hours,
        existing_admission_fingerprints=existing,
    )


def test_descriptor_freezes_first_snapshot_admission_contract() -> None:
    payload = json.loads(Path("deploy/weathernext-first-snapshot-admission.json").read_text())
    assert payload["contract"] == "weathernext3-first-snapshot-admission.v1"
    assert payload["depends_on"] == [
        "weathernext3-first-access.v1",
        "weathernext3-sustained-collection.v1",
    ]
    assert payload["freshness"]["maximum_candidate_age_hours_must_be_explicit"] is True
    assert payload["authority"]["production_sqlite_write_authorized"] is False


def test_happy_path_emits_privacy_safe_write_plan_without_values() -> None:
    result = _admit()
    assert result["state"] == "snapshot_write_plan_ready"
    assert result["schema_fingerprint"] == SCHEMA_FINGERPRINT
    assert result["product_surfaces"] == ["0p05", "0p1"]
    assert result["canary_evidence_validated"] is True
    assert result["provenance_validated"] is True
    assert result["statistics_matrix_validated"] is True
    assert result["production_write_performed"] is False
    assert result["real_values_exposed"] is False
    assert result["private_fields_exposed"] is False
    assert "snapshot_admission_fingerprint" in result
    serialized = json.dumps(result, sort_keys=True)
    assert "20.0" not in serialized
    assert "0.2" not in serialized


def test_schema_drift_is_rejected_with_stable_reason() -> None:
    with pytest.raises(SnapshotAdmissionError) as exc:
        _admit(schema_fingerprint="different-schema")
    assert exc.value.reason_code == REASON_SCHEMA_MISMATCH


def test_stale_candidate_is_rejected_against_explicit_age_bound() -> None:
    with pytest.raises(SnapshotAdmissionError) as exc:
        _admit(
            admission_time=datetime(2026, 9, 8, 18, tzinfo=timezone.utc),
            maximum_age_hours=2,
        )
    assert exc.value.reason_code == REASON_STALE


def test_duplicate_snapshot_identity_is_rejected() -> None:
    first = _admit()
    fingerprint = str(first["snapshot_admission_fingerprint"])
    with pytest.raises(SnapshotAdmissionError) as exc:
        _admit(existing=(fingerprint,))
    assert exc.value.reason_code == REASON_SNAPSHOT_DUPLICATE


def test_snapshot_identity_is_deterministic_across_run_order_and_retrieval_receipt_time() -> None:
    first = _admit()
    later_receipt_runs = [
        _run(
            resolution="0p1",
            retrieved_at=datetime(2026, 9, 8, 14, 35, tzinfo=timezone.utc),
        ),
        _run(
            resolution="0p05",
            retrieved_at=datetime(2026, 9, 8, 14, 36, tzinfo=timezone.utc),
        ),
    ]
    second = _admit(runs=later_receipt_runs)
    assert first["snapshot_admission_fingerprint"] == second["snapshot_admission_fingerprint"]


def test_each_variable_valid_time_requires_complete_statistics_matrix() -> None:
    runs = [
        _run(resolution="0p05", include_incomplete_second_variable=True),
        _run(resolution="0p1"),
    ]
    with pytest.raises(SnapshotAdmissionError) as exc:
        _admit(runs=runs)
    assert exc.value.reason_code == REASON_STATISTICS_INCOMPLETE


def test_temporal_provenance_rejects_retrieval_before_init() -> None:
    runs = [
        _run(
            resolution="0p05",
            retrieved_at=datetime(2026, 9, 8, 5, 59, tzinfo=timezone.utc),
        ),
        _run(resolution="0p1"),
    ]
    with pytest.raises(SnapshotAdmissionError) as exc:
        _admit(runs=runs)
    assert exc.value.reason_code == REASON_TEMPORAL_INVALID


def test_incomplete_canary_is_rejected_before_write_plan() -> None:
    evidence = _first_access_evidence()
    evidence["canary"] = {"product_surfaces_complete": False}
    with pytest.raises(SnapshotAdmissionError) as exc:
        validate_first_snapshot_admission(
            first_access_evidence=evidence,
            runs=[_run(resolution="0p05"), _run(resolution="0p1")],
            candidate_schema_fingerprint=SCHEMA_FINGERPRINT,
            admission_time_utc=datetime(2026, 9, 8, 15, tzinfo=timezone.utc),
            maximum_candidate_age_hours=6,
        )
    assert exc.value.reason_code == REASON_CANARY_INVALID
