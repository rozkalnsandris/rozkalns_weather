from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import re
from typing import Mapping

from .backfill import iter_run_times
from .locations import BENCHMARK_LOCATION
from .models import utc_iso
from .providers.dwd_cdc_observations import CDC_STATION_ID, REQUIRED_VARIABLES

SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TRUTH_VERIFIED_START = date(2026, 4, 2)
VERIFIED_TRUTH_END = date(2026, 9, 10)
FIXED_WINDOW_START = date(2026, 8, 13)
FIXED_WINDOW_END = date(2026, 8, 26)
COMMON_START = FIXED_WINDOW_START
MAX_DAYS = 14
TRUTH_CHUNK_DAYS = 14
MODELS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
RUN_HOURS = (0, 6, 12, 18)
RECOVERY_DECISIONS = ("verified_backup_available", "owner_accepts_proceeding_without_prewrite_backup")
TRUTH_SOURCE_AUTHORITY = "DWD"
TRUTH_TRANSPORT = "DWD CDC Open Data"
TRUTH_TRANSPORT_STATUS = "verified_frozen_window_product_coverage"
FORECAST_TRANSPORT_STATUS = "VERIFIED_COMPLETE_FIXED_WINDOW"
FORECAST_TRANSPORT_DECISION_CONTRACT = "deploy/exact-run-common-window.json"
CHECKPOINT_NAMESPACE = "fixed-window-20260813-20260826-v1"
LEGACY_FORECAST_TRANSPORT_BLOCK_REASON = "NO_COMPLETE_ICON_D2_EXACT_RUN_ARCHIVE_TRANSPORT"
LEGACY_FORECAST_TRANSPORT_DECISION_CONTRACT = "deploy/icon-d2-exact-run-transport-decision.json"
# Compatibility identity retained for readers of pre-#159 plans. New plans do not emit it as a blocker.
FORECAST_TRANSPORT_BLOCK_REASON = LEGACY_FORECAST_TRANSPORT_BLOCK_REASON
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
    if (start, end) != (FIXED_WINDOW_START, FIXED_WINDOW_END):
        raise ValueError(
            "production bootstrap requires the exact fixed common window "
            f"{FIXED_WINDOW_START.isoformat()}..{FIXED_WINDOW_END.isoformat()}"
        )
    if start < TRUTH_VERIFIED_START or end > VERIFIED_TRUTH_END:
        raise ValueError("fixed common window is outside source-verified DWD CDC truth coverage")
    inclusive_days = (end - start).days + 1
    if inclusive_days > MAX_DAYS:
        raise ValueError(f"production bootstrap exceeds {MAX_DAYS} inclusive days")
    if recovery_decision not in RECOVERY_DECISIONS:
        raise ValueError("unsupported recovery decision")
    identity = {
        "source_sha": source_sha,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "window_kind": "fixed_non_rolling",
        "models": list(MODELS),
        "run_hours_utc": list(RUN_HOURS),
        "benchmark_location_id": BENCHMARK_LOCATION.id,
        "truth_station_id": CDC_STATION_ID,
        "truth_variables": list(REQUIRED_VARIABLES),
        "truth_chunk_days": TRUTH_CHUNK_DAYS,
        "truth_source_authority": TRUTH_SOURCE_AUTHORITY,
        "truth_transport": TRUTH_TRANSPORT,
        "truth_transport_status": TRUTH_TRANSPORT_STATUS,
        "exact_run_transport_status": FORECAST_TRANSPORT_STATUS,
        "exact_run_transport_decision_contract": FORECAST_TRANSPORT_DECISION_CONTRACT,
        "checkpoint_namespace": CHECKPOINT_NAMESPACE,
        "pre_159_fingerprint_reusable": False,
        "recovery_decision": recovery_decision,
    }
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    transport = {
        "transport": "Open-Meteo Single Runs API",
        "status": FORECAST_TRANSPORT_STATUS,
        "decision_contract": FORECAST_TRANSPORT_DECISION_CONTRACT,
        "exact_init_required": True,
        "full_horizon_required": True,
        "skip_ahead_allowed": False,
        "live_backfill_allowed": False,
    }
    return {
        "schema_version": 2,
        "state": "SOURCE_READY_REQUIRES_EXACT_LIVE_DATA_AUTHORITY",
        "block_reasons": [],
        "bootstrap_fingerprint": fingerprint,
        "identity": identity,
        "truth_transport": {
            "source_authority": TRUTH_SOURCE_AUTHORITY,
            "transport": TRUTH_TRANSPORT,
            "station_id": CDC_STATION_ID,
            "location_id": BENCHMARK_LOCATION.id,
            "station_name": "Werl",
            "required_variables": list(REQUIRED_VARIABLES),
            "verified_window_start": TRUTH_VERIFIED_START.isoformat(),
            "verified_window_end": VERIFIED_TRUTH_END.isoformat(),
            "selected_common_window_start": FIXED_WINDOW_START.isoformat(),
            "selected_common_window_end": FIXED_WINDOW_END.isoformat(),
            "historical_capability": TRUTH_TRANSPORT_STATUS,
            "coverage_revalidation_required_before_live": True,
            "live_backfill_allowed": False,
        },
        "forecast_colocation": {
            "location_id": BENCHMARK_LOCATION.id,
            "models": list(MODELS),
            "exact_public_station_coordinates": True,
            "nearest_station_fallback_allowed": False,
        },
        "forecast_transport": {model: dict(transport) for model in MODELS},
        "historical_evidence": {
            "legacy_transport_decision_contract": LEGACY_FORECAST_TRANSPORT_DECISION_CONTRACT,
            "legacy_block_reason": LEGACY_FORECAST_TRANSPORT_BLOCK_REASON,
            "existing_rows_preserved": True,
            "existing_rows_rewritten": False,
            "legacy_checkpoint_reusable_for_fixed_window": False,
        },
        "inclusive_days": inclusive_days,
        "truth_chunk_count": len(_truth_chunks(start, end)),
        "forecast_run_count_per_model": len(_run_keys(start, end)),
        "checkpoint_namespace": CHECKPOINT_NAMESPACE,
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
    plan_reasons = plan.get("block_reasons")
    reasons: list[str] = []
    if isinstance(plan_reasons, list) and all(isinstance(reason, str) for reason in plan_reasons):
        reasons.extend(plan_reasons)
    elif plan_reasons not in (None, []):
        reasons.append("PLAN_BLOCK_REASONS_INVALID")
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
        if truth.get("station_id") != CDC_STATION_ID:
            reasons.append("TRUTH_STATION_MISMATCH")
        if truth.get("location_id") != BENCHMARK_LOCATION.id:
            reasons.append("TRUTH_LOCATION_MISMATCH")
        if truth.get("variables") != list(REQUIRED_VARIABLES):
            reasons.append("TRUTH_VARIABLE_SCOPE_MISMATCH")
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
            if model_state.get("location_id") != BENCHMARK_LOCATION.id:
                reasons.append(f"{model.upper()}_LOCATION_MISMATCH")
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
        "schema_version": 2,
        "state": "PASS" if not reasons else "BLOCKED",
        "block_reasons": reasons,
        "checkpoint_namespace": CHECKPOINT_NAMESPACE,
        "production_data_authority_granted": False,
        "automatic_retry_allowed": False,
        "automatic_restore_allowed": False,
        "automatic_delete_allowed": False,
    }
