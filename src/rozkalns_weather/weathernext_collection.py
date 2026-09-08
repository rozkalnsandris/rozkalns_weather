from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from .locations import DWD_10416
from .models import ForecastRun, ensure_utc
from .providers.weathernext import (
    STATS,
    available_init_candidates,
    expected_available_at,
    forecast_horizon_hours,
    run_class,
)
from .verification import lead_bucket, sample_confidence
from .weathernext_access import validate_first_access_evidence, validate_provenance

LIFECYCLE_STATES = frozenset(
    {
        "access_ready",
        "snapshot_admissible",
        "collecting",
        "degraded",
        "version_boundary",
        "sample_insufficient",
        "first_month_ready",
    }
)
LIFECYCLE_TRANSITIONS = {
    ("access_ready", "snapshot_admitted"): "snapshot_admissible",
    ("snapshot_admissible", "first_snapshot_stored"): "collecting",
    ("collecting", "provider_degraded"): "degraded",
    ("degraded", "provider_recovered"): "collecting",
    ("collecting", "version_change_detected"): "version_boundary",
    ("version_boundary", "boundary_acknowledged"): "collecting",
    ("collecting", "month_closed_insufficient"): "sample_insufficient",
    ("sample_insufficient", "continue_collecting"): "collecting",
    ("collecting", "month_closed_eligible"): "first_month_ready",
    ("sample_insufficient", "month_closed_eligible"): "first_month_ready",
}
RUN_LEDGER_STATES = frozenset(
    {"expected", "target_disseminated", "retrieved", "missing", "delayed", "superseded"}
)
SUPPORTED_MODEL_VERSIONS = frozenset({"3.0.0"})
MAX_RECOVERY_AGE_HOURS = 168
MAX_RECOVERY_INITS = 24
LATENCY_GRACE_MINUTES = 90
DEGRADED_AFTER_CONSECUTIVE_MISSING = 2
MIN_MEANINGFUL_SAMPLES = 30
PRIVATE_EVIDENCE_KEYS = frozenset(
    {
        "project",
        "project_id",
        "google_cloud_project",
        "dataset",
        "dataset_id",
        "weathernext_bigquery_dataset",
        "credential",
        "credentials",
        "token",
        "secret",
        "service_account",
        "home_lat",
        "home_lon",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "sql",
        "query_sql",
        "database_path",
        "filesystem_path",
        "host_path",
        "raw_payload",
        "raw_provider_payload",
        "raw_log",
        "raw_logs",
        "environment",
        "env",
    }
)
PRIVATE_VALUE_MARKERS = ("/home/", "/root/", "/opt/", "BEGIN PRIVATE KEY", "service_account")


@dataclass(frozen=True, slots=True)
class QuantileSample:
    variable: str
    observed: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    accumulation_window_minutes: int | None = None

    def __post_init__(self) -> None:
        values = (self.observed, self.p10, self.p25, self.p50, self.p75, self.p90)
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("quantile verification inputs must be finite")
        if not self.p10 <= self.p25 <= self.p50 <= self.p75 <= self.p90:
            raise ValueError("WeatherNext quantiles must be monotonic p10<=p25<=p50<=p75<=p90")
        if self.variable == "precipitation_1h" and self.accumulation_window_minutes != 60:
            raise ValueError("WeatherNext precipitation_1h requires a 60-minute accumulation window")


@dataclass(frozen=True, slots=True)
class VerificationSample:
    valid_time_utc: datetime
    lead_hours: float
    model_version: str
    forecast: float
    observed: float
    location_id: str = DWD_10416.id
    provider: str = "weathernext3"

    def __post_init__(self) -> None:
        object.__setattr__(self, "valid_time_utc", ensure_utc(self.valid_time_utc))
        if self.lead_hours < 0:
            raise ValueError("lead_hours must be >= 0")
        if not isfinite(float(self.forecast)) or not isfinite(float(self.observed)):
            raise ValueError("verification values must be finite")


def _utc_iso(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def transition_lifecycle(current: str, event: str) -> str:
    if current not in LIFECYCLE_STATES:
        raise ValueError("unknown WeatherNext collection lifecycle state")
    try:
        return LIFECYCLE_TRANSITIONS[(current, event)]
    except KeyError as exc:
        raise ValueError(f"invalid WeatherNext lifecycle transition: {current}+{event}") from exc


def build_collection_plan(
    *,
    now: datetime,
    known_init_times: Iterable[datetime] = (),
    limit: int = 24,
) -> dict[str, object]:
    if not 1 <= limit <= 24:
        raise ValueError("limit must be between 1 and 24")
    now = ensure_utc(now)
    known = {ensure_utc(value) for value in known_init_times}
    candidates = available_init_candidates(now, limit=limit)
    planned = []
    for init_time in candidates:
        if init_time in known:
            continue
        planned.append(
            {
                "init_time_utc": _utc_iso(init_time),
                "expected_available_at_utc": _utc_iso(expected_available_at(init_time)),
                "run_class": run_class(init_time),
                "forecast_horizon_hours": forecast_horizon_hours(init_time),
            }
        )
    return {
        "schema_version": 1,
        "state": "collection_plan_ready",
        "provider": "weathernext3",
        "planned_inits": planned,
        "planned_count": len(planned),
        "known_init_count": len(known),
        "dedupe_key": "provider+model_version+init_time_utc+location_id+source_surface",
        "scheduler_activation_authorized": False,
        "real_query_performed": False,
        "production_write_performed": False,
    }


def validate_snapshot_admission(
    *,
    first_access_evidence: Mapping[str, Any],
    runs: Sequence[ForecastRun],
) -> dict[str, object]:
    access = validate_first_access_evidence(first_access_evidence)
    if access.get("state") != "canary_ready_for_snapshot":
        raise ValueError("validated first-access canary is required")
    if not runs:
        raise ValueError("at least one WeatherNext run is required")
    selected_init = str(access.get("selected_init_time_utc") or "")
    schema_fingerprint = str(access.get("schema_fingerprint") or "")
    if not selected_init or not schema_fingerprint:
        raise ValueError("first-access init and schema fingerprint are required")

    resolutions: set[str] = set()
    identities: list[str] = []
    model_versions: set[str] = set()
    for run in runs:
        provenance = validate_provenance(run)
        if provenance.get("complete") is not True:
            raise ValueError("WeatherNext run provenance is incomplete")
        if _utc_iso(run.init_time_utc) != selected_init:
            raise ValueError("run init does not match validated first-access canary")
        resolution = str(run.source_metadata.get("resolution") or "")
        if resolution not in {"0p05", "0p1", "combined"}:
            raise ValueError("WeatherNext source resolution is not admitted")
        resolutions.add(resolution)
        model_versions.add(str(run.model_version or ""))
        identities.append(
            "|".join(
                (
                    run.provider,
                    str(run.model_version or ""),
                    _utc_iso(run.init_time_utc),
                    run.source_surface,
                    resolution,
                    str(len(run.values)),
                )
            )
        )
    if len(model_versions) != 1:
        raise ValueError("one snapshot admission cannot mix WeatherNext model versions")
    if "combined" not in resolutions and not {"0p05", "0p1"}.issubset(resolutions):
        raise ValueError("snapshot admission requires both 0p05 station and 0p1 surface products")
    model_version = next(iter(model_versions))
    if model_version not in SUPPORTED_MODEL_VERSIONS:
        raise ValueError("WeatherNext model version requires an explicit adapter decision")
    fingerprint = hashlib.sha256("\n".join(sorted(identities)).encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "state": "snapshot_admissible",
        "provider": "weathernext3",
        "model_version": model_version,
        "location_id": DWD_10416.id,
        "selected_init_time_utc": selected_init,
        "schema_fingerprint": schema_fingerprint,
        "admission_fingerprint": fingerprint,
        "product_surfaces_complete": True,
        "immutable_revision_required": True,
        "idempotency_required": True,
        "mutation_class": "production_sqlite_forecast_snapshot_write",
        "requires_exact_private_live_data_authority": True,
        "production_write_performed": False,
        "real_values_exposed": False,
    }


def reconcile_run_ledger(
    *,
    now: datetime,
    expected_init_times: Iterable[datetime],
    receipts: Mapping[str, Mapping[str, Any]] | None = None,
    latency_grace_minutes: int = LATENCY_GRACE_MINUTES,
) -> list[dict[str, object]]:
    if latency_grace_minutes < 0 or latency_grace_minutes > 360:
        raise ValueError("latency_grace_minutes must be between 0 and 360")
    now = ensure_utc(now)
    receipts = receipts or {}
    output: list[dict[str, object]] = []
    for init_time in sorted({ensure_utc(value) for value in expected_init_times}):
        init_key = _utc_iso(init_time)
        expected_at = expected_available_at(init_time)
        receipt = receipts.get(init_key)
        if receipt is not None:
            state = str(receipt.get("state") or "")
            if state not in {"retrieved", "delayed", "superseded"}:
                raise ValueError("receipt state must be retrieved, delayed or superseded")
        elif now < expected_at:
            state = "expected"
        elif now <= expected_at + timedelta(minutes=latency_grace_minutes):
            state = "target_disseminated"
        else:
            state = "missing"
        if state not in RUN_LEDGER_STATES:
            raise ValueError("unknown run ledger state")
        output.append(
            {
                "init_time_utc": init_key,
                "run_class": run_class(init_time),
                "expected_available_at_utc": _utc_iso(expected_at),
                "state": state,
                "observed_publication_at_utc": (
                    receipt.get("observed_publication_at_utc") if receipt else None
                ),
                "retrieved_at_utc": receipt.get("retrieved_at_utc") if receipt else None,
            }
        )
    return output


def plan_bounded_recovery(
    *,
    now: datetime,
    ledger: Iterable[Mapping[str, Any]],
    max_age_hours: int = MAX_RECOVERY_AGE_HOURS,
    max_inits: int = MAX_RECOVERY_INITS,
) -> dict[str, object]:
    if not 1 <= max_age_hours <= MAX_RECOVERY_AGE_HOURS:
        raise ValueError(f"max_age_hours must be between 1 and {MAX_RECOVERY_AGE_HOURS}")
    if not 1 <= max_inits <= MAX_RECOVERY_INITS:
        raise ValueError(f"max_inits must be between 1 and {MAX_RECOVERY_INITS}")
    now = ensure_utc(now)
    cutoff = now - timedelta(hours=max_age_hours)
    eligible: list[tuple[datetime, Mapping[str, Any]]] = []
    for item in ledger:
        if str(item.get("state") or "") != "missing":
            continue
        init_time = _parse_utc(str(item.get("init_time_utc") or ""))
        if cutoff <= init_time <= now and expected_available_at(init_time) <= now:
            eligible.append((init_time, item))
    eligible.sort(key=lambda pair: pair[0])
    selected = eligible[:max_inits]
    return {
        "schema_version": 1,
        "state": "recovery_plan_ready",
        "provider": "weathernext3",
        "max_age_hours": max_age_hours,
        "max_inits": max_inits,
        "planned_inits": [_utc_iso(item[0]) for item in selected],
        "planned_count": len(selected),
        "read_only_query_authority_required": True,
        "production_write_authority_required": True,
        "real_query_performed": False,
        "production_write_performed": False,
        "automatic_retry_or_cleanup": False,
    }


def evaluate_version_boundary(
    *,
    previous_model_version: str | None,
    previous_schema_fingerprint: str | None,
    current_model_version: str,
    current_schema_fingerprint: str,
    supported_versions: Iterable[str] = SUPPORTED_MODEL_VERSIONS,
) -> dict[str, object]:
    supported = set(supported_versions)
    if not current_model_version or not current_schema_fingerprint:
        raise ValueError("current model version and schema fingerprint are required")
    if current_model_version not in supported:
        return {
            "state": "version_boundary",
            "reason": "unsupported_model_version",
            "collection_eligible": False,
            "adapter_decision_required": True,
            "current_model_version": current_model_version,
            "schema_changed": previous_schema_fingerprint not in {None, current_schema_fingerprint},
        }
    version_changed = previous_model_version not in {None, current_model_version}
    schema_changed = previous_schema_fingerprint not in {None, current_schema_fingerprint}
    if version_changed or schema_changed:
        return {
            "state": "version_boundary",
            "reason": "model_version_changed" if version_changed else "schema_fingerprint_changed",
            "collection_eligible": False,
            "adapter_decision_required": True,
            "current_model_version": current_model_version,
            "schema_changed": schema_changed,
        }
    return {
        "state": "compatible",
        "reason": None,
        "collection_eligible": True,
        "adapter_decision_required": False,
        "current_model_version": current_model_version,
        "schema_changed": False,
    }


def collection_health(
    *,
    now: datetime,
    init_time: datetime,
    retrieved_at_utc: datetime | None,
    observed_publication_at_utc: datetime | None = None,
    consecutive_missing_runs: int = 0,
) -> dict[str, object]:
    if consecutive_missing_runs < 0:
        raise ValueError("consecutive_missing_runs must be >= 0")
    now = ensure_utc(now)
    init_time = ensure_utc(init_time)
    expected_at = expected_available_at(init_time)
    retrieved = ensure_utc(retrieved_at_utc) if retrieved_at_utc is not None else None
    observed = ensure_utc(observed_publication_at_utc) if observed_publication_at_utc is not None else None
    if observed is not None and observed < init_time:
        raise ValueError("observed publication cannot precede init")
    if retrieved is not None and retrieved < init_time:
        raise ValueError("retrieval cannot precede init")
    state = "degraded" if consecutive_missing_runs >= DEGRADED_AFTER_CONSECUTIVE_MISSING else "healthy"
    if consecutive_missing_runs == 0 and retrieved is not None:
        recovery_state = "recovered_or_healthy"
    elif state == "degraded":
        recovery_state = "degraded"
    else:
        recovery_state = "watching"
    return {
        "schema_version": 1,
        "state": state,
        "recovery_state": recovery_state,
        "provider": "weathernext3",
        "run_class": run_class(init_time),
        "init_time_utc": _utc_iso(init_time),
        "expected_available_at_utc": _utc_iso(expected_at),
        "observed_publication_at_utc": _utc_iso(observed) if observed else None,
        "retrieved_at_utc": _utc_iso(retrieved) if retrieved else None,
        "observed_publication_lag_minutes": (
            (observed - expected_at).total_seconds() / 60.0 if observed else None
        ),
        "retrieval_lag_minutes": (
            (retrieved - expected_at).total_seconds() / 60.0 if retrieved else None
        ),
        "freshness_age_minutes": (
            max(0.0, (now - retrieved).total_seconds() / 60.0) if retrieved else None
        ),
        "consecutive_missing_runs": consecutive_missing_runs,
        "private_fields_exposed": False,
    }


def first_month_verification_eligibility(
    samples: Iterable[VerificationSample],
    *,
    common_valid_times: Iterable[datetime],
    minimum_samples: int = MIN_MEANINGFUL_SAMPLES,
) -> dict[str, object]:
    if minimum_samples < MIN_MEANINGFUL_SAMPLES:
        raise ValueError(f"minimum_samples must be >= {MIN_MEANINGFUL_SAMPLES}")
    common = {ensure_utc(value) for value in common_valid_times}
    grouped: dict[tuple[str, str], list[VerificationSample]] = {}
    excluded = 0
    for sample in samples:
        if sample.provider != "weathernext3" or sample.location_id != DWD_10416.id:
            excluded += 1
            continue
        if sample.valid_time_utc not in common:
            excluded += 1
            continue
        key = (sample.model_version, lead_bucket(sample.lead_hours))
        grouped.setdefault(key, []).append(sample)
    slices = []
    meaningful_count = 0
    for (model_version, bucket), items in sorted(grouped.items()):
        n = len(items)
        meaningful = n >= minimum_samples
        meaningful_count += int(meaningful)
        errors = [item.forecast - item.observed for item in items]
        slices.append(
            {
                "model_version": model_version,
                "lead_bucket": bucket,
                "n": n,
                "sample_confidence": sample_confidence(n),
                "meaningful": meaningful,
                "mae": mean(abs(error) for error in errors) if meaningful else None,
                "rmse": (mean(error * error for error in errors) ** 0.5) if meaningful else None,
                "bias": mean(errors) if meaningful else None,
            }
        )
    return {
        "schema_version": 1,
        "state": "first_month_ready" if meaningful_count else "sample_insufficient",
        "provider": "weathernext3",
        "location_id": DWD_10416.id,
        "truth_source": "DWD WMO 10416",
        "minimum_samples_per_slice": minimum_samples,
        "common_valid_time_count": len(common),
        "excluded_sample_count": excluded,
        "eligible_slice_count": meaningful_count,
        "slices": slices,
        "home_accuracy_included": False,
    }


def summarize_quantile_calibration(samples: Iterable[QuantileSample]) -> dict[str, object]:
    items = list(samples)
    if not items:
        return {
            "n": 0,
            "p10_p90_coverage": None,
            "p10_p90_mean_width": None,
            "p25_p75_coverage": None,
            "p25_p75_mean_width": None,
            "p50_mae": None,
            "p50_bias": None,
            "precipitation_event_probability_supported": False,
        }
    variables = {item.variable for item in items}
    if len(variables) != 1:
        raise ValueError("quantile calibration summary must contain one variable")
    variable = next(iter(variables))
    errors = [item.p50 - item.observed for item in items]
    return {
        "n": len(items),
        "variable": variable,
        "statistics": list(STATS),
        "p10_p90_coverage": mean(1.0 if item.p10 <= item.observed <= item.p90 else 0.0 for item in items),
        "p10_p90_mean_width": mean(item.p90 - item.p10 for item in items),
        "p25_p75_coverage": mean(1.0 if item.p25 <= item.observed <= item.p75 else 0.0 for item in items),
        "p25_p75_mean_width": mean(item.p75 - item.p25 for item in items),
        "p50_mae": mean(abs(error) for error in errors),
        "p50_bias": mean(errors),
        "accumulation_window_minutes": 60 if variable == "precipitation_1h" else None,
        "precipitation_event_probability_supported": False,
        "full_ensemble_crps_supported": False,
    }


def _find_private_evidence(value: object, *, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            child_path = f"{path}.{key}" if path else key
            if key in PRIVATE_EVIDENCE_KEYS:
                return child_path
            found = _find_private_evidence(child, path=child_path)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_private_evidence(child, path=f"{path}[{index}]")
            if found:
                return found
    elif isinstance(value, str):
        if any(marker.lower() in value.lower() for marker in PRIVATE_VALUE_MARKERS):
            return path or "value"
    return None


def validate_first_month_evidence(evidence: Mapping[str, Any]) -> dict[str, object]:
    private = _find_private_evidence(evidence)
    if private:
        raise ValueError(f"private/restricted evidence field forbidden: {private}")
    if evidence.get("provider") != "weathernext3":
        raise ValueError("first-month evidence provider must be weathernext3")
    if evidence.get("location_id") != DWD_10416.id:
        raise ValueError("first-month evidence must use station_10416")
    if evidence.get("truth_source") != "DWD WMO 10416":
        raise ValueError("first-month evidence must use DWD WMO 10416 truth")
    if evidence.get("raw_realtime_payload_included") is not False:
        raise ValueError("raw real-time WeatherNext payload must not be included")
    if evidence.get("weather_warning_authority") is not False:
        raise ValueError("WeatherNext must not be labeled as warning authority")
    return {
        "schema_version": 1,
        "state": str(evidence.get("state") or "sample_insufficient"),
        "provider": "weathernext3",
        "location_id": DWD_10416.id,
        "truth_source": "DWD WMO 10416",
        "model_versions": list(evidence.get("model_versions") or []),
        "run_classes": list(evidence.get("run_classes") or []),
        "lead_bucket_summaries": list(evidence.get("lead_bucket_summaries") or []),
        "freshness_summary": dict(evidence.get("freshness_summary") or {}),
        "quantile_summaries": list(evidence.get("quantile_summaries") or []),
        "notable_miss_summaries": list(evidence.get("notable_miss_summaries") or []),
        "raw_realtime_payload_included": False,
        "private_fields_exposed": False,
        "publication_allowed": False,
        "terms_recheck_required_before_publication": True,
        "weather_warning_authority": False,
    }


def build_first_month_evidence(
    *,
    state: str,
    model_versions: Iterable[str],
    run_classes: Iterable[str],
    lead_bucket_summaries: Iterable[Mapping[str, Any]],
    freshness_summary: Mapping[str, Any],
    quantile_summaries: Iterable[Mapping[str, Any]],
    notable_miss_summaries: Iterable[Mapping[str, Any]] = (),
) -> dict[str, object]:
    payload = {
        "schema_version": 1,
        "state": state,
        "provider": "weathernext3",
        "location_id": DWD_10416.id,
        "truth_source": "DWD WMO 10416",
        "model_versions": sorted(set(model_versions)),
        "run_classes": sorted(set(run_classes)),
        "lead_bucket_summaries": [dict(item) for item in lead_bucket_summaries],
        "freshness_summary": dict(freshness_summary),
        "quantile_summaries": [dict(item) for item in quantile_summaries],
        "notable_miss_summaries": [dict(item) for item in notable_miss_summaries],
        "raw_realtime_payload_included": False,
        "publication_allowed": False,
        "terms_recheck_required_before_publication": True,
        "weather_warning_authority": False,
    }
    return validate_first_month_evidence(payload)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m rozkalns_weather.weathernext_collection")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="build a network-free sustained WeatherNext collection plan")
    plan.add_argument("--now", required=True)
    plan.add_argument("--known-init", action="append", default=[])
    plan.add_argument("--limit", type=int, default=24)
    validate = sub.add_parser("validate-evidence", help="validate sanitized first-month evidence from stdin")
    args = parser.parse_args()
    if args.command == "plan":
        payload = build_collection_plan(
            now=_parse_utc(args.now),
            known_init_times=[_parse_utc(value) for value in args.known_init],
            limit=args.limit,
        )
        print(json.dumps(payload, sort_keys=True, indent=2))
        return
    if args.command == "validate-evidence":
        import sys

        evidence = json.load(sys.stdin)
        if not isinstance(evidence, dict):
            raise ValueError("first-month evidence must be a JSON object")
        print(json.dumps(validate_first_month_evidence(evidence), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
