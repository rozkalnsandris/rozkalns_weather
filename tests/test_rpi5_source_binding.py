from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.rollout import validate_source_package

ROOT = Path(__file__).resolve().parents[1]
WEATHER_SHA = "26f704692c202827206cd370b5f5112864bb3b1b"
RPI5_SHA = "1741cfa076d00a11f609356fee37179226bb9753"
QUEUE_SHA = "867b9dc82622bef55ffa2cb1a866c5206dfae74f"
RPI5_RECOVERY_PR_HEAD = "41d25c46cee40a2d0bee034a44c031b721df1740"
SUCCESSOR = "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json"
LEGACY = "ops/deploy/rpi5-main-weather-public-runtime-trusted-checkout-bootstrap.json"


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
    assert binding["rpi5_main_source"]["exact_main_ci_summary"] == "8/8_SUCCESS"
    assert binding["rpi5_main_source"]["current_dependency_status"] == "BLOCKED_EXTERNAL_SOURCE_RECOVERY"


def test_queue_and_rpi5_recovery_are_explicit_blockers() -> None:
    binding = _binding()
    queue = binding["deploy_queue"]
    rpi = binding["rpi5_main_source"]
    assert queue["issue"] == 46
    assert queue["observed_state_at_reconciliation"] == "OPEN_STOP_ERROR"
    assert queue["eligibility_only"] is True
    assert queue["grants_live_authority"] is False
    assert queue["current_candidate_binding_status"] == "BLOCKED_QUEUE_STOP_ERROR_AND_SOURCE_SHA_MISMATCH"
    assert queue["failed_authorization_reusable"] is False
    assert queue["queue_refresh_authorized_by_issue_127"] is False
    assert rpi["public_operator_recovery_issue"] == 543
    assert rpi["public_operator_recovery_pr"] == 545
    assert rpi["public_operator_recovery_pr_state"] == "OPEN_DRAFT"
    assert rpi["public_operator_recovery_pr_head"] == RPI5_RECOVERY_PR_HEAD
    assert rpi["public_operator_recovery_pr_validate"] == "FAILURE"


def test_successor_checkout_is_canonical_and_legacy_is_evidence_only() -> None:
    binding = _binding()
    assert binding["canonical_current_contracts"]["successor_trusted_checkout"] == SUCCESSOR
    assert binding["legacy_checkout"]["contract"] == LEGACY
    assert binding["legacy_checkout"]["historical_evidence_only"] is True
    assert binding["legacy_checkout"]["authority_source"] is False
    assert binding["legacy_checkout"]["mutation_allowed"] is False
    assert binding["legacy_checkout"]["cleanup_allowed"] is False


def test_source_merge_cannot_claim_host_ready_live_or_deployed() -> None:
    safety = _binding()["source_safety"]
    false_fields = (
        "source_merge_authorizes_live",
        "source_merge_proves_host_ready",
        "source_merge_proves_deployment",
        "operator_host_installed",
        "helper_installation_enabled",
        "operator_installation_enabled",
        "privileged_install_invocation_enabled",
        "production_mutation_enabled",
        "production_mutation_started",
    )
    assert all(safety[field] is False for field in false_fields)
    assert safety["fresh_human_composite_strict_live_authorization_required"] is True
    assert safety["fresh_sanitized_runtime_baseline_required"] is True
    assert safety["operator_installer_bridge_active"] is False
    assert safety["queue_matches_current_weather_candidate"] is False
    assert safety["source_only_snapshot_must_not_be_treated_as_live_evidence"] is True


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
    assert refs["current_source_assessment"] == "BLOCKED_EXTERNAL_RPI5_SOURCE_AND_QUEUE_RECOVERY"
    assert runtime["future_rpi5_adapter"]["source_binding_descriptor"] == "deploy/rpi5-source-binding.json"
    trusted = readiness["trusted_boundary_compatibility"]
    assert trusted["source_binding_descriptor"] == "deploy/rpi5-source-binding.json"
    assert trusted["canonical_successor_trusted_checkout_contract"] == SUCCESSOR
    assert trusted["legacy_trusted_checkout_is_current_authority"] is False
    assert trusted["operator_source_ready"] is True
    assert trusted["operator_host_installed"] is False
    assert trusted["source_merge_proves_deployment"] is False
    assert trusted["source_merge_authorizes_live"] is False
    assert "deploy/rpi5-source-binding.json" in validate_source_package()["validated_files"]
