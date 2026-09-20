from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.rollout import validate_source_package

ROOT = Path(__file__).resolve().parents[1]
WEATHER_BASE_SHA = "9e903b0e1d129856c4b1533b48487b7f5c36737d"
RPI5_SHA = "84e129909831bd8111c4f4c1f6618b7fff2a803b"


def _binding() -> dict[str, object]:
    return json.loads((ROOT / "deploy/rpi5-source-binding.json").read_text())


def test_reconciliation_tracks_current_source_lineage_without_runtime_claim() -> None:
    binding = _binding()
    assert binding["status"] == "SOURCE_RECONCILED_RUNTIME_UNPROVEN"
    assert binding["reconciled_on"] == "2026-09-19"
    weather = binding["weather_source"]
    assert weather["candidate_sha_at_reconciliation"] == WEATHER_BASE_SHA
    assert weather["snapshot_role"] == "pre_issue_140_main_anchor_only"
    assert weather["final_live_candidate_must_be_resolved_from_current_merged_main"] is True
    assert weather["source_sha_is_runtime_proof"] is False
    rpi = binding["rpi5_main_source"]
    assert rpi["main_sha_at_reconciliation"] == RPI5_SHA
    assert rpi["stale_v7_next_gate_superseded"] is True
    assert rpi["source_state_proves_host_installation"] is False
    assert rpi["source_state_proves_deployment"] is False
    assert rpi["fresh_current_main_and_ci_required_before_live"] is True
    lifecycle = binding["lifecycle"]
    assert lifecycle["current_ordinary_release_role"] == "LEGACY_SUPERSEDED"
    assert lifecycle["superseded_by"] == "SIMPLE_DEPLOY_V1"
    assert lifecycle["generic_rpi5_deployer_source_sha"] == "ff20fcf64ba62c95e5f15eeb481c3c66bb5c9708"


def test_queue_handoff_requires_final_merged_weather_sha_and_grants_no_live_authority() -> None:
    queue = _binding()["deploy_queue"]
    assert queue["issue"] == 46
    assert queue["observed_state_at_reconciliation"] == "BLOCKED_WEATHER_SOURCE_HANDOFF_RECONCILIATION"
    assert queue["final_merged_weather_sha_must_be_bound_after_merge"] is True
    assert queue["fresh_queue_revalidation_required_before_live"] is True
    assert queue["eligibility_only"] is True
    assert queue["grants_live_authority"] is False
    assert queue["queue_refresh_authorized_by_this_source_issue"] is False
    assert queue["historical_or_failed_authorization_reusable"] is False


def test_static_source_binding_contains_no_point_in_time_host_observation_or_stale_v7_gate() -> None:
    binding = _binding()
    assert "fresh_sanitized_host_observation" not in binding
    assert "next_owner_live_gate" not in binding
    lineage = binding["control_plane_lineage"]
    assert lineage["runtime_installation_state_encoded_as_source_authority"] is False
    assert lineage["fresh_operator_installation_proof_required_by_jit"] is True
    assert lineage["fresh_runtime_baseline_required_by_jit"] is True


def test_v1_compatibility_sentinels_are_explicitly_non_authoritative() -> None:
    safety = _binding()["source_safety"]
    compatibility_fields = (
        "operator_host_installed",
        "helper_installation_enabled",
        "operator_installation_enabled",
        "privileged_install_invocation_enabled",
        "production_mutation_enabled",
        "production_mutation_started",
    )
    assert all(safety[field] is False for field in compatibility_fields)
    assert safety["compatibility_sentinels_are_current_host_observations"] is False
    assert safety["compatibility_sentinels_grant_or_deny_runtime_capability"] is False
    assert safety["operator_installation_proof_required_via_fresh_jit_evidence"] is True
    assert safety["fresh_sanitized_runtime_baseline_required"] is True
    assert safety["source_only_snapshot_must_not_be_treated_as_live_evidence"] is True


def test_rollout_readiness_does_not_encode_current_operator_host_state() -> None:
    readiness = json.loads((ROOT / "deploy/rollout-readiness.json").read_text())
    trusted = readiness["trusted_boundary_compatibility"]
    assert "operator_host_installed" not in trusted
    assert "operator_installer_bridge_status" not in trusted
    assert trusted["operator_installation_state_is_source_authoritative"] is False
    assert trusted["operator_installation_proof_required_via_fresh_jit"] is True
    assert trusted["fresh_runtime_baseline_required_via_jit"] is True


def test_runtime_descriptor_points_to_post_merge_queue_and_jit_reconciliation() -> None:
    runtime = json.loads((ROOT / "deploy/runtime-descriptor.json").read_text())
    assessment = runtime["rollout_readiness"]["current_source_assessment"]
    assert assessment == "SIMPLE_DEPLOY_V1_CANARY_SOURCE_READY_CUTOVER_NOT_ACTIVE"
    assert "BLOCKED_EXTERNAL_RPI5_SOURCE_AND_QUEUE_RECOVERY" not in json.dumps(runtime)


def test_post_merge_sequence_keeps_queue_jit_and_live_authority_separate() -> None:
    reconciliation = _binding()["post_merge_reconciliation"]
    assert reconciliation["required_order"][0] == "resolve_final_merged_weather_main_sha"
    assert reconciliation["required_order"][-1] == (
        "only_if_jit_pass_request_new_bounded_composite_strict_live_authorization"
    )
    assert reconciliation["queue_ready_transition_authorized_by_issue_140"] is False
    assert reconciliation["live_authorization_created_by_issue_140"] is False
    assert reconciliation["source_merge_is_not_queue_ready_transition"] is True


def test_warning_and_research_authority_are_preserved() -> None:
    safety = _binding()["research_and_safety"]
    assert safety["dwd_severe_weather_warning_authority"] == "DWD"
    assert safety["weathernext3_role"] == "primary_research"
    assert safety["weathernext3_required_for_public_runtime"] is False
    assert safety["weathernext_real_values_fabricated"] is False


def test_source_package_validator_accepts_reconciled_handoff() -> None:
    result = validate_source_package()
    assert result["ok"] is True
    assert "deploy/rpi5-source-binding.json" in result["validated_files"]
