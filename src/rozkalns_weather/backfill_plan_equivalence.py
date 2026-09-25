from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from .production_bootstrap import CHECKPOINT_NAMESPACE, MODELS, RUN_HOURS, SOURCE_SHA_RE

CONTRACT = "backfill-plan-equivalence-v1"
_ALLOWED_PROGRESS_KEYS = frozenset({"started_at_utc", "updated_at_utc", "completed_count", "attempt", "note"})
_PRIVATE_KEYS = frozenset({
    "path", "database_path", "host_path", "private_path", "home_lat", "home_lon",
    "credential", "credentials", "token", "secret", "api_key", "api_token",
    "raw_log", "raw_logs", "env", "environment",
})


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


def _canonical_sha256(value: Mapping[str, object]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{label} must be a non-empty list of strings")
    return list(value)


def _int_list(value: object, label: str) -> list[int]:
    if not isinstance(value, list) or not value or any(not isinstance(item, int) or isinstance(item, bool) for item in value):
        raise ValueError(f"{label} must be a non-empty list of integers")
    return list(value)


def build_backfill_plan_receipt(
    *,
    source_sha: str,
    start_date: str,
    end_date: str,
    providers_models: Sequence[str],
    run_hours_utc: Sequence[int],
    truth_chunks: Sequence[str],
    rate_limits: Mapping[str, int],
    checkpoint_namespace: str,
    recovery_decision: str,
) -> dict[str, object]:
    if not SOURCE_SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be an exact lowercase 40-character commit SHA")
    if not start_date or not end_date or start_date > end_date:
        raise ValueError("invalid date window")
    providers = list(providers_models)
    run_hours = list(run_hours_utc)
    chunks = list(truth_chunks)
    if not providers or any(not isinstance(item, str) or not item for item in providers):
        raise ValueError("providers_models invalid")
    if not run_hours or any(not isinstance(item, int) or isinstance(item, bool) for item in run_hours):
        raise ValueError("run_hours_utc invalid")
    if not chunks or any(not isinstance(item, str) or not item for item in chunks):
        raise ValueError("truth_chunks invalid")
    normalized_limits: dict[str, int] = {}
    for key in sorted(rate_limits):
        value = rate_limits[key]
        if not isinstance(key, str) or not key or not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError("rate_limits must contain positive integer limits")
        normalized_limits[key] = value
    if not normalized_limits:
        raise ValueError("rate_limits missing")
    if not checkpoint_namespace:
        raise ValueError("checkpoint_namespace missing")
    if not recovery_decision:
        raise ValueError("recovery_decision missing")

    identity: dict[str, object] = {
        "source_sha": source_sha,
        "start_date": start_date,
        "end_date": end_date,
        "providers_models": providers,
        "run_hours_utc": run_hours,
        "truth_chunks": chunks,
        "rate_limits": normalized_limits,
        "checkpoint_namespace": checkpoint_namespace,
        "recovery_decision": recovery_decision,
    }
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "plan_digest_sha256": _canonical_sha256(identity),
        "identity": identity,
        "authority": {
            "production_corpus_write_authorized": False,
            "runtime_live_authorized": False,
        },
    }


def _prefix_reason(actual: object, expected: list[str]) -> str | None:
    if not isinstance(actual, list) or any(not isinstance(item, str) for item in actual):
        return "CHECKPOINT_PREFIX_INVALID"
    if len(actual) != len(set(actual)):
        return "CHECKPOINT_PREFIX_DUPLICATE"
    if actual != expected[: len(actual)]:
        return "CHECKPOINT_PREFIX_REORDERED_OR_EXPANDED"
    return None


def validate_execution_equivalence(
    frozen_plan: Mapping[str, object], execution_evidence: Mapping[str, object]
) -> dict[str, object]:
    reasons: list[str] = []
    if _private(execution_evidence):
        reasons.append("PRIVATE_EVIDENCE_REJECTED")

    identity = frozen_plan.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("frozen plan identity missing")
    if frozen_plan.get("contract") != CONTRACT:
        raise ValueError("unsupported frozen plan contract")
    expected_digest = frozen_plan.get("plan_digest_sha256")
    if not isinstance(expected_digest, str):
        raise ValueError("frozen plan digest missing")

    if execution_evidence.get("plan_digest_sha256") != expected_digest:
        reasons.append("PLAN_DIGEST_MISMATCH")

    bound = execution_evidence.get("identity")
    if not isinstance(bound, Mapping):
        reasons.append("EXECUTION_IDENTITY_MISSING")
        bound = {}

    material_fields = (
        "source_sha",
        "start_date",
        "end_date",
        "providers_models",
        "run_hours_utc",
        "truth_chunks",
        "rate_limits",
        "checkpoint_namespace",
        "recovery_decision",
    )
    for field in material_fields:
        if bound.get(field) != identity.get(field):
            reasons.append(f"{field.upper()}_DRIFT")

    expected_chunks = _string_list(identity.get("truth_chunks"), "truth_chunks")
    checkpoint = execution_evidence.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        reasons.append("CHECKPOINT_EVIDENCE_MISSING")
    else:
        if checkpoint.get("namespace") != identity.get("checkpoint_namespace"):
            reasons.append("CHECKPOINT_NAMESPACE_DRIFT")
        reason = _prefix_reason(checkpoint.get("completed_truth_chunks"), expected_chunks)
        if reason:
            reasons.append(reason)
        if checkpoint.get("recovery_decision") != identity.get("recovery_decision"):
            reasons.append("CHECKPOINT_RECOVERY_DECISION_DRIFT")

    progress = execution_evidence.get("progress_metadata", {})
    if not isinstance(progress, Mapping):
        reasons.append("PROGRESS_METADATA_INVALID")
    else:
        unexpected = sorted(str(key) for key in progress if str(key) not in _ALLOWED_PROGRESS_KEYS)
        if unexpected:
            reasons.append("PROGRESS_METADATA_MATERIAL_FIELD")

    reasons = list(dict.fromkeys(reasons))
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "state": "PASS" if not reasons else "BLOCKED",
        "block_reasons": reasons,
        "plan_digest_sha256": expected_digest,
        "scope_equivalent": not reasons,
        "authority": {
            "production_corpus_write_authorized": False,
            "runtime_live_authorized": False,
            "automatic_retry_authorized": False,
        },
    }


def build_default_bootstrap_plan_receipt(*, source_sha: str, recovery_decision: str) -> dict[str, object]:
    return build_backfill_plan_receipt(
        source_sha=source_sha,
        start_date="2026-08-13",
        end_date="2026-08-26",
        providers_models=MODELS,
        run_hours_utc=RUN_HOURS,
        truth_chunks=("2026-08-13..2026-08-26",),
        rate_limits={"forecast_requests_per_minute": 30, "truth_requests_per_minute": 10},
        checkpoint_namespace=CHECKPOINT_NAMESPACE,
        recovery_decision=recovery_decision,
    )
