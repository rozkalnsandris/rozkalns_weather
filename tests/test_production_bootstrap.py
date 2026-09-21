from __future__ import annotations

from datetime import date, timedelta
import json

import pytest

from rozkalns_weather.cli import main as cli_main
from rozkalns_weather.production_bootstrap import (
    FORECAST_TRANSPORT_BLOCK_REASON,
    FORECAST_TRANSPORT_DECISION_CONTRACT,
    build_production_bootstrap_plan,
    evaluate_resume_evidence,
)


def _plan():
    return build_production_bootstrap_plan(
        source_sha="a" * 40,
        start=date(2026, 4, 2),
        end=date(2026, 4, 15),
        recovery_decision="verified_backup_available",
    )


def _runs(start: date, end: date) -> list[str]:
    result: list[str] = []
    cursor = start
    while cursor <= end:
        for hour in (0, 6, 12, 18):
            result.append(f"{cursor.isoformat()}T{hour:02d}:00:00Z")
        cursor += timedelta(days=1)
    return result


def _complete_evidence() -> dict[str, object]:
    plan = _plan()
    runs = _runs(date(2026, 4, 2), date(2026, 4, 15))

    def model_state() -> dict[str, object]:
        return {
            "location_id": "station_05480",
            "completed_runs": list(runs),
            "revision_drift_runs": [],
            "unexpected_runs": [],
            "database_ahead_of_checkpoint": False,
        }

    return {
        "bootstrap_fingerprint": plan["bootstrap_fingerprint"],
        "recovery_decision": "verified_backup_available",
        "schema": {"state": "ready", "implicit_migration_performed": False},
        "truth": {
            "station_id": "05480",
            "location_id": "station_05480",
            "variables": list(plan["identity"]["truth_variables"]),
            "completed_chunks": ["2026-04-02..2026-04-15"],
            "database_ahead_of_checkpoint": False,
        },
        "forecasts": {
            "icon_d2": model_state(),
            "ecmwf_ifs": model_state(),
            "ecmwf_aifs": model_state(),
        },
        "integrity": {"ok": True},
    }


def test_plan_freezes_bounds_scope_and_fails_closed_on_icon_d2_transport() -> None:
    plan = _plan()
    assert plan["inclusive_days"] == 14
    assert plan["truth_chunk_count"] == 1
    assert plan["forecast_run_count_per_model"] == 56
    assert plan["identity"]["models"] == ["icon_d2", "ecmwf_ifs", "ecmwf_aifs"]
    assert plan["identity"]["run_hours_utc"] == [0, 6, 12, 18]
    assert plan["identity"]["benchmark_location_id"] == "station_05480"
    assert plan["identity"]["truth_station_id"] == "05480"
    assert plan["identity"]["icon_d2_exact_run_transport_status"] == FORECAST_TRANSPORT_BLOCK_REASON
    assert plan["state"] == "BLOCKED_SOURCE_CAPABILITY"
    assert plan["block_reasons"] == [FORECAST_TRANSPORT_BLOCK_REASON]
    assert plan["truth_transport"]["source_authority"] == "DWD"
    assert plan["truth_transport"]["transport"] == "DWD CDC Open Data"
    assert plan["truth_transport"]["station_id"] == "05480"
    assert plan["truth_transport"]["location_id"] == "station_05480"
    assert plan["truth_transport"]["historical_capability"] == "verified_frozen_window_product_coverage"
    assert plan["truth_transport"]["coverage_revalidation_required_before_live"] is True
    assert plan["truth_transport"]["live_backfill_allowed"] is False
    assert plan["forecast_colocation"] == {
        "location_id": "station_05480",
        "models": ["icon_d2", "ecmwf_ifs", "ecmwf_aifs"],
        "exact_public_station_coordinates": True,
        "nearest_station_fallback_allowed": False,
    }
    assert plan["forecast_transport"]["icon_d2"] == {
        "transport": "Open-Meteo Single Runs API",
        "status": FORECAST_TRANSPORT_BLOCK_REASON,
        "decision_contract": FORECAST_TRANSPORT_DECISION_CONTRACT,
        "exact_init_required": True,
        "skip_ahead_allowed": False,
        "live_backfill_allowed": False,
    }
    assert plan["schema_init_explicit_only"] is True
    assert plan["production_data_authority_granted"] is False


def test_plan_rejects_unverified_window_and_unsupported_recovery() -> None:
    with pytest.raises(ValueError, match="source-verified only through 2026-09-10"):
        build_production_bootstrap_plan(
            source_sha="a" * 40,
            start=date(2026, 4, 2),
            end=date(2026, 10, 1),
            recovery_decision="verified_backup_available",
        )
    with pytest.raises(ValueError, match="unsupported recovery"):
        build_production_bootstrap_plan(
            source_sha="a" * 40,
            start=date(2026, 4, 2),
            end=date(2026, 4, 3),
            recovery_decision="auto_restore",
        )


def test_complete_evidence_cannot_override_source_capability_block() -> None:
    result = evaluate_resume_evidence(_plan(), _complete_evidence())
    assert result["state"] == "BLOCKED"
    assert result["block_reasons"] == [FORECAST_TRANSPORT_BLOCK_REASON]
    assert result["production_data_authority_granted"] is False


def test_partial_duplicate_revision_and_interrupted_states_fail_closed() -> None:
    plan = _plan()
    partial = _complete_evidence()
    partial["forecasts"]["icon_d2"]["completed_runs"] = partial["forecasts"]["icon_d2"]["completed_runs"][:-1]
    assert "PARTIAL_BOOTSTRAP_INCOMPLETE" in evaluate_resume_evidence(plan, partial)["block_reasons"]

    duplicate = _complete_evidence()
    duplicate["forecasts"]["ecmwf_ifs"]["completed_runs"].append(
        duplicate["forecasts"]["ecmwf_ifs"]["completed_runs"][-1]
    )
    assert "ECMWF_IFS_CHECKPOINT_DUPLICATE" in evaluate_resume_evidence(plan, duplicate)["block_reasons"]

    revision = _complete_evidence()
    revision["forecasts"]["ecmwf_aifs"]["revision_drift_runs"] = ["2026-04-02T00:00:00Z"]
    assert "ECMWF_AIFS_REVISION_DRIFT" in evaluate_resume_evidence(plan, revision)["block_reasons"]

    interrupted = _complete_evidence()
    interrupted["truth"]["database_ahead_of_checkpoint"] = True
    assert "INTERRUPTED_CHECKPOINT_RESUME_REQUIRED" in evaluate_resume_evidence(plan, interrupted)["block_reasons"]


def test_station_location_and_variable_scope_mismatch_fail_closed() -> None:
    evidence = _complete_evidence()
    evidence["truth"]["station_id"] = "10416"
    evidence["truth"]["location_id"] = "station_10416"
    evidence["truth"]["variables"] = ["temperature_2m"]
    evidence["forecasts"]["icon_d2"]["location_id"] = "station_10416"
    reasons = evaluate_resume_evidence(_plan(), evidence)["block_reasons"]
    assert "TRUTH_STATION_MISMATCH" in reasons
    assert "TRUTH_LOCATION_MISMATCH" in reasons
    assert "TRUTH_VARIABLE_SCOPE_MISMATCH" in reasons
    assert "ICON_D2_LOCATION_MISMATCH" in reasons


def test_resume_evidence_rejects_private_fields() -> None:
    evidence = _complete_evidence()
    evidence["database_path"] = "/private/path/weather.db"
    with pytest.raises(ValueError, match="forbidden private field"):
        evaluate_resume_evidence(_plan(), evidence)


def test_production_bootstrap_plan_cli_is_runtime_independent_and_source_blocked(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "rozkalns-weather",
            "production-bootstrap-plan",
            "--source-sha",
            "d" * 40,
            "--start",
            "2026-04-02",
            "--end",
            "2026-04-03",
            "--recovery-decision",
            "owner_accepts_proceeding_without_prewrite_backup",
        ],
    )
    cli_main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "BLOCKED_SOURCE_CAPABILITY"
    assert payload["block_reasons"] == [FORECAST_TRANSPORT_BLOCK_REASON]
    assert payload["production_data_authority_granted"] is False
