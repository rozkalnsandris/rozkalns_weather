from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest

from rozkalns_weather.cli import main as cli_main
from rozkalns_weather.rollout_live_preflight import evaluate_first_public_rollout_preflight

ROOT = Path(__file__).resolve().parents[1]
WEATHER_SHA = "d" * 40
RPI5_SHA = "e" * 40
TARGET = "rozkalns-weather-public-rpi5"


def _contract() -> dict[str, object]:
    return json.loads((ROOT / "deploy/first-public-rollout-preflight.json").read_text())


def _valid_evidence() -> dict[str, object]:
    contract = _contract()
    rpi = contract["rpi5_contracts"]
    budgets = contract["mutation_budgets"]
    bootstrap = contract["bootstrap"]
    return {
        "weather": {
            "candidate_sha": WEATHER_SHA,
            "current_main_sha": WEATHER_SHA,
            "exact_sha_ci": {"governance": "SUCCESS", "backend_tests": "SUCCESS"},
        },
        "rpi5_main": {
            "candidate_sha": RPI5_SHA,
            "current_main_sha": RPI5_SHA,
            "exact_sha_ci": {"validate": "SUCCESS"},
        },
        "queue": {
            "repository": "rozkalnsandris/ops-workflows",
            "issue": 46,
            "state": "OPEN_READY",
            "source_sha": WEATHER_SHA,
            "target_alias": TARGET,
            "eligibility_only": True,
            "grants_live_authority": False,
        },
        "runtime": {
            "host_alias": "rpi5",
            "target_alias": TARGET,
            "baseline_token": "baseline-v1:abc",
            "expected_baseline_token": "baseline-v1:abc",
            "operator": {"installed": True, "verified": True, "artifact_count": 23},
        },
        "contract_identities": {
            field: rpi[field]
            for field in (
                "composite_operator",
                "operator_install",
                "helper_install",
                "composite_authority",
                "execution",
                "successor_trusted_checkout",
            )
        },
        "bootstrap": {
            "start_date": bootstrap["start_date"],
            "end_date": bootstrap["end_date"],
            "models": bootstrap["models"],
            "run_hours_utc": bootstrap["run_hours_utc"],
            "recovery_decision": "verified_backup_available",
        },
        "authorization": {
            "present": True,
            "schema": "rozkalns.weather-composite-live-auth.v1",
            "ttl_valid": True,
            "replay_state": "AVAILABLE",
            "owner_identity_verified": True,
            "raw_body_immutable": True,
            "host_alias": "rpi5",
            "rpi5_main_sha": RPI5_SHA,
            "expected_bootstrap_baseline_token": "baseline-v1:abc",
            "start_date": bootstrap["start_date"],
            "end_date": bootstrap["end_date"],
            "recovery_decision": "verified-backup-available",
            "helper_install_artifact_count": 13,
            "additional_mutation_budget": budgets["supplemental"],
        },
        "mutation_budgets": {
            "release": budgets["release"],
            "supplemental": budgets["supplemental"],
            "read_only": budgets["read_only"],
        },
        "authority_safety": {
            "generic_shell_authority": False,
            "caller_selected_path": False,
            "caller_selected_argv": False,
            "caller_selected_environment": False,
            "caller_selected_repository_url": False,
            "credentials_exposed": False,
            "home_coordinates_exposed": False,
            "private_bigquery_or_weathernext_data": False,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
            "automatic_restore": False,
            "automatic_delete": False,
        },
    }


def test_source_package_requires_post_merge_queue_and_fresh_jit_evidence() -> None:
    contract = _contract()
    assert contract["status"] == "SOURCE_READY_REQUIRES_POST_MERGE_QUEUE_AND_FRESH_JIT_EVIDENCE"
    assert contract["deploy_queue"]["current_source_assessment"] == "POST_MERGE_QUEUE_RECONCILIATION_REQUIRED"
    assert "QUEUE_MUST_BIND_FINAL_MERGED_WEATHER_SHA" in contract["deploy_queue"]["current_block_reasons"]
    assert contract["runtime_evidence"]["operator_installation_proof_required"] is True
    assert contract["runtime_evidence"]["fresh_baseline_required"] is True
    assert contract["post_merge_reconciliation"]["final_merged_weather_sha_must_match_ready_queue"] is True
    assert contract["post_merge_reconciliation"]["queue_ready_transition_authorized_by_this_source_issue"] is False
    compatibility_gate = contract["next_owner_live_gate"]
    assert compatibility_gate["available_now"] is False
    assert compatibility_gate["historical_schema_compatibility_only"] is True
    assert compatibility_gate["superseded"] is True
    assert contract["authority"]["source_auto_full_authorizes_live"] is False


def test_static_rpi_contract_does_not_claim_current_operator_installation_state() -> None:
    rpi = _contract()["rpi5_contracts"]
    assert "composite_operator_status" not in rpi
    assert "operator_install_status" not in rpi
    assert rpi["operator_installer_status_is_current_runtime_proof"] is False
    assert rpi["operator_installer_status_is_current_host_state"] is False
    assert rpi["current_runtime_installation_state_must_come_from_jit_evidence"] is True


def test_full_sanitized_jit_evidence_can_pass_without_consuming_authorization() -> None:
    result = evaluate_first_public_rollout_preflight(_valid_evidence())
    assert result["state"] == "PASS"
    assert result["block_reasons"] == []
    assert result["live_authority_granted"] is False
    assert result["authorization_created"] is False
    assert result["authorization_consumed"] is False
    assert result["runtime_mutation_performed"] is False


def test_stale_weather_sha_or_ci_blocks() -> None:
    evidence = _valid_evidence()
    evidence["weather"]["current_main_sha"] = "f" * 40
    evidence["weather"]["exact_sha_ci"]["governance"] = "FAILURE"
    result = evaluate_first_public_rollout_preflight(evidence)
    assert "WEATHER_SHA_NOT_CURRENT_MAIN" in result["block_reasons"]
    assert "WEATHER_EXACT_SHA_CI_NOT_GREEN" in result["block_reasons"]


def test_stale_rpi_sha_or_ci_blocks() -> None:
    evidence = _valid_evidence()
    evidence["rpi5_main"]["current_main_sha"] = "a" * 40
    evidence["rpi5_main"]["exact_sha_ci"]["validate"] = "FAILURE"
    result = evaluate_first_public_rollout_preflight(evidence)
    assert "RPI5_SHA_NOT_CURRENT_MAIN" in result["block_reasons"]
    assert "RPI5_EXACT_SHA_CI_NOT_GREEN" in result["block_reasons"]


def test_queue_drift_and_host_target_mismatch_block() -> None:
    evidence = _valid_evidence()
    evidence["queue"]["source_sha"] = "1" * 40
    evidence["queue"]["target_alias"] = "wrong-target"
    evidence["runtime"]["host_alias"] = "wrong-host"
    evidence["runtime"]["target_alias"] = "wrong-target"
    result = evaluate_first_public_rollout_preflight(evidence)
    assert "QUEUE_WEATHER_SHA_MISMATCH" in result["block_reasons"]
    assert "QUEUE_TARGET_MISMATCH" in result["block_reasons"]
    assert "HOST_ALIAS_MISMATCH" in result["block_reasons"]
    assert "TARGET_ALIAS_MISMATCH" in result["block_reasons"]


def test_expired_or_replayed_authorization_blocks() -> None:
    evidence = _valid_evidence()
    evidence["authorization"]["ttl_valid"] = False
    evidence["authorization"]["replay_state"] = "CONSUMED"
    result = evaluate_first_public_rollout_preflight(evidence)
    assert "AUTHORIZATION_EXPIRED" in result["block_reasons"]
    assert "AUTHORIZATION_REPLAY_NOT_AVAILABLE" in result["block_reasons"]
    assert result["authorization_consumed"] is False


def test_baseline_mismatch_blocks() -> None:
    evidence = _valid_evidence()
    evidence["runtime"]["baseline_token"] = "baseline-v1:drift"
    result = evaluate_first_public_rollout_preflight(evidence)
    assert "BASELINE_TOKEN_MISMATCH" in result["block_reasons"]


def test_private_jit_input_is_rejected_even_when_safety_flags_claim_clean() -> None:
    evidence = _valid_evidence()
    evidence["credentials"] = "must-not-enter-preflight"
    result = evaluate_first_public_rollout_preflight(evidence)
    assert "EXCLUSION_SAFETY_MISMATCH" in result["block_reasons"]


def test_operator_installation_must_be_proven_by_fresh_runtime_evidence() -> None:
    evidence = _valid_evidence()
    evidence["runtime"]["operator"]["installed"] = False
    evidence["runtime"]["operator"]["verified"] = False
    result = evaluate_first_public_rollout_preflight(evidence)
    assert "OPERATOR_INSTALLATION_PROOF_REQUIRED" in result["block_reasons"]


def test_operator_budget_and_exclusion_drift_block() -> None:
    evidence = _valid_evidence()
    evidence["runtime"]["operator"]["verified"] = False
    evidence["mutation_budgets"]["release"] = copy.deepcopy(evidence["mutation_budgets"]["release"])
    evidence["mutation_budgets"]["release"][0]["max_operations"] = 2
    evidence["authority_safety"]["generic_shell_authority"] = True
    result = evaluate_first_public_rollout_preflight(evidence)
    assert "OPERATOR_INSTALLATION_PROOF_REQUIRED" in result["block_reasons"]
    assert "MUTATION_BUDGET_MISMATCH" in result["block_reasons"]
    assert "EXCLUSION_SAFETY_MISMATCH" in result["block_reasons"]


def test_live_preflight_cli_reads_sanitized_stdin_and_reports_pass(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["rozkalns-weather", "rollout-live-preflight-validate"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_valid_evidence())))
    cli_main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "PASS"
    assert payload["authorization_consumed"] is False
    serialized = json.dumps(payload)
    assert "HOME_LAT" not in serialized
    assert "/home/" not in serialized


def test_live_preflight_cli_blocked_uses_distinct_exit(monkeypatch, capsys) -> None:
    evidence = _valid_evidence()
    evidence["queue"]["source_sha"] = "0" * 40
    monkeypatch.setattr("sys.argv", ["rozkalns-weather", "rollout-live-preflight-validate"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(evidence)))
    with pytest.raises(SystemExit) as exc:
        cli_main()
    assert exc.value.code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "BLOCKED"
    assert "QUEUE_WEATHER_SHA_MISMATCH" in payload["block_reasons"]
