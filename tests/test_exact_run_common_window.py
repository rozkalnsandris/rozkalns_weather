from __future__ import annotations

import json
from pathlib import Path


def _contract() -> dict[str, object]:
    return json.loads(Path("deploy/exact-run-common-window.json").read_text(encoding="utf-8"))


def test_exact_run_common_window_is_fixed_complete_and_station_bound() -> None:
    contract = _contract()
    assert contract["status"] == "SELECTED_VERIFIED_FIXED_WINDOW"
    assert contract["decision_issue"] == 159
    assert contract["parent_issue"] == 148
    assert contract["benchmark_location_id"] == "station_05480"
    assert contract["truth_station_id"] == "05480"
    window = contract["selected_window"]
    assert window == {
        "start_date": "2026-08-13",
        "end_date": "2026-08-26",
        "inclusive_days": 14,
        "fixed_non_rolling": True,
        "run_hours_utc": [0, 6, 12, 18],
        "runs_per_model": 56,
    }
    assert set(contract["models"]) == {"icon_d2", "ecmwf_ifs", "ecmwf_aifs"}
    assert all(item["exact_run_availability_proven"] is True for item in contract["models"].values())
    assert all(item["full_horizon_boundary_proven"] is True for item in contract["models"].values())


def test_public_probe_evidence_closes_every_run_and_horizon_gap() -> None:
    evidence = _contract()["public_probe_evidence"]
    assert evidence["primary_api_or_model_unavailable_failures"] == 0
    assert evidence["primary_non_pass_class"] == "SSL_HANDSHAKE_TRANSPORT_TIMEOUT_ONLY"
    assert evidence["gap_closure_expected"] == 14
    assert evidence["gap_closure_passed"] == 14
    assert evidence["gap_closure_transport_retry_only"] is True
    assert evidence["gap_closure_api_or_model_error_retried"] is False
    assert evidence["combined_exact_run_required_variable_expected"] == 168
    assert evidence["combined_exact_run_required_variable_passes"] == 168
    assert evidence["combined_full_horizon_boundary_expected"] == 24
    assert evidence["combined_full_horizon_boundary_passes"] == 24
    assert evidence["gap_closure_fingerprint"] == "aa8bd30174a660ab5ae38f5202925eb2622521a5bf52485208fc499e8284bbf2"


def test_truth_retention_legacy_and_authority_boundaries_remain_fail_closed() -> None:
    contract = _contract()
    retention = contract["retention_evidence"]
    assert retention["open_meteo_data_run_public_retention"] == "3 months"
    assert retention["oldest_selected_init_age_days"] == 39
    assert retention["selection_has_material_margin_from_retention_edge"] is True
    assert retention["cross_model_retention_inference_used"] is False
    assert retention["each_model_exact_run_probed_separately"] is True
    truth = contract["truth_alignment"]
    assert truth["source_authority"] == "DWD"
    assert truth["source_verified_truth_end"] == "2026-09-10"
    assert truth["latest_aifs_requested_horizon_end_utc"] == "2026-09-10T18:00:00Z"
    assert truth["requested_horizons_within_verified_truth"] is True
    legacy = contract["preserved_legacy_evidence"]
    assert legacy["decision_contract"] == "deploy/icon-d2-exact-run-transport-decision.json"
    assert legacy["icon_d2_completed_prefix_runs"] == 279
    assert legacy["existing_rows_preserved"] is True
    assert legacy["existing_rows_rewritten"] is False
    authority = contract["authority"]
    assert authority["production_data_authority_granted"] is False
    assert authority["source_merge_authorizes_production_write"] is False
    assert authority["live_resume_authorized"] is False
