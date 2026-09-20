from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEATHER_BASE_SHA = "9e903b0e1d129856c4b1533b48487b7f5c36737d"
RPI5_SHA = "84e129909831bd8111c4f4c1f6618b7fff2a803b"


def _reconciliation() -> dict[str, object]:
    return json.loads((ROOT / "deploy/public-ui-rollout-reconciliation.json").read_text())


def test_public_ui_source_handoff_is_reconciled_without_live_claim() -> None:
    payload = _reconciliation()
    assert payload["contract"] == "rozkalns-weather.public-ui-rollout-reconciliation.v1"
    assert payload["issue"] == 136
    assert payload["runtime_mode"] == "public-only"
    assert payload["outcome"] == "SIMPLE_DEPLOY_V1_CANARY_SOURCE_READY_CUTOVER_REQUIRED"
    simple = payload["simple_deploy_v1"]
    assert simple["role"] == "CURRENT_ORDINARY_APPLICATION_RELEASE_ARCHITECTURE"
    assert simple["shared_workflow_sha"] == "e05ed760791a127c7c9628696806ef39c9fe329c"
    assert simple["generic_rpi5_deployer_source_sha"] == "ff20fcf64ba62c95e5f15eeb481c3c66bb5c9708"
    assert payload["weather"]["reconciliation_anchor_sha"] == WEATHER_BASE_SHA
    assert payload["weather"]["ui_source_implemented"] is True
    assert payload["weather"]["ui_surfaces"] == ["Overview", "Models", "Accuracy", "Warnings-Radar"]
    assert payload["weather"]["source_sha_is_runtime_proof"] is False
    assert payload["safety"]["source_merge_authorizes_live"] is False
    assert payload["safety"]["source_merge_proves_deployment"] is False
    assert payload["safety"]["source_merge_proves_operator_installation"] is False


def test_rpi5_lineage_is_current_but_runtime_proof_is_deferred_to_jit() -> None:
    rpi = _reconciliation()["rpi5_main"]
    assert rpi["observed_main_sha"] == RPI5_SHA
    assert rpi["required_exact_main_ci"] == "Validate-FAST-LANE-GITHUB-ONLY-SUCCESS"
    assert rpi["weather_v9_recovery_control_plane_closed_before_reconciliation"] is True
    assert rpi["stale_v7_next_gate_superseded"] is True
    assert rpi["source_snapshot_only"] is True
    assert rpi["source_state_is_operator_installation_proof"] is False
    assert rpi["source_state_is_deployment_proof"] is False
    assert rpi["fresh_current_main_and_ci_required_before_jit"] is True


def test_queue_requires_final_merged_weather_sha_and_is_eligibility_only() -> None:
    queue = _reconciliation()["deploy_queue"]
    assert queue["issue"] == 46
    assert queue["observed_state"] == "BLOCKED_WEATHER_SOURCE_HANDOFF_RECONCILIATION"
    assert queue["final_merged_weather_sha_must_be_bound_after_merge"] is True
    assert queue["eligibility_only"] is True
    assert queue["grants_live_authority"] is False
    assert queue["refresh_authorized_by_issue_136"] is False
    assert queue["refresh_authorized_by_issue_140"] is False
    assert queue["ready_for_final_candidate_proven_by_source"] is False
    assert queue["lifecycle_role"] == "LEGACY_SUPERSEDED_FOR_ORDINARY_APPLICATION_RELEASES"
    assert queue["required_by_current_ordinary_release"] is False


def test_static_reconciliation_has_no_point_in_time_host_snapshot_or_live_gate() -> None:
    payload = _reconciliation()
    assert "fresh_read_only_host_observation" not in payload
    assert "next_owner_live_gate" not in payload
    jit = payload["jit_runtime_evidence"]
    assert jit["fresh_operator_installation_proof_required"] is True
    assert jit["fresh_sanitized_runtime_baseline_required"] is True
    assert jit["baseline_token_exact_match_required"] is True
    assert jit["source_snapshot_may_not_substitute"] is True


def test_required_external_sequence_uses_simple_deploy_cutover_not_legacy_queue() -> None:
    sequence = _reconciliation()["required_external_sequence"]
    assert sequence[0] == "complete Weather #142 source adoption and guarded merge"
    assert "SIMPLE-DEPLOY cutover" in sequence[1]
    assert "immutable digest" in sequence[2]
    assert "schema and public corpus bootstrap" in sequence[3]
    assert "ops-workflows issue 46" not in " ".join(sequence)


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
