from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.rollout import validate_source_package

ROOT = Path(__file__).resolve().parents[1]
WEATHER_SHA = "7b188d56ef083f60289bf34297199a42f13e1048"
RPI5_SHA = "2672451d1f3ddc6cffcc70a3627c6b758db8abe0"
SUCCESSOR = "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json"
LEGACY = "ops/deploy/rpi5-main-weather-public-runtime-trusted-checkout-bootstrap.json"


def _binding() -> dict[str, object]:
    return json.loads((ROOT / "deploy/rpi5-source-binding.json").read_text())


def test_reconciliation_binds_exact_source_snapshots_without_deployment_claim() -> None:
    binding = _binding()
    assert binding["status"] == "SOURCE_RECONCILED_RUNTIME_UNPROVEN"
    assert binding["weather_source"]["candidate_sha_at_reconciliation"] == WEATHER_SHA
    assert binding["weather_source"]["queue_binding_sha"] == "52d3fd0ff946d3d5a0e1379f6c4362bf834a1aa9"
    assert binding["weather_source"]["queue_binding_matches_candidate"] is False
    assert binding["rpi5_main_source"]["main_sha_at_reconciliation"] == RPI5_SHA
    assert binding["rpi5_main_source"]["exact_main_validate_run"] == 34571359393
    assert binding["rpi5_main_source"]["issue_462"] == "DONE_SOURCE_ONLY_OPERATOR_INSTALLER_BRIDGE_INACTIVE"
    assert binding["deploy_queue"]["issue"] == 46
    assert binding["deploy_queue"]["eligibility_only"] is True
    assert binding["deploy_queue"]["grants_live_authority"] is False
    assert binding["deploy_queue"]["current_candidate_binding_status"] == "BLOCKED_SOURCE_SHA_MISMATCH"


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


def test_warning_and_research_authority_are_preserved() -> None:
    safety = _binding()["research_and_safety"]
    assert safety["dwd_severe_weather_warning_authority"] == "DWD"
    assert safety["weathernext3_role"] == "primary_research"
    assert safety["weathernext3_required_for_public_runtime"] is False
    assert safety["weathernext_real_values_fabricated"] is False


def test_runtime_descriptors_reference_binding_and_validator_enforces_it() -> None:
    runtime = json.loads((ROOT / "deploy/runtime-descriptor.json").read_text())
    readiness = json.loads((ROOT / "deploy/rollout-readiness.json").read_text())
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
