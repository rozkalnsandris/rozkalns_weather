from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
from typing import Mapping

from .rollout import (
    BOOTSTRAP_MODELS,
    BOOTSTRAP_RUN_HOURS_UTC,
    OPERATION_ID,
    RECOVERY_DECISIONS,
    SOURCE_SHA_PATTERN,
    TARGET_ALIAS,
    TRUTH_STATION_ID,
    validate_bootstrap_inputs,
)

PREFLIGHT_CONTRACT = "rozkalns-weather.first-public-rollout-preflight.v1"
PREFLIGHT_PATH = "deploy/first-public-rollout-preflight.json"
SUCCESS = "SUCCESS"
FORBIDDEN_INPUT_KEYS = frozenset({
    "home_lat",
    "home_lon",
    "credentials",
    "credential",
    "token",
    "secret",
    "raw_log",
    "raw_logs",
    "database_path",
    "host_path",
    "env",
    "environment",
    "google_cloud_project",
    "bigquery_dataset",
})


def _contains_private_input(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_INPUT_KEYS:
                return True
            if _contains_private_input(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_private_input(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return lowered.startswith("/home/") or lowered.startswith("/root/")
    return False


def _load_contract(root: Path | None = None) -> dict[str, object]:
    root = root or Path.cwd()
    payload = json.loads((root / PREFLIGHT_PATH).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("first public rollout preflight contract must be a JSON object")
    if payload.get("contract") != PREFLIGHT_CONTRACT:
        raise ValueError("first public rollout preflight contract identity mismatch")
    return payload


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _budget_key(items: object, identity_key: str) -> tuple[tuple[str, int], ...] | None:
    if not isinstance(items, list):
        return None
    normalized: list[tuple[str, int]] = []
    for item in items:
        if not isinstance(item, Mapping):
            return None
        identity = item.get(identity_key)
        count = item.get("max_operations")
        if not isinstance(identity, str) or not isinstance(count, int):
            return None
        normalized.append((identity, count))
    return tuple(normalized)


def _add(blocks: list[str], code: str, condition: bool) -> None:
    if condition and code not in blocks:
        blocks.append(code)


def evaluate_first_public_rollout_preflight(
    evidence: Mapping[str, object], *, root: Path | None = None
) -> dict[str, object]:
    contract = _load_contract(root)
    blocks: list[str] = []
    _add(blocks, "EXCLUSION_SAFETY_MISMATCH", _contains_private_input(evidence))
    weather = _mapping(evidence.get("weather"))
    rpi5 = _mapping(evidence.get("rpi5_main"))
    queue = _mapping(evidence.get("queue"))
    runtime = _mapping(evidence.get("runtime"))
    operator = _mapping(runtime.get("operator"))
    authorization = _mapping(evidence.get("authorization"))
    safety = _mapping(evidence.get("authority_safety"))
    budgets = _mapping(evidence.get("mutation_budgets"))
    bootstrap = _mapping(evidence.get("bootstrap"))

    weather_candidate = weather.get("candidate_sha")
    weather_main = weather.get("current_main_sha")
    _add(blocks, "WEATHER_SHA_NOT_CURRENT_MAIN", not isinstance(weather_candidate, str) or not SOURCE_SHA_PATTERN.fullmatch(weather_candidate) or weather_candidate != weather_main)
    weather_ci = _mapping(weather.get("exact_sha_ci"))
    _add(blocks, "WEATHER_EXACT_SHA_CI_NOT_GREEN", weather_ci.get("governance") != SUCCESS or weather_ci.get("backend_tests") != SUCCESS)

    rpi_candidate = rpi5.get("candidate_sha")
    rpi_main = rpi5.get("current_main_sha")
    _add(blocks, "RPI5_SHA_NOT_CURRENT_MAIN", not isinstance(rpi_candidate, str) or not SOURCE_SHA_PATTERN.fullmatch(rpi_candidate) or rpi_candidate != rpi_main)
    rpi_ci = _mapping(rpi5.get("exact_sha_ci"))
    _add(blocks, "RPI5_EXACT_SHA_CI_NOT_GREEN", rpi_ci.get("validate") != SUCCESS)

    expected_queue = _mapping(contract.get("deploy_queue"))
    _add(blocks, "QUEUE_NOT_READY", queue.get("repository") != expected_queue.get("repository") or queue.get("issue") != expected_queue.get("issue") or queue.get("state") != expected_queue.get("required_state") or queue.get("eligibility_only") is not True or queue.get("grants_live_authority") is not False)
    _add(blocks, "QUEUE_WEATHER_SHA_MISMATCH", queue.get("source_sha") != weather_candidate)
    _add(blocks, "QUEUE_TARGET_MISMATCH", queue.get("target_alias") != TARGET_ALIAS)

    _add(blocks, "HOST_ALIAS_MISMATCH", runtime.get("host_alias") != contract.get("host_alias"))
    _add(blocks, "TARGET_ALIAS_MISMATCH", runtime.get("target_alias") != TARGET_ALIAS)
    _add(blocks, "OPERATOR_INSTALLATION_PROOF_REQUIRED", operator.get("installed") is not True or operator.get("verified") is not True)
    expected_rpi = _mapping(contract.get("rpi5_contracts"))
    _add(blocks, "OPERATOR_ARTIFACT_COUNT_MISMATCH", operator.get("artifact_count") != expected_rpi.get("operator_artifact_count"))
    identities = _mapping(evidence.get("contract_identities"))
    identity_fields = ("composite_operator", "operator_install", "helper_install", "composite_authority", "execution", "successor_trusted_checkout")
    _add(blocks, "CONTRACT_IDENTITY_MISMATCH", any(identities.get(field) != expected_rpi.get(field) for field in identity_fields))

    expected_bootstrap = _mapping(contract.get("bootstrap"))
    bootstrap_ok = False
    try:
        parsed = validate_bootstrap_inputs(
            start=date.fromisoformat(str(bootstrap.get("start_date"))),
            end=date.fromisoformat(str(bootstrap.get("end_date"))),
            models=bootstrap.get("models", []),
            run_hours_utc=bootstrap.get("run_hours_utc", []),
        )
        bootstrap_ok = (
            parsed["start_date"] == expected_bootstrap.get("start_date")
            and parsed["end_date"] == expected_bootstrap.get("end_date")
            and parsed["truth_station_id"] == TRUTH_STATION_ID
            and tuple(parsed["models"]) == BOOTSTRAP_MODELS
            and tuple(parsed["run_hours_utc"]) == BOOTSTRAP_RUN_HOURS_UTC
        )
    except (TypeError, ValueError):
        bootstrap_ok = False
    _add(blocks, "BOOTSTRAP_BOUNDS_MISMATCH", not bootstrap_ok)

    recovery = bootstrap.get("recovery_decision")
    _add(blocks, "RECOVERY_DECISION_MISSING", recovery in (None, ""))
    _add(blocks, "RECOVERY_DECISION_INVALID", recovery not in (None, "") and recovery not in RECOVERY_DECISIONS)

    _add(blocks, "AUTHORIZATION_MISSING", authorization.get("present") is not True)
    expected_auth = _mapping(contract.get("authorization_evidence"))
    _add(blocks, "AUTHORIZATION_SCHEMA_MISMATCH", authorization.get("schema") != expected_auth.get("schema"))
    _add(blocks, "AUTHORIZATION_EXPIRED", authorization.get("ttl_valid") is not True)
    _add(blocks, "AUTHORIZATION_REPLAY_NOT_AVAILABLE", authorization.get("replay_state") != expected_auth.get("replay_state_before_first_mutation"))
    _add(blocks, "AUTHORIZATION_OWNER_INVALID", authorization.get("owner_identity_verified") is not True)
    _add(blocks, "AUTHORIZATION_BODY_MUTATED", authorization.get("raw_body_immutable") is not True)
    mapped_recovery = _mapping(_mapping(contract.get("recovery")).get("rpi5_value_mapping")).get(str(recovery))
    auth_scope_bad = (
        authorization.get("host_alias") != contract.get("host_alias")
        or authorization.get("rpi5_main_sha") != rpi_candidate
        or authorization.get("start_date") != expected_bootstrap.get("start_date")
        or authorization.get("end_date") != expected_bootstrap.get("end_date")
        or authorization.get("recovery_decision") != mapped_recovery
        or authorization.get("helper_install_artifact_count") != expected_rpi.get("helper_artifact_count")
    )
    _add(blocks, "AUTHORIZATION_SCOPE_MISMATCH", auth_scope_bad)

    baseline = runtime.get("baseline_token")
    expected_baseline = runtime.get("expected_baseline_token")
    _add(blocks, "BASELINE_TOKEN_MISSING", not isinstance(baseline, str) or not baseline or not isinstance(expected_baseline, str) or not expected_baseline)
    _add(blocks, "BASELINE_TOKEN_MISMATCH", isinstance(baseline, str) and isinstance(expected_baseline, str) and bool(baseline) and bool(expected_baseline) and baseline != expected_baseline)
    _add(blocks, "AUTHORIZATION_SCOPE_MISMATCH", authorization.get("expected_bootstrap_baseline_token") != expected_baseline)

    expected_budgets = _mapping(contract.get("mutation_budgets"))
    release_ok = _budget_key(budgets.get("release"), "category") == _budget_key(expected_budgets.get("release"), "category")
    supplemental_ok = _budget_key(budgets.get("supplemental"), "category") == _budget_key(expected_budgets.get("supplemental"), "category")
    readonly_ok = _budget_key(budgets.get("read_only"), "stage_id") == _budget_key(expected_budgets.get("read_only"), "stage_id")
    auth_supplemental_ok = _budget_key(authorization.get("additional_mutation_budget"), "category") == _budget_key(expected_budgets.get("supplemental"), "category")
    _add(blocks, "MUTATION_BUDGET_MISMATCH", not (release_ok and supplemental_ok and readonly_ok and auth_supplemental_ok))

    required_false = (
        "generic_shell_authority",
        "caller_selected_path",
        "caller_selected_argv",
        "caller_selected_environment",
        "caller_selected_repository_url",
        "credentials_exposed",
        "home_coordinates_exposed",
        "private_bigquery_or_weathernext_data",
        "automatic_retry",
        "automatic_cleanup",
        "automatic_rollback",
        "automatic_restore",
        "automatic_delete",
    )
    _add(blocks, "EXCLUSION_SAFETY_MISMATCH", any(safety.get(field) is not False for field in required_false))

    return {
        "schema_version": 1,
        "contract": PREFLIGHT_CONTRACT,
        "state": "PASS" if not blocks else "BLOCKED",
        "block_reasons": blocks,
        "host_alias": contract.get("host_alias"),
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "weather_sha": weather_candidate,
        "rpi5_main_sha": rpi_candidate,
        "bootstrap": {
            "start_date": expected_bootstrap.get("start_date"),
            "end_date": expected_bootstrap.get("end_date"),
            "models": list(BOOTSTRAP_MODELS),
            "run_hours_utc": list(BOOTSTRAP_RUN_HOURS_UTC),
            "truth_station_id": TRUTH_STATION_ID,
        },
        "recovery_decision": recovery,
        "live_authority_granted": False,
        "authorization_created": False,
        "authorization_consumed": False,
        "runtime_mutation_performed": False,
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "private_paths_exposed": False,
            "raw_logs_exposed": False,
        },
    }
