from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _reconciliation() -> dict[str, object]:
    return json.loads((ROOT / "deploy/public-ui-rollout-reconciliation.json").read_text())


def test_public_ui_source_is_ready_but_live_is_not_claimed() -> None:
    payload = _reconciliation()
    assert payload["contract"] == "rozkalns-weather.public-ui-rollout-reconciliation.v1"
    assert payload["runtime_mode"] == "public-only"
    assert payload["weather"]["ui_source_implemented"] is True
    assert payload["weather"]["ui_surfaces"] == ["Overview", "Models", "Accuracy", "Warnings-Radar"]
    assert payload["outcome"] == "BLOCKED_EXTERNAL_RPI5_SOURCE_AND_QUEUE_RECOVERY"
    assert payload["next_owner_live_gate"]["available_now"] is False
    assert payload["safety"]["source_merge_authorizes_live"] is False
    assert payload["safety"]["source_merge_proves_deployment"] is False
    assert payload["safety"]["production_mutation_started"] is False


def test_rpi5_and_queue_blockers_are_exact_and_fail_closed() -> None:
    payload = _reconciliation()
    rpi = payload["rpi5_main"]
    queue = payload["deploy_queue"]
    assert rpi["public_operator_recovery_issue"] == 543
    assert rpi["canonical_pr"] == 545
    assert rpi["canonical_pr_state"] == "OPEN_DRAFT"
    assert rpi["canonical_pr_validate"] == "FAILURE"
    assert rpi["source_dependency_satisfied"] is False
    assert queue["issue"] == 46
    assert queue["observed_state"] == "OPEN_STOP_ERROR"
    assert queue["matches_weather_anchor"] is False
    assert queue["ready_for_current_candidate"] is False
    assert queue["grants_live_authority"] is False
    blockers = set(payload["blockers"])
    assert "RPI5_MAIN_ISSUE_543_CANONICAL_PR_545_NOT_READY" in blockers
    assert "OPS_WORKFLOWS_46_STOP_ERROR" in blockers
    assert "FRESH_STRICT_LIVE_AUTHORIZATION_REQUIRED_AFTER_EXTERNAL_RECOVERY" in blockers


def test_public_ui_does_not_depend_on_private_weathernext_or_home_coordinates() -> None:
    payload = _reconciliation()
    runtime = payload["public_runtime_contract"]
    safety = payload["safety"]
    assert runtime["weathernext_required"] is False
    assert runtime["home_coordinates_required"] is False
    assert runtime["dwd_warning_authority"] == "DWD"
    assert safety["weathernext_private_access_blocks_public_ui"] is False
    assert safety["home_coordinates_block_public_ui"] is False
    assert safety["weathernext_real_values_fabricated"] is False


def test_live_candidate_and_runtime_baseline_must_be_refreshed_after_external_recovery() -> None:
    payload = _reconciliation()
    assert payload["weather"]["live_candidate_rule"].startswith("resolve exact current merged main")
    assert payload["fresh_read_only_host_observation"]["runtime_state_is_point_in_time_only"] is True
    sequence = payload["required_external_sequence"]
    assert sequence[-2].startswith("run the existing first-public-rollout JIT preflight")
    assert sequence[-1] == "only then request one exact Composite STRICT LIVE authorization"
