from __future__ import annotations

from datetime import date
import json
import sys
from typing import Mapping

from .production_bootstrap import (
    MODELS,
    RUN_HOURS,
    SOURCE_SHA_RE,
    _run_keys,
    _truth_chunks,
    build_production_bootstrap_plan,
    evaluate_resume_evidence,
)

EVIDENCE_CONTRACT = "production-bootstrap-execution-evidence-v1"
TARGET_ALIAS = "rozkalns-weather-public-rpi5"
DATABASE_IDENTITY = "rozkalns-weather-public-corpus-sqlite-v1"
SCHEMA_INIT_COMMAND = "rozkalns-weather init-database"
_PRIVATE_KEYS = {
    "path", "database_path", "host_path", "private_path", "home_lat", "home_lon",
    "credential", "credentials", "token", "secret", "api_key", "api_token",
    "raw_log", "raw_logs", "env", "environment",
}


def _private(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _PRIVATE_KEYS
            or str(key).lower().endswith("_path")
            or _private(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_private(item) for item in value)
    return False


def _as_map(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _result(plan: Mapping[str, object], state: str, reasons: list[str], progress: dict[str, object]) -> dict[str, object]:
    identity = plan["identity"]
    assert isinstance(identity, Mapping)
    return {
        "schema_version": 1,
        "contract": EVIDENCE_CONTRACT,
        "state": state,
        "block_reasons": list(dict.fromkeys(reasons)),
        "bindings": {
            "source_sha": identity["source_sha"],
            "bootstrap_fingerprint": plan["bootstrap_fingerprint"],
            "target_alias": TARGET_ALIAS,
            "database_identity": DATABASE_IDENTITY,
            "start_date": identity["start_date"],
            "end_date": identity["end_date"],
            "models": list(identity["models"]),
            "run_hours_utc": list(identity["run_hours_utc"]),
            "truth_station_id": identity["truth_station_id"],
            "recovery_decision": identity["recovery_decision"],
        },
        "progress": progress,
        "authority": {
            "production_data_authority_granted": False,
            "automatic_retry_allowed": False,
            "automatic_restore_allowed": False,
            "automatic_delete_allowed": False,
            "host_runtime_mutation_authorized": False,
        },
        "privacy": {
            "private_paths_exposed": False,
            "credentials_exposed": False,
            "coordinates_exposed": False,
            "raw_logs_exposed": False,
        },
    }


def validate_execution_evidence(plan: Mapping[str, object], evidence: Mapping[str, object]) -> dict[str, object]:
    identity = _as_map(plan.get("identity"))
    if identity is None:
        raise ValueError("production bootstrap plan identity missing")
    start = date.fromisoformat(str(identity["start_date"]))
    end = date.fromisoformat(str(identity["end_date"]))
    expected_truth = _truth_chunks(start, end)
    expected_runs = _run_keys(start, end)
    progress: dict[str, object] = {
        "truth": {"completed": 0, "expected": len(expected_truth)},
        "forecasts": {model: {"completed": 0, "expected": len(expected_runs)} for model in MODELS},
        "complete": False,
    }
    if _private(evidence):
        return _result(plan, "BLOCKED", ["PRIVATE_EVIDENCE_REJECTED"], progress)

    reasons: list[str] = []
    if evidence.get("schema_version") != 1:
        reasons.append("EVIDENCE_SCHEMA_MISMATCH")
    if evidence.get("contract") != EVIDENCE_CONTRACT:
        reasons.append("EVIDENCE_CONTRACT_MISMATCH")
    source_sha = evidence.get("source_sha")
    if not isinstance(source_sha, str) or not SOURCE_SHA_RE.fullmatch(source_sha) or source_sha != identity.get("source_sha"):
        reasons.append("SOURCE_SHA_MISMATCH")
    if evidence.get("bootstrap_fingerprint") != plan.get("bootstrap_fingerprint"):
        reasons.append("BOOTSTRAP_FINGERPRINT_MISMATCH")
    if evidence.get("recovery_decision") != identity.get("recovery_decision"):
        reasons.append("RECOVERY_DECISION_MISMATCH")
    if evidence.get("target_alias") != TARGET_ALIAS:
        reasons.append("TARGET_ALIAS_MISMATCH")
    if evidence.get("database_identity") != DATABASE_IDENTITY:
        reasons.append("DATABASE_IDENTITY_UNBOUND")

    bound = _as_map(evidence.get("identity"))
    if bound is None:
        reasons.append("BOOTSTRAP_IDENTITY_MISSING")
    else:
        for field in ("start_date", "end_date", "truth_station_id", "recovery_decision"):
            if bound.get(field) != identity.get(field):
                reasons.append(f"{field.upper()}_MISMATCH")
        if bound.get("models") != list(MODELS):
            reasons.append("MODELS_MISMATCH")
        if bound.get("run_hours_utc") != list(RUN_HOURS):
            reasons.append("RUN_HOURS_MISMATCH")

    schema = _as_map(evidence.get("schema"))
    if schema is None or schema.get("explicit_init_completed") is not True or schema.get("command") != SCHEMA_INIT_COMMAND:
        reasons.append("SCHEMA_INIT_NOT_EXPLICITLY_PROVEN")

    truth = _as_map(evidence.get("truth"))
    if truth is not None:
        completed = truth.get("completed_chunks")
        completed_n = len(completed) if isinstance(completed, list) else 0
        progress["truth"] = {"completed": completed_n, "expected": len(expected_truth)}
        if truth.get("expected_chunk_count") != len(expected_truth):
            reasons.append("TRUTH_EXPECTED_COUNT_MISMATCH")
        if truth.get("present_chunk_count") != completed_n:
            reasons.append("TRUTH_PRESENT_COUNT_MISMATCH")
        if truth.get("checkpoint_ahead_of_database") is True or truth.get("database_ahead_of_checkpoint") is True:
            reasons.append("CHECKPOINT_DATABASE_DIVERGENCE")
        if truth.get("write_interrupted") is True:
            reasons.append("INTERRUPTED_WRITE_REQUIRES_STOP")

    forecasts = _as_map(evidence.get("forecasts"))
    if forecasts is not None:
        forecast_progress = progress["forecasts"]
        assert isinstance(forecast_progress, dict)
        for model in MODELS:
            section = _as_map(forecasts.get(model))
            if section is None:
                continue
            completed = section.get("completed_runs")
            completed_n = len(completed) if isinstance(completed, list) else 0
            forecast_progress[model] = {"completed": completed_n, "expected": len(expected_runs)}
            prefix = model.upper()
            if section.get("expected_run_count") != len(expected_runs):
                reasons.append(f"{prefix}_EXPECTED_COUNT_MISMATCH")
            if section.get("present_run_count") != completed_n:
                reasons.append(f"{prefix}_PRESENT_COUNT_MISMATCH")
            if section.get("checkpoint_ahead_of_database") is True or section.get("database_ahead_of_checkpoint") is True:
                reasons.append("CHECKPOINT_DATABASE_DIVERGENCE")
            if section.get("write_interrupted") is True:
                reasons.append("INTERRUPTED_WRITE_REQUIRES_STOP")

    try:
        base = evaluate_resume_evidence(plan, evidence)
    except ValueError:
        reasons.append("MALFORMED_EVIDENCE")
        base_reasons: list[str] = []
    else:
        base_reasons = [str(item) for item in base.get("block_reasons", [])]

    partial = "PARTIAL_BOOTSTRAP_INCOMPLETE" in base_reasons
    for reason in base_reasons:
        if reason == "PARTIAL_BOOTSTRAP_INCOMPLETE":
            continue
        if reason == "CORPUS_INTEGRITY_NOT_PROVEN" and partial:
            integrity = _as_map(evidence.get("integrity"))
            if integrity is not None and integrity.get("ok") is None:
                continue
        reasons.append(reason)

    complete = not partial and "MALFORMED_EVIDENCE" not in reasons
    progress["complete"] = complete
    if reasons:
        state = "BLOCKED"
    elif complete:
        state = "PASS"
    else:
        state = "IN_PROGRESS"
    return _result(plan, state, reasons, progress)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m rozkalns_weather.production_bootstrap_evidence")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--recovery-decision", required=True)
    args = parser.parse_args()
    try:
        plan = build_production_bootstrap_plan(
            source_sha=args.source_sha,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            recovery_decision=args.recovery_decision,
        )
        evidence = json.load(sys.stdin)
        if not isinstance(evidence, dict):
            raise ValueError
        payload = validate_execution_evidence(plan, evidence)
    except (ValueError, json.JSONDecodeError):
        payload = {
            "schema_version": 1,
            "contract": EVIDENCE_CONTRACT,
            "state": "BLOCKED",
            "block_reasons": ["MALFORMED_EVIDENCE"],
            "authority": {"production_data_authority_granted": False},
            "privacy": {"private_paths_exposed": False, "credentials_exposed": False, "coordinates_exposed": False, "raw_logs_exposed": False},
        }
    print(json.dumps(payload, sort_keys=True, indent=2))
    raise SystemExit(0 if payload["state"] in {"PASS", "IN_PROGRESS"} else 3)


if __name__ == "__main__":
    main()
