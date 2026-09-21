from __future__ import annotations

from datetime import date, timedelta
import json

import pytest

from rozkalns_weather.cli import main as cli_main
from rozkalns_weather.production_bootstrap import (
    CHECKPOINT_NAMESPACE,
    FIXED_WINDOW_END,
    FIXED_WINDOW_START,
    FORECAST_TRANSPORT_DECISION_CONTRACT,
    FORECAST_TRANSPORT_STATUS,
    build_production_bootstrap_plan,
    evaluate_resume_evidence,
)


def _plan():
    return build_production_bootstrap_plan(
        source_sha="a" * 40,
        start=FIXED_WINDOW_START,
        end=FIXED_WINDOW_END,
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
    runs = _runs(FIXED_WINDOW_START, FIXED_WINDOW_END)

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
            "completed_chunks": ["2026-08-13..2026-08-26"],
            "database_ahead_of_checkpoint": False,
        },
        "forecasts": {
            "icon_d2": model_state(),
            "ecmwf_ifs": model_state(),
            "ecmwf_aifs": model_state(),
        },
        "integrity": {"ok": True},
    }


def test_plan_pins_verified_fixed_window_and_new_namespace() -> None:
    plan = _plan()
    assert plan["state"] == "SOURCE_READY_REQUIRES_EXACT_LIVE_DATA_AUTHORITY"
    assert plan["block_reasons"] == []
    assert plan["inclusive_days"] == 14
    assert plan["truth_chunk_count"] == 1
    assert plan["forecast_run_count_per_model"] == 56
    assert plan["identity"]["start_date"] == "2026-08-13"
    assert plan["identity"]["end_date"] == "2026-08-26"
    assert plan["identity"]["window_kind"] == "fixed_non_rolling"
    assert plan["identity"]["models"] == ["icon_d2", "ecmwf_ifs", "ecmwf_aifs"]
    assert plan["identity"]["run_hours_utc"] == [0, 6, 12, 18]
    assert plan["identity"]["benchmark_location_id"] == "station_05480"
    assert plan["identity"]["truth_station_id"] == "05480"
    assert plan["identity"]["exact_run_transport_status"] == FORECAST_TRANSPORT_STATUS
    assert plan["identity"]["exact_run_transport_decision_contract"] == FORECAST_TRANSPORT_DECISION_CONTRACT
    assert plan["identity"]["checkpoint_namespace"] == CHECKPOINT_NAMESPACE
    assert plan["identity"]["pre_159_fingerprint_reusable"] is False
    assert plan["production_data_authority_granted"] is False
    for model in ("icon_d2", "ecmwf_ifs", "ecmwf_aifs"):
        transport = plan["forecast_transport"][model]
        assert transport["status"] == FORECAST_TRANSPORT_STATUS
        assert transport["exact_init_required"] is True
        assert transport["full_horizon_required"] is True
        assert transport["skip_ahead_allowed"] is False
        assert transport["live_backfill_allowed"] is False
    assert plan["historical_evidence"]["existing_rows_preserved"] is True
    assert plan["historical_evidence"]["legacy_checkpoint_reusable_for_fixed_window"] is False


def test_plan_rejects_old_rolling_or_partial_windows() -> None:
    for start, end in (
        (date(2026, 4, 2), date(2026, 9, 10)),
        (date(2026, 8, 14), date(2026, 8, 26)),
        (date(2026, 8, 13), date(2026, 8, 25)),
    ):
        with pytest.raises(ValueError, match="exact fixed common window"):
            build_production_bootstrap_plan(
                source_sha="a" * 40,
                start=start,
                end=end,
                recovery_decision="verified_backup_available",
            )


def test_complete_evidence_passes_without_granting_live_authority() -> None:
    result = evaluate_resume_evidence(_plan(), _complete_evidence())
    assert result["state"] == "PASS"
    assert result["block_reasons"] == []
    assert result["checkpoint_namespace"] == CHECKPOINT_NAMESPACE
    assert result["production_data_authority_granted"] is False
    assert result["automatic_retry_allowed"] is False


def test_stale_fingerprint_and_partial_or_revision_states_fail_closed() -> None:
    plan = _plan()
    stale = _complete_evidence()
    stale["bootstrap_fingerprint"] = "0" * 64
    assert "BOOTSTRAP_FINGERPRINT_MISMATCH" in evaluate_resume_evidence(plan, stale)["block_reasons"]

    partial = _complete_evidence()
    partial["forecasts"]["icon_d2"]["completed_runs"] = partial["forecasts"]["icon_d2"]["completed_runs"][:-1]
    assert "PARTIAL_BOOTSTRAP_INCOMPLETE" in evaluate_resume_evidence(plan, partial)["block_reasons"]

    revision = _complete_evidence()
    revision["forecasts"]["ecmwf_aifs"]["revision_drift_runs"] = ["2026-08-13T00:00:00Z"]
    assert "ECMWF_AIFS_REVISION_DRIFT" in evaluate_resume_evidence(plan, revision)["block_reasons"]


def test_station_location_variable_and_private_scope_fail_closed() -> None:
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

    private = _complete_evidence()
    private["database_path"] = "/private/path/weather.db"
    with pytest.raises(ValueError, match="forbidden private field"):
        evaluate_resume_evidence(_plan(), private)


def test_production_bootstrap_plan_cli_is_source_ready_but_not_live_authority(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "rozkalns-weather",
            "production-bootstrap-plan",
            "--source-sha",
            "d" * 40,
            "--start",
            "2026-08-13",
            "--end",
            "2026-08-26",
            "--recovery-decision",
            "owner_accepts_proceeding_without_prewrite_backup",
        ],
    )
    cli_main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "SOURCE_READY_REQUIRES_EXACT_LIVE_DATA_AUTHORITY"
    assert payload["block_reasons"] == []
    assert payload["checkpoint_namespace"] == CHECKPOINT_NAMESPACE
    assert payload["production_data_authority_granted"] is False
