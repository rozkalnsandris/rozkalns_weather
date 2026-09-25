from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite
from typing import Mapping, Sequence

from .time_semantics import parse_canonical_utc, validate_utc_timestamp


TIMESTAMP_SANITY_CONTRACT = "provider-timestamp-sanity-v1"
FUTURE_TOLERANCE_SECONDS = 300.0
LOCAL_CLOCK_SKEW_TOLERANCE_SECONDS = 120.0
_STATE_SEVERITY = {"PASS": 0, "WARN": 1, "BLOCKED": 2}
_TIMESTAMP_FIELDS = (
    "init_time_utc",
    "expected_available_at_utc",
    "upstream_available_at_utc",
    "ingest_attempt_at_utc",
    "retrieved_at_utc",
    "valid_time_utc",
    "observation_time_utc",
)


class _TimestampEvidenceError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _parse_timestamp(value: object, *, required: bool = False) -> datetime | None:
    if value in (None, ""):
        if required:
            raise _TimestampEvidenceError("TIMESTAMP_EVIDENCE_MISSING")
        return None
    evidence = validate_utc_timestamp(value)
    if evidence["state"] != "PASS":
        reason = str(evidence["reason_code"])
        if reason == "TIMEZONE_NAIVE":
            raise _TimestampEvidenceError("TIMESTAMP_TIMEZONE_NAIVE")
        if reason in {"CANONICAL_TIMESTAMP_NOT_UTC", "LOCAL_TIME_PERSISTENCE_FORBIDDEN"}:
            raise _TimestampEvidenceError("TIMESTAMP_NOT_CANONICAL_UTC")
        raise _TimestampEvidenceError("TIMESTAMP_INVALID")
    return parse_canonical_utc(value)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _runtime_clock_evidence(value: Mapping[str, object] | None) -> dict[str, object]:
    if value is None:
        return {
            "state": "UNKNOWN",
            "reason_code": "RUNTIME_CLOCK_EVIDENCE_UNAVAILABLE",
            "offset_seconds": None,
            "measured_at_utc": None,
        }
    try:
        measured_at = _parse_timestamp(value.get("measured_at_utc"), required=True)
        offset = float(value.get("offset_seconds"))
    except (TypeError, ValueError, _TimestampEvidenceError):
        return {
            "state": "BLOCKED",
            "reason_code": "RUNTIME_CLOCK_EVIDENCE_INVALID",
            "offset_seconds": None,
            "measured_at_utc": None,
        }
    if not isfinite(offset):
        return {
            "state": "BLOCKED",
            "reason_code": "RUNTIME_CLOCK_EVIDENCE_INVALID",
            "offset_seconds": None,
            "measured_at_utc": None,
        }
    offset = round(offset, 3)
    if abs(offset) > LOCAL_CLOCK_SKEW_TOLERANCE_SECONDS:
        state = "WARN"
        reason_code = "LOCAL_CLOCK_SKEW_EVIDENCE"
    else:
        state = "PASS"
        reason_code = "RUNTIME_CLOCK_WITHIN_TOLERANCE"
    return {
        "state": state,
        "reason_code": reason_code,
        "offset_seconds": offset,
        "measured_at_utc": _iso(measured_at),
    }


def _blocked(reason_code: str) -> dict[str, object]:
    return {
        "contract": TIMESTAMP_SANITY_CONTRACT,
        "state": "BLOCKED",
        "reason_codes": [reason_code],
        "read_only": True,
        "future_tolerance_seconds": FUTURE_TOLERANCE_SECONDS,
        "runtime_clock": _runtime_clock_evidence(None),
        "samples": [],
        "summary": {"samples": 0, "provider_clock_suspect": 0, "local_clock_suspect": 0},
        "health_integration": {
            "affects_provider_freshness_state": False,
            "scheduler_delay_inferred": False,
            "provider_outage_claimed": False,
        },
    }


def timestamp_sanity_sample(
    raw: Mapping[str, object],
    *,
    reference_time_utc: object | None = None,
    runtime_clock_evidence: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate one timing/provenance record without mutating or inventing timestamps."""

    provider = str(raw.get("provider") or "unknown")
    model_name = str(raw.get("model_name") or "") or None
    parsed: dict[str, datetime | None] = {}
    try:
        for field in _TIMESTAMP_FIELDS:
            parsed[field] = _parse_timestamp(raw.get(field))
        reference_time = _parse_timestamp(reference_time_utc)
    except _TimestampEvidenceError as exc:
        result = _blocked(exc.reason_code)
        result.update({"provider": provider, "model_name": model_name})
        return result

    clock = _runtime_clock_evidence(runtime_clock_evidence)
    if clock["state"] == "BLOCKED":
        result = _blocked(str(clock["reason_code"]))
        result.update({"provider": provider, "model_name": model_name, "runtime_clock": clock})
        return result

    init_time = parsed["init_time_utc"]
    expected = parsed["expected_available_at_utc"]
    upstream = parsed["upstream_available_at_utc"]
    attempt = parsed["ingest_attempt_at_utc"]
    retrieved = parsed["retrieved_at_utc"]
    valid = parsed["valid_time_utc"]
    observed = parsed["observation_time_utc"]

    blocked_reasons: list[str] = []
    warn_reasons: list[str] = []
    provider_clock_suspect = False

    if expected is not None and init_time is not None and expected < init_time:
        blocked_reasons.append("EXPECTED_AVAILABILITY_BEFORE_INIT")
    if upstream is not None and init_time is not None and upstream < init_time:
        blocked_reasons.append("UPSTREAM_AVAILABILITY_BEFORE_INIT")
        provider_clock_suspect = True
    if attempt is not None and init_time is not None and attempt < init_time:
        blocked_reasons.append("INGEST_ATTEMPT_BEFORE_INIT")
    if retrieved is not None and init_time is not None and retrieved < init_time:
        blocked_reasons.append("RETRIEVAL_BEFORE_INIT")
    if attempt is not None and retrieved is not None and attempt > retrieved:
        blocked_reasons.append("INGEST_ATTEMPT_AFTER_RETRIEVAL")
    if upstream is not None and retrieved is not None and upstream > retrieved:
        blocked_reasons.append("UPSTREAM_AVAILABILITY_AFTER_RETRIEVAL")
        provider_clock_suspect = True
    if valid is not None and init_time is not None and valid < init_time:
        blocked_reasons.append("NEGATIVE_LEAD_TIME")
    if observed is not None and retrieved is not None and observed > retrieved:
        blocked_reasons.append("OBSERVATION_AFTER_RETRIEVAL")

    if upstream is None and raw.get("upstream_available_at_utc") in (None, ""):
        warn_reasons.append("UPSTREAM_AVAILABILITY_UNOBSERVED")

    if reference_time is not None:
        future_bound = reference_time + timedelta(seconds=FUTURE_TOLERANCE_SECONDS)
        if retrieved is not None and retrieved > future_bound:
            blocked_reasons.append("RETRIEVAL_FUTURE_BEYOND_TOLERANCE")
        if attempt is not None and attempt > future_bound:
            blocked_reasons.append("INGEST_ATTEMPT_FUTURE_BEYOND_TOLERANCE")
        if observed is not None and observed > future_bound:
            blocked_reasons.append("OBSERVATION_FUTURE_BEYOND_TOLERANCE")
        if upstream is not None and upstream > future_bound:
            blocked_reasons.append("UPSTREAM_AVAILABILITY_FUTURE_BEYOND_TOLERANCE")
            provider_clock_suspect = True

    if clock["state"] == "WARN":
        warn_reasons.append(str(clock["reason_code"]))

    blocked_reasons = sorted(set(blocked_reasons))
    warn_reasons = sorted(set(warn_reasons))
    if blocked_reasons:
        state = "BLOCKED"
        reasons = blocked_reasons + warn_reasons
    elif warn_reasons:
        state = "WARN"
        reasons = warn_reasons
    else:
        state = "PASS"
        reasons = ["TIMESTAMP_SANITY_OK"]

    lead_hours = None
    if init_time is not None and valid is not None:
        lead_hours = round((valid - init_time).total_seconds() / 3600.0, 3)

    normalized = {field: _iso(value) for field, value in parsed.items()}
    return {
        "contract": TIMESTAMP_SANITY_CONTRACT,
        "state": state,
        "reason_codes": reasons,
        "read_only": True,
        "provider": provider,
        "model_name": model_name,
        "timestamps": normalized,
        "lead_time_hours": lead_hours,
        "reference_clock": {
            "state": "EXPLICIT" if reference_time is not None else "UNKNOWN",
            "reason_code": "REFERENCE_TIME_EXPLICIT" if reference_time is not None else "REFERENCE_TIME_EVIDENCE_UNAVAILABLE",
            "reference_time_utc": _iso(reference_time),
            "future_tolerance_seconds": FUTURE_TOLERANCE_SECONDS,
        },
        "runtime_clock": clock,
        "clock_skew": {
            "provider_evidence": "SUSPECT" if provider_clock_suspect else "NOT_DETECTED",
            "local_evidence": "SUSPECT" if clock["state"] == "WARN" else ("UNKNOWN" if clock["state"] == "UNKNOWN" else "NOT_DETECTED"),
        },
        "availability_semantics": {
            "expected_is_documented_or_planned_target": expected is not None,
            "upstream_is_observed_evidence": upstream is not None,
            "upstream_timestamp_fabricated": False,
        },
        "stored_provenance_rewritten": False,
        "scheduler_delay_inferred": False,
        "provider_outage_claimed": False,
    }


def provider_timestamp_sanity_report(
    evidence: Sequence[Mapping[str, object]] | None,
    *,
    reference_time_utc: object | None = None,
    runtime_clock_evidence: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build deterministic read-only timestamp-sanity evidence for provider/report consumers."""

    if evidence is None or len(evidence) == 0:
        return _blocked("TIMESTAMP_EVIDENCE_UNAVAILABLE")
    samples = [
        timestamp_sanity_sample(
            raw,
            reference_time_utc=reference_time_utc,
            runtime_clock_evidence=runtime_clock_evidence,
        )
        for raw in evidence
    ]
    states = [str(sample["state"]) for sample in samples]
    state = max(states, key=lambda item: _STATE_SEVERITY[item])
    reasons = sorted({reason for sample in samples for reason in sample["reason_codes"]})
    clock = _runtime_clock_evidence(runtime_clock_evidence)
    return {
        "contract": TIMESTAMP_SANITY_CONTRACT,
        "state": state,
        "reason_codes": reasons,
        "read_only": True,
        "future_tolerance_seconds": FUTURE_TOLERANCE_SECONDS,
        "runtime_clock": clock,
        "reference_time_state": "EXPLICIT" if reference_time_utc not in (None, "") else "UNKNOWN",
        "samples": samples,
        "summary": {
            "samples": len(samples),
            "provider_clock_suspect": sum(sample["clock_skew"]["provider_evidence"] == "SUSPECT" for sample in samples if "clock_skew" in sample),
            "local_clock_suspect": sum(sample["clock_skew"]["local_evidence"] == "SUSPECT" for sample in samples if "clock_skew" in sample),
        },
        "health_integration": {
            "affects_provider_freshness_state": False,
            "scheduler_delay_inferred": False,
            "provider_outage_claimed": False,
        },
    }


def provider_health_timestamp_sanity_summary(report: Mapping[str, object], provider: str) -> dict[str, object]:
    """Return provider-scoped timing evidence without reclassifying freshness or outage state."""

    samples = [
        sample
        for sample in report.get("samples", [])
        if isinstance(sample, Mapping) and sample.get("provider") == provider
    ]
    if not samples:
        return {
            "contract": TIMESTAMP_SANITY_CONTRACT,
            "state": "BLOCKED",
            "reason_codes": ["PROVIDER_TIMESTAMP_EVIDENCE_UNAVAILABLE"],
            "runtime_clock": report.get("runtime_clock", _runtime_clock_evidence(None)),
            "samples": [],
            "affects_provider_freshness_state": False,
            "scheduler_delay_inferred": False,
            "provider_outage_claimed": False,
        }
    states = [str(sample.get("state") or "BLOCKED") for sample in samples]
    return {
        "contract": TIMESTAMP_SANITY_CONTRACT,
        "state": max(states, key=lambda item: _STATE_SEVERITY[item]),
        "reason_codes": sorted({reason for sample in samples for reason in sample.get("reason_codes", [])}),
        "runtime_clock": report.get("runtime_clock", _runtime_clock_evidence(None)),
        "samples": samples,
        "affects_provider_freshness_state": False,
        "scheduler_delay_inferred": False,
        "provider_outage_claimed": False,
    }
