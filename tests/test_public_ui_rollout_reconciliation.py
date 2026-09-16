from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RPI5_SHA = "14592fd53e6f7f7a6f2f4a2a60f9b9d009134f43"


def _reconciliation() -> dict[str, object]:
    return json.loads((ROOT / "deploy/public-ui-rollout-reconciliation.json").read_text())


def test_public_ui_source_is_ready_but_live_is_not_claimed() -> None:
    payload = _reconciliation()
    assert payload["contract"] == "rozkalns-weather.public-ui-rollout-reconciliation.v1"
    assert payload["issue"] == 136
    assert payload["runtime_mode"] == "public-only"
    assert payload["weather"]["ui_source_implemented"] is True
    assert payload["weather"]["ui_surfaces"] == ["Overview", "Models", "Accuracy", "Warnings-Radar"]
    assert payload["outcome"] == "BLOCKED_WEATHER_V7_HOST_CAPABILITY_AND_QUEUE_RECOVERY"
    assert payload["next_owner_live_gate"]["available_now"] is True
    assert payload["safety"]["source_merge_authorizes_live"] is False
    assert payload["safety"]["source_merge_proves_deployment"] is False
    assert payload["safety"]["production_mutation_started"] is False


def test_rpi5_source_recovery_is_complete_but_host_capability_chain_is_not() -> None:
    payload = _reconciliation()
    rpi = payload["rpi5_main"]
    assert rpi["observed_main_sha"] == RPI5_SHA
    assert rpi["required_exact_main_ci"] == "5/5_SUCCESS"
    assert rpi["sudo_git_trust_correction_issue"] == 586
    assert rpi["sudo_git_trust_correction_pr"] == 587
    assert rpi["sudo_git_trust_correction_pr_state"] == "MERGED"
    assert rpi["source_dependency_satisfied"] is True
    assert rpi["host_capability_dependency_satisfied"] is False
    assert rpi["operator_v7_dependency_satisfied"] is False


def test_queue_remains_stale_and_fail_closed() -> None:
    queue = _reconciliation()["deploy_queue"]
    assert queue["issue"] == 46
    assert queue["observed_state"] == "OPEN_STOP_ERROR"
    assert queue["matches_weather_anchor"] is False
    assert queue["ready_for_current_candidate"] is False
    assert queue["grants_live_authority"] is False
    assert queue["refresh_authorized_by_issue_136"] is False


def test_fresh_host_observation_supports_only_the_first_weather_v7_gate() -> None:
    payload = _reconciliation()
    observed = payload["fresh_read_only_host_observation"]
    gate = payload["next_owner_live_gate"]
    assert observed["host_online"] is True
    assert observed["manager_checkout_matches_current_rpi5_main"] is False
    assert observed["manager_checkout_clean"] is False
    assert observed["corrected_installer_source_v2_checkout_present"] is False
    assert observed["predecessor_installer_source_checkout_present"] is True
    assert observed["predecessor_installer_source_checkout_clean"] is True
    assert observed["operator_upgrade_v7_checkout_present"] is False
    assert observed["weather_v7_privileged_broker_binary_present"] is False
    assert observed["weather_v7_privileged_broker_socket_loaded"] is False
    assert observed["weather_public_port_9180_listening"] is False
    assert observed["runtime_state_is_point_in_time_only"] is True
    assert gate["name"] == "DELIVER_CORRECTED_WEATHER_V7_INSTALLER_SOURCE_V2"
    assert gate["authorization_class"] == "STRICT"
    assert gate["rpi5_main_sha"] == RPI5_SHA
    assert gate["authorizes_host_capability_install"] is False
    assert gate["authorizes_operator_upgrade"] is False
    assert gate["authorizes_weather_rollout"] is False


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


def test_required_external_sequence_keeps_queue_and_composite_rollout_after_operator_v7() -> None:
    payload = _reconciliation()
    sequence = payload["required_external_sequence"]
    assert sequence[0].startswith("owner-authorized corrected Weather-v7 installer-source v2 delivery")
    assert "host-capability install" in sequence[2]
    assert "operator upgrade" in sequence[4]
    assert sequence[-2].startswith("run the existing first-public-rollout JIT preflight")
    assert sequence[-1] == "only then request the bounded Composite STRICT LIVE rollout authorization"
