from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import re
from typing import Mapping

from .backfill import iter_run_times
from .models import utc_iso

SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COMMON_START = date(2026, 4, 2)
MAX_DAYS = 180
TRUTH_CHUNK_DAYS = 14
MODELS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
RUN_HOURS = (0, 6, 12, 18)
RECOVERY_DECISIONS = ("verified_backup_available", "owner_accepts_proceeding_without_prewrite_backup")
FORBIDDEN_KEYS = frozenset({"home_lat", "home_lon", "credentials", "credential", "raw_logs", "raw_log", "database_path", "host_path", "env", "environment"})


def _truth_chunks(start: date, end: date) -> tuple[str, ...]:
    chunks: list[str] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=TRUTH_CHUNK_DAYS - 1))
        chunks.append(f"{cursor.isoformat()}..{chunk_end.isoformat()}")
        cursor = chunk_end + timedelta(days=1)
    return tuple(chunks)


def _run_keys(start: date, end: date) -> tuple[str, ...]:
    return tuple(utc_iso(value) for value in iter_run_times(start, end, RUN_HOURS))


def _prefix_reason(values: object, expected: tuple[str, ...], label: str) -> str | None:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        return f"{label}_CHECKPOINT_INVALID"
    if len(values) != len(set(values)):
        return f"{label}_CHECKPOINT_DUPLICATE"
    if tuple(values) != expected[: len(values)]:
        return f"{label}_CHECKPOINT_NOT_PREFIX"
    return None


def _contains_forbidden(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).lower() in FORBIDDEN_KEYS or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def build_production_bootstrap_plan(*, source_sha: str, start: date, end: date, recovery_decision: str) -> dict[str, object]:
    if not SOURCE_SHA_RE.fullmatch(source_sha):
        raise ValueError("source SHA must be an exact lowercase 40-character commit SHA")
    if end < start:
        raise ValueError("bootstrap end date must not be before start date")
    if start < COMMON_START:
        raise ValueError(f"production common benchmark starts at {COMMON_START.isoformat()}")
    inclusive_days = (end - start).days + 1
    if inclusive_days > MAX_DAYS:
        raise ValueError(f"production bootstrap exceeds {MAX_DAYS} inclusive days")
    if recovery_decision not in RECOVERY_DECISIONS:
        raise ValueError("unsupported recovery decision")
    identity = {
        "source_sha": source_sha,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "models": list(MODELS),
        "run_hours_utc": list(RUN_HOURS),
        "truth_station_id": "10416",
        "truth_chunk_days": TRUTH_CHUNK_DAYS,
        "recovery_decision": recovery_decision,
    }
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema_version": 1,
        "state": "source_plan_ready",
        "bootstrap_fingerprint": fingerprint,
        "identity": identity,
        "inclusive_days": inclusive_days,
        "truth_chunk_count": len(_truth_chunks(start, end)),
        "forecast_run_count_per_model": len(_run_keys(start, end)),
        "schema_init_explicit_only": True,
        "implicit_migration_allowed": False,
        "delete_allowed": False,
        "restore_allowed": False,
        "production_data_authority_granted": False,
    }


def evaluate_resume_evidence(plan: Mapping[str, object], evidence: Mapping[str, object]) -> dict[str, object]:
    if _contains_forbidden(evidence):
        raise ValueError("production bootstrap evidence contains forbidden private field")
    identity = plan.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("production bootstrap plan identity missing")
    start = date.fromisoformat(str(identity["start_date"]))
    end = date.fromisoformat(str(identity["end_date"]))
    reasons: list[str] = []
    if evidence.get("bootstrap_fingerprint") != plan.get("bootstrap_fingerprint"):
        reasons.append("BOOTSTRAP_FINGERPRINT_MISMATCH")
    if evidence.get("recovery_decision") != identity.get("recovery_decision"):
        reasons.append("RECOVERY_DECISION_MISMATCH")
    schema = evidence.get("schema")
    if not isinstance(schema, Mapping) or schema.get("state") != "ready" or schema.get("implicit_migration_performed") is not False:
        reasons.append("SCHEMA_NOT_EXPLICITLY_READY")
    truth = evidence.get("truth")
    expected_truth = _truth_chunks(start, end)
    if not isinstance(truth, Mapping):
        reasons.append("TRUTH_EVIDENCE_MISSING")
        truth_completed: list[str] = []
    else:
        truth_completed = truth.get("completed_chunks", []) if isinstance(truth.get("completed_chunks", []), list) else []
        reason = _prefix_reason(truth.get("completed_chunks"), expected_truth, "TRUTH")
        if reason:
            reasons.append(reason)
        if truth.get("station_id") != "10416":
            reasons.append("TRUTH_STATION_MISMATCH")
        if truth.get("database_ahead_of_checkpoint") is True:
            reasons.append("INTERRUPTED_CHECKPOINT_RESUME_REQUIRED")
    forecasts = evidence.get("forecasts")
    expected_runs = _run_keys(start, end)
    complete_models = 0
    if not isinstance(forecasts, Mapping):
        reasons.append("FORECAST_EVIDENCE_MISSING")
    else:
        for model in MODELS:
            model_state = forecasts.get(model)
            if not isinstance(model_state, Mapping):
                reasons.append(f"{model.upper()}_EVIDENCE_MISSING")
                continue
            reason = _prefix_reason(model_state.get("completed_runs"), expected_runs, model.upper())
            if reason:
                reasons.append(reason)
            completed = model_state.get("completed_runs")
            if isinstance(completed, list) and len(completed) == len(expected_runs):
                complete_models += 1
            if model_state.get("revision_drift_runs") not in ([], None):
                reasons.append(f"{model.upper()}_REVISION_DRIFT")
            if model_state.get("unexpected_runs") not in ([], None):
                reasons.append(f"{model.upper()}_UNEXPECTED_RUNS")
            if model_state.get("database_ahead_of_checkpoint") is True:
                reasons.append("INTERRUPTED_CHECKPOINT_RESUME_REQUIRED")
    integrity = evidence.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("ok") is not True:
        reasons.append("CORPUS_INTEGRITY_NOT_PROVEN")
    if len(truth_completed) != len(expected_truth) or complete_models != len(MODELS):
        reasons.append("PARTIAL_BOOTSTRAP_INCOMPLETE")
    reasons = list(dict.fromkeys(reasons))
    return {
        "schema_version": 1,
        "state": "PASS" if not reasons else "BLOCKED",
        "block_reasons": reasons,
        "production_data_authority_granted": False,
        "automatic_retry_allowed": False,
        "automatic_restore_allowed": False,
        "automatic_delete_allowed": False,
    }
