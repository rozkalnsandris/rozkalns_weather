from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from rozkalns_weather.models import ForecastRun, ForecastValue
from rozkalns_weather.providers.weathernext import STATS
from rozkalns_weather.weathernext_collection import (
    QuantileSample,
    VerificationSample,
    build_collection_plan,
    build_first_month_evidence,
    collection_health,
    evaluate_version_boundary,
    first_month_verification_eligibility,
    plan_bounded_recovery,
    reconcile_run_ledger,
    summarize_quantile_calibration,
    transition_lifecycle,
    validate_first_month_evidence,
    validate_snapshot_admission,
)


def _first_access_evidence() -> dict[str, object]:
    return {
        "state": "canary_ready_for_snapshot",
        "selected_init_time_utc": "2026-09-08T06:00:00Z",
        "schema": {
            "state": "linked_dataset_ready",
            "observed_required_fingerprint": "schema-fingerprint-001",
        },
        "dry_run": [
            {"resolution": "0p05", "within_cap": True},
            {"resolution": "0p1", "within_cap": True},
        ],
        "canary": {"product_surfaces_complete": True},
        "provenance": {"complete": True},
    }


def _run(*, resolution: str) -> ForecastRun:
    init = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)
    valid = init + timedelta(hours=1)
    if resolution == "0p05":
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
        )
        surface = "BigQuery WeatherNext 3 0p05"
    else:
        values = tuple(
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
        surface = "BigQuery WeatherNext 3 0p1"
    return ForecastRun(
        provider="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        model_version="3.0.0",
        init_time_utc=init,
        retrieved_at_utc=init + timedelta(hours=9),
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


def test_descriptor_freezes_source_only_sustained_collection_contract() -> None:
    payload = json.loads(Path("deploy/weathernext-sustained-collection.json").read_text())
    assert payload["contract"] == "weathernext3-sustained-collection.v1"
    assert payload["depends_on"] == "weathernext3-first-access.v1"
    assert payload["cadence"]["scheduler_activation_authorized"] is False
    assert payload["snapshot_admission"]["write_authorized_by_source_auto_full"] is False
    assert payload["authority"]["source_auto_full_authorizes_real_bigquery_reads"] is False
    assert payload["authority"]["source_auto_full_authorizes_production_corpus_writes"] is False


def test_lifecycle_is_explicit_and_fail_closed() -> None:
    assert transition_lifecycle("access_ready", "snapshot_admitted") == "snapshot_admissible"
    assert transition_lifecycle("snapshot_admissible", "first_snapshot_stored") == "collecting"
    assert transition_lifecycle("collecting", "provider_degraded") == "degraded"
    assert transition_lifecycle("degraded", "provider_recovered") == "collecting"
    assert transition_lifecycle("collecting", "version_change_detected") == "version_boundary"
    assert transition_lifecycle("collecting", "month_closed_eligible") == "first_month_ready"
    with pytest.raises(ValueError):
        transition_lifecycle("first_month_ready", "keep_going")


def test_snapshot_admission_requires_validated_two_surface_canary_and_never_writes() -> None:
    result = validate_snapshot_admission(
        first_access_evidence=_first_access_evidence(),
        runs=[_run(resolution="0p05"), _run(resolution="0p1")],
    )
    assert result["state"] == "snapshot_admissible"
    assert result["product_surfaces_complete"] is True
    assert result["requires_exact_private_live_data_authority"] is True
    assert result["production_write_performed"] is False
    assert result["real_values_exposed"] is False
    with pytest.raises(ValueError):
        validate_snapshot_admission(
            first_access_evidence=_first_access_evidence(),
            runs=[_run(resolution="0p05")],
        )


def test_collection_plan_is_dissemination_aware_and_dedupes_known_init() -> None:
    now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    known = datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc)
    plan = build_collection_plan(now=now, known_init_times=[known], limit=8)
    assert plan["state"] == "collection_plan_ready"
    assert plan["scheduler_activation_authorized"] is False
    assert plan["real_query_performed"] is False
    assert all(item["init_time_utc"] != "2026-09-08T07:00:00Z" for item in plan["planned_inits"])
    assert any(item["run_class"] == "synoptic_360h" for item in plan["planned_inits"])
    assert any(item["run_class"] == "interim_48h" for item in plan["planned_inits"])


def test_run_ledger_distinguishes_target_window_missing_and_retrieved() -> None:
    now = datetime(2026, 9, 8, 15, 50, tzinfo=timezone.utc)
    init06 = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)
    init07 = datetime(2026, 9, 8, 7, tzinfo=timezone.utc)
    init05 = datetime(2026, 9, 8, 5, tzinfo=timezone.utc)
    ledger = reconcile_run_ledger(
        now=now,
        expected_init_times=[init05, init06, init07],
        receipts={
            "2026-09-08T05:00:00Z": {
                "state": "retrieved",
                "retrieved_at_utc": "2026-09-08T12:40:00Z",
            }
        },
    )
    by_init = {item["init_time_utc"]: item for item in ledger}
    assert by_init["2026-09-08T05:00:00Z"]["state"] == "retrieved"
    assert by_init["2026-09-08T06:00:00Z"]["state"] == "missing"
    assert by_init["2026-09-08T07:00:00Z"]["state"] == "target_disseminated"


def test_recovery_plan_is_bounded_and_does_not_execute_reads_or_writes() -> None:
    now = datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc)
    ledger = [
        {"init_time_utc": "2026-09-08T06:00:00Z", "state": "missing"},
        {"init_time_utc": "2026-09-08T07:00:00Z", "state": "retrieved"},
    ]
    plan = plan_bounded_recovery(now=now, ledger=ledger, max_age_hours=24, max_inits=4)
    assert plan["planned_inits"] == ["2026-09-08T06:00:00Z"]
    assert plan["real_query_performed"] is False
    assert plan["production_write_performed"] is False
    assert plan["automatic_retry_or_cleanup"] is False
    with pytest.raises(ValueError):
        plan_bounded_recovery(now=now, ledger=ledger, max_age_hours=169)


def test_model_or_schema_change_creates_boundary_instead_of_silent_mix() -> None:
    compatible = evaluate_version_boundary(
        previous_model_version="3.0.0",
        previous_schema_fingerprint="abc",
        current_model_version="3.0.0",
        current_schema_fingerprint="abc",
    )
    assert compatible["collection_eligible"] is True
    schema_boundary = evaluate_version_boundary(
        previous_model_version="3.0.0",
        previous_schema_fingerprint="abc",
        current_model_version="3.0.0",
        current_schema_fingerprint="def",
    )
    assert schema_boundary["state"] == "version_boundary"
    assert schema_boundary["adapter_decision_required"] is True
    unknown = evaluate_version_boundary(
        previous_model_version="3.0.0",
        previous_schema_fingerprint="abc",
        current_model_version="4.0.0",
        current_schema_fingerprint="new",
    )
    assert unknown["reason"] == "unsupported_model_version"
    assert unknown["collection_eligible"] is False


def test_health_keeps_expected_publication_and_retrieval_separate() -> None:
    init = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)
    result = collection_health(
        now=datetime(2026, 9, 8, 16, tzinfo=timezone.utc),
        init_time=init,
        observed_publication_at_utc=datetime(2026, 9, 8, 14, 20, tzinfo=timezone.utc),
        retrieved_at_utc=datetime(2026, 9, 8, 14, 30, tzinfo=timezone.utc),
        consecutive_missing_runs=0,
    )
    assert result["expected_available_at_utc"] == "2026-09-08T14:10:00Z"
    assert result["observed_publication_at_utc"] == "2026-09-08T14:20:00Z"
    assert result["retrieved_at_utc"] == "2026-09-08T14:30:00Z"
    assert result["observed_publication_lag_minutes"] == 10.0
    assert result["retrieval_lag_minutes"] == 20.0
    assert result["private_fields_exposed"] is False
    degraded = collection_health(
        now=datetime(2026, 9, 8, 16, tzinfo=timezone.utc),
        init_time=init,
        retrieved_at_utc=None,
        consecutive_missing_runs=2,
    )
    assert degraded["state"] == "degraded"


def test_first_month_eligibility_requires_station_common_times_and_minimum_sample() -> None:
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    samples = [
        VerificationSample(
            valid_time_utc=start + timedelta(hours=index),
            lead_hours=12,
            model_version="3.0.0",
            forecast=20.0 + index / 100,
            observed=19.5 + index / 100,
        )
        for index in range(30)
    ]
    samples.append(
        VerificationSample(
            valid_time_utc=start,
            lead_hours=12,
            model_version="3.0.0",
            forecast=20.0,
            observed=20.0,
            location_id="home",
        )
    )
    result = first_month_verification_eligibility(
        samples,
        common_valid_times=[start + timedelta(hours=index) for index in range(30)],
    )
    assert result["state"] == "first_month_ready"
    assert result["location_id"] == "station_10416"
    assert result["truth_source"] == "DWD WMO 10416"
    assert result["home_accuracy_included"] is False
    assert result["excluded_sample_count"] == 1
    assert result["slices"][0]["n"] == 30
    assert result["slices"][0]["meaningful"] is True
    assert result["slices"][0]["mae"] is not None


def test_quantile_summary_preserves_intervals_and_does_not_invent_precip_probability() -> None:
    summary = summarize_quantile_calibration(
        [
            QuantileSample("temperature_2m", 20.0, 18.0, 19.0, 20.0, 21.0, 22.0),
            QuantileSample("temperature_2m", 23.0, 19.0, 20.0, 21.0, 22.0, 24.0),
        ]
    )
    assert summary["n"] == 2
    assert summary["p10_p90_coverage"] == 1.0
    assert summary["p25_p75_coverage"] == 0.5
    assert summary["precipitation_event_probability_supported"] is False
    precipitation = summarize_quantile_calibration(
        [QuantileSample("precipitation_1h", 0.2, 0.0, 0.0, 0.1, 0.3, 0.5, 60)]
    )
    assert precipitation["accumulation_window_minutes"] == 60
    assert precipitation["precipitation_event_probability_supported"] is False
    with pytest.raises(ValueError):
        QuantileSample("precipitation_1h", 0.2, 0.0, 0.0, 0.1, 0.3, 0.5, 360)


def test_first_month_evidence_is_sanitized_and_publication_fail_closed() -> None:
    evidence = build_first_month_evidence(
        state="first_month_ready",
        model_versions=["3.0.0"],
        run_classes=["interim_48h", "synoptic_360h"],
        lead_bucket_summaries=[{"lead_bucket": "12-24h", "n": 30, "mae": 1.2}],
        freshness_summary={"retrieved_runs": 100, "missing_runs": 2},
        quantile_summaries=[{"variable": "temperature_2m", "n": 30, "p10_p90_coverage": 0.8}],
        notable_miss_summaries=[{"lead_bucket": "12-24h", "absolute_error": 4.0}],
    )
    assert evidence["publication_allowed"] is False
    assert evidence["terms_recheck_required_before_publication"] is True
    assert evidence["weather_warning_authority"] is False
    assert evidence["private_fields_exposed"] is False
    bad = dict(evidence)
    bad["project_id"] = "private-project"
    with pytest.raises(ValueError):
        validate_first_month_evidence(bad)
