from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.rollout import validate_source_package

ROOT = Path(__file__).resolve().parents[1]
WEATHER_SHA = "90c7a1db356ecc9f7b3bf7b557a4884809ca5222"
RPI5_SHA = "14592fd53e6f7f7a6f2f4a2a60f9b9d009134f43"
QUEUE_SHA = "867b9dc82622bef55ffa2cb1a866c5206dfae74f"
PREDECESSOR_SHA = "fb3ac2fc40d1683bb5539b2c0e870256087412cb"
CORRECTED_SOURCE = (
    "ops/deploy/rpi5-main-weather-v7-host-capability-installer-source-v2-trusted-checkout-bootstrap.json"
)
PREDECESSOR_SOURCE = (
    "ops/deploy/rpi5-main-weather-v7-host-capability-installer-source-trusted-checkout-bootstrap.json"
)


def _binding() -> dict[str, object]:
    return json.loads((ROOT / "deploy/rpi5-source-binding.json").read_text())


def test_reconciliation_binds_fresh_source_snapshots_without_deployment_claim() -> None:
    binding = _binding()
    assert binding["status"] == "SOURCE_RECONCILED_RUNTIME_UNPROVEN"
    assert binding["reconciled_on"] == "2026-09-16"
    assert binding["weather_source"]["candidate_sha_at_reconciliation"] == WEATHER_SHA
    assert binding["weather_source"]["exact_sha_ci_summary"] == "7/7_SUCCESS"
    assert binding["weather_source"]["queue_binding_sha"] == QUEUE_SHA
    assert binding["weather_source"]["queue_binding_matches_candidate"] is False
    assert binding["weather_source"]["live_candidate_must_be_resolved_from_current_merged_main"] is True
    assert binding["rpi5_main_source"]["main_sha_at_reconciliation"] == RPI5_SHA
    assert binding["rpi5_main_source"]["required_exact_main_ci_summary"] == "5/5_SUCCESS"
    assert binding["rpi5_main_source"]["sudo_git_trust_correction_pr"] == 587
    assert binding["rpi5_main_source"]["sudo_git_trust_correction_pr_state"] == "MERGED"
    assert (
        binding["rpi5_main_source"]["current_dependency_status"]
        == "SOURCE_READY_HOST_CAPABILITY_CHAIN_PENDING"
    )


def test_queue_remains_fail_closed_and_does_not_grant_live_authority() -> None:
    queue = _binding()["deploy_queue"]
    assert queue["issue"] == 46
    assert queue["observed_state_at_reconciliation"] == "OPEN_STOP_ERROR"
    assert queue["eligibility_only"] is True
    assert queue["grants_live_authority"] is False
    assert queue["current_candidate_binding_status"] == "BLOCKED_QUEUE_STOP_ERROR_AND_SOURCE_SHA_MISMATCH"
    assert queue["failed_authorization_reusable"] is False
    assert queue["queue_refresh_authorized_by_issue_136"] is False


def test_corrected_weather_v7_source_chain_is_canonical_and_predecessor_is_evidence_only() -> None:
    binding = _binding()
    contracts = binding["canonical_current_contracts"]
    predecessor = binding["predecessor_installer_source_checkout"]
    assert contracts["corrected_installer_source_checkout"] == CORRECTED_SOURCE
    assert contracts["host_capability_installer"].endswith(
        "weather-public-runtime-operator-upgrade-v7-host-capability-installer.json"
    )
    assert predecessor["contract"] == PREDECESSOR_SOURCE
    assert predecessor["historical_evidence_only"] is True
    assert predecessor["authority_source"] is False
    assert predecessor["mutation_allowed"] is False
    assert predecessor["cleanup_allowed"] is False


def test_fresh_sanitized_host_observation_exposes_only_gate_relevant_state() -> None:
    observed = _binding()["fresh_sanitized_host_observation"]
    assert observed["manager_checkout_observed"] is True
    assert observed["manager_checkout_matches_current_main"] is False
    assert observed["manager_checkout_clean"] is False
    assert observed["corrected_installer_source_v2_checkout_present"] is False
    assert observed["predecessor_installer_source_checkout_present"] is True
    assert observed["predecessor_installer_source_checkout_clean"] is True
    assert observed["predecessor_installer_source_checkout_sha"] == PREDECESSOR_SHA
    assert observed["operator_upgrade_v7_checkout_present"] is False
    assert observed["weather_v7_privileged_broker_binary_present"] is False
    assert observed["weather_v7_privileged_broker_socket_loaded"] is False
    assert observed["weather_public_port_9180_listening"] is False
    assert observed["point_in_time_only"] is True


def test_source_merge_cannot_claim_host_ready_live_or_deployed() -> None:
    safety = _binding()["source_safety"]
    false_fields = (
        "source_merge_authorizes_live",
        "source_merge_proves_host_ready",
        "source_merge_proves_deployment",
        "corrected_installer_source_v2_checkout_ready",
        "weather_v7_host_capability_installed",
        "weather_v7_operator_upgrade_completed",
        "production_mutation_enabled",
        "production_mutation_started",
        "queue_matches_current_weather_candidate",
    )
    assert all(safety[field] is False for field in false_fields)
    assert safety["fresh_owner_live_authorization_required_for_next_gate"] is True
    assert safety["fresh_sanitized_runtime_baseline_required"] is True
    assert safety["source_only_snapshot_must_not_be_treated_as_live_evidence"] is True


def test_next_owner_gate_is_only_corrected_installer_source_delivery() -> None:
    gate = _binding()["next_owner_live_gate"]
    assert gate["name"] == "DELIVER_CORRECTED_WEATHER_V7_INSTALLER_SOURCE_V2"
    assert gate["available_now"] is True
    assert gate["rpi5_main_sha"] == RPI5_SHA
    assert gate["checkout_identity"] == "RPi5_main-weather-v7-host-capability-installer-source-v2-trusted"
    assert gate["max_operations_each"] == 1
    assert gate["authorizes_host_capability_install"] is False
    assert gate["authorizes_operator_upgrade"] is False
    assert gate["authorizes_weather_rollout"] is False


def test_warning_and_research_authority_are_preserved() -> None:
    safety = _binding()["research_and_safety"]
    assert safety["dwd_severe_weather_warning_authority"] == "DWD"
    assert safety["weathernext3_role"] == "primary_research"
    assert safety["weathernext3_required_for_public_runtime"] is False
    assert safety["weathernext_real_values_fabricated"] is False


def test_runtime_descriptors_reference_binding_and_validator_enforces_it() -> None:
    runtime = json.loads((ROOT / "deploy/runtime-descriptor.json").read_text())
    readiness = json.loads((ROOT / "deploy/rollout-readiness.json").read_text())
    refs = runtime["rollout_readiness"]
    assert refs["public_ui_rollout_reconciliation_descriptor"] == "deploy/public-ui-rollout-reconciliation.json"
    assert runtime["future_rpi5_adapter"]["source_binding_descriptor"] == "deploy/rpi5-source-binding.json"
    trusted = readiness["trusted_boundary_compatibility"]
    assert trusted["source_binding_descriptor"] == "deploy/rpi5-source-binding.json"
    assert trusted["source_merge_proves_deployment"] is False
    assert trusted["source_merge_authorizes_live"] is False
    assert "deploy/rpi5-source-binding.json" in validate_source_package()["validated_files"]
