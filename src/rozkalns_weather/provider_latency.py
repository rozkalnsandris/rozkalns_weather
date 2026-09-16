from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import ceil
from typing import Mapping, Sequence


LATENCY_CONTRACT = "provider-availability-latency-v1"
PUBLIC_FORECAST_PROVIDERS = (
    "dwd_mosmix_l",
    "icon_d2",
    "ecmwf_ifs",
    "ecmwf_aifs",
)
UPSTREAM_LATE_AFTER_MINUTES = 30.0
LOCAL_ATTEMPT_LATE_AFTER_MINUTES = 30.0
RETRIEVAL_LATE_AFTER_MINUTES = 60.0
_STATE_SEVERITY = {"PASS": 0, "WARN": 1, "BLOCKED": 2}


class _EvidenceError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _utc(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise _EvidenceError("LATENCY_EVIDENCE_INVALID") from exc
    else:
        raise _EvidenceError("LATENCY_EVIDENCE_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _EvidenceError("LATENCY_TIMESTAMP_NOT_UTC")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _minutes(later: datetime, earlier: datetime) -> float:
    return round((later - earlier).total_seconds() / 60.0, 3)


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return round(float(ordered[index]), 3)


def _distribution(values: Sequence[float]) -> dict[str, object]:
    return {
        "n": len(values),
        "p50_minutes": _percentile(values, 0.50),
        "p95_minutes": _percentile(values, 0.95),
        "max_minutes": round(max(values), 3) if values else None,
    }


def _blocked(reason_code: str) -> dict[str, object]:
    return {
        "contract": LATENCY_CONTRACT,
        "state": "BLOCKED",
        "reason_codes": [reason_code],
        "read_only": True,
        "thresholds": {
            "upstream_late_after_minutes": UPSTREAM_LATE_AFTER_MINUTES,
            "local_attempt_late_after_minutes": LOCAL_ATTEMPT_LATE_AFTER_MINUTES,
            "retrieval_late_after_minutes": RETRIEVAL_LATE_AFTER_MINUTES,
        },
        "summary": {"samples": 0, "upstream_observed_samples": 0},
        "groups": [],
        "samples": [],
        "health_integration": {
            "affects_provider_freshness_state": False,
            "outage_claimed": False,
        },
    }


def _normalize(raw: Mapping[str, object]) -> dict[str, object]:
    provider = str(raw.get("provider") or "")
    model_name = str(raw.get("model_name") or "")
    run_cycle = str(raw.get("run_cycle") or "")
    expected_source = str(raw.get("expected_availability_source") or "")
    if provider not in PUBLIC_FORECAST_PROVIDERS or not model_name or not run_cycle or not expected_source:
        raise _EvidenceError("LATENCY_EVIDENCE_INVALID")

    init_time = _utc(raw.get("init_time_utc"), field="init_time_utc")
    expected = _utc(raw.get("expected_available_at_utc"), field="expected_available_at_utc")
    retrieved = _utc(raw.get("retrieved_at_utc"), field="retrieved_at_utc")
    attempt = _utc(raw.get("ingest_attempt_at_utc"), field="ingest_attempt_at_utc")

    upstream_raw = raw.get("upstream_available_at_utc")
    upstream = None if upstream_raw in (None, "") else _utc(upstream_raw, field="upstream_available_at_utc")
    upstream_source = str(raw.get("upstream_availability_source") or "") or None
    if upstream is not None and upstream_source is None:
        raise _EvidenceError("LATENCY_EVIDENCE_INVALID")
    if upstream is None and upstream_source is not None:
        raise _EvidenceError("LATENCY_EVIDENCE_INVALID")

    if expected < init_time or retrieved < init_time or attempt < init_time or attempt > retrieved:
        raise _EvidenceError("TIMESTAMP_ORDER_INVALID")
    if upstream is not None and (upstream < init_time or upstream > retrieved):
        raise _EvidenceError("TIMESTAMP_ORDER_INVALID")

    reasons: list[str] = []
    if upstream is None:
        reasons.append("UPSTREAM_AVAILABILITY_UNOBSERVED")
    elif _minutes(upstream, expected) > UPSTREAM_LATE_AFTER_MINUTES:
        reasons.append("UPSTREAM_AVAILABILITY_LATE")

    if upstream is not None and _minutes(attempt, upstream) > LOCAL_ATTEMPT_LATE_AFTER_MINUTES:
        reasons.append("LOCAL_RETRIEVAL_ATTEMPT_LATE")
    if _minutes(retrieved, expected) > RETRIEVAL_LATE_AFTER_MINUTES:
        reasons.append("RETRIEVAL_LATE")

    state = "WARN" if reasons else "PASS"
    if not reasons:
        reasons = ["LATENCY_WITHIN_BOUNDS"]

    return {
        "provider": provider,
        "model_name": model_name,
        "model_version": raw.get("model_version"),
        "run_cycle": run_cycle,
        "init_time_utc": _iso(init_time),
        "expected_available_at_utc": _iso(expected),
        "expected_availability_source": expected_source,
        "upstream_available_at_utc": _iso(upstream) if upstream is not None else None,
        "upstream_availability_source": upstream_source,
        "retrieved_at_utc": _iso(retrieved),
        "ingest_attempt_at_utc": _iso(attempt),
        "state": state,
        "reason_codes": reasons,
        "latency_minutes": {
            "init_to_expected": _minutes(expected, init_time),
            "init_to_upstream": _minutes(upstream, init_time) if upstream is not None else None,
            "expected_to_upstream": _minutes(upstream, expected) if upstream is not None else None,
            "expected_to_retrieval": _minutes(retrieved, expected),
            "upstream_to_local_attempt": _minutes(attempt, upstream) if upstream is not None else None,
            "ingest_attempt_to_retrieval": _minutes(retrieved, attempt),
        },
        "provenance": {
            "expected_is_documented_or_planned_target": True,
            "upstream_is_observed_evidence": upstream is not None,
            "upstream_timestamp_fabricated": False,
        },
        "outage_claimed": False,
    }


def provider_latency_report(evidence: Sequence[Mapping[str, object]] | None) -> dict[str, object]:
    """Build a deterministic read-only latency benchmark from explicit provenance evidence."""

    if evidence is None or len(evidence) == 0:
        return _blocked("LATENCY_EVIDENCE_UNAVAILABLE")

    try:
        samples = [_normalize(raw) for raw in evidence]
    except _EvidenceError as exc:
        return _blocked(exc.reason_code)
    except (TypeError, ValueError):
        return _blocked("LATENCY_EVIDENCE_INVALID")

    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for sample in samples:
        grouped[(str(sample["provider"]), str(sample["model_name"]), str(sample["run_cycle"]))].append(sample)

    groups: list[dict[str, object]] = []
    for (provider, model_name, run_cycle), items in sorted(grouped.items()):
        states = [str(item["state"]) for item in items]
        state = max(states, key=lambda item: _STATE_SEVERITY[item])
        reasons = sorted({reason for item in items for reason in item["reason_codes"]})
        observed = [item for item in items if item["upstream_available_at_utc"] is not None]
        expected_to_retrieval = [float(item["latency_minutes"]["expected_to_retrieval"]) for item in items]
        expected_to_upstream = [
            float(item["latency_minutes"]["expected_to_upstream"])
            for item in observed
            if item["latency_minutes"]["expected_to_upstream"] is not None
        ]
        upstream_to_attempt = [
            float(item["latency_minutes"]["upstream_to_local_attempt"])
            for item in observed
            if item["latency_minutes"]["upstream_to_local_attempt"] is not None
        ]
        attempt_to_retrieval = [float(item["latency_minutes"]["ingest_attempt_to_retrieval"]) for item in items]
        groups.append(
            {
                "provider": provider,
                "model_name": model_name,
                "run_cycle": run_cycle,
                "state": state,
                "reason_codes": reasons,
                "samples": len(items),
                "upstream_observed_samples": len(observed),
                "distributions": {
                    "expected_to_upstream": _distribution(expected_to_upstream),
                    "expected_to_retrieval": _distribution(expected_to_retrieval),
                    "upstream_to_local_attempt": _distribution(upstream_to_attempt),
                    "ingest_attempt_to_retrieval": _distribution(attempt_to_retrieval),
                },
                "outage_claimed": False,
            }
        )

    states = [str(group["state"]) for group in groups]
    state = max(states, key=lambda item: _STATE_SEVERITY[item])
    reasons = sorted({reason for group in groups for reason in group["reason_codes"]})
    return {
        "contract": LATENCY_CONTRACT,
        "state": state,
        "reason_codes": reasons,
        "read_only": True,
        "thresholds": {
            "upstream_late_after_minutes": UPSTREAM_LATE_AFTER_MINUTES,
            "local_attempt_late_after_minutes": LOCAL_ATTEMPT_LATE_AFTER_MINUTES,
            "retrieval_late_after_minutes": RETRIEVAL_LATE_AFTER_MINUTES,
        },
        "summary": {
            "samples": len(samples),
            "upstream_observed_samples": sum(sample["upstream_available_at_utc"] is not None for sample in samples),
        },
        "groups": groups,
        "samples": samples,
        "health_integration": {
            "affects_provider_freshness_state": False,
            "outage_claimed": False,
        },
    }


def provider_health_latency_summary(report: Mapping[str, object], provider: str) -> dict[str, object]:
    """Return a compact latency surface that provider-health may expose without reclassifying health."""

    groups = [
        group
        for group in report.get("groups", [])
        if isinstance(group, Mapping) and group.get("provider") == provider
    ]
    if not groups:
        return {
            "contract": LATENCY_CONTRACT,
            "state": "BLOCKED",
            "reason_codes": ["PROVIDER_LATENCY_EVIDENCE_UNAVAILABLE"],
            "groups": [],
            "affects_provider_freshness_state": False,
            "outage_claimed": False,
        }
    states = [str(group.get("state") or "BLOCKED") for group in groups]
    return {
        "contract": LATENCY_CONTRACT,
        "state": max(states, key=lambda item: _STATE_SEVERITY[item]),
        "reason_codes": sorted({reason for group in groups for reason in group.get("reason_codes", [])}),
        "groups": groups,
        "affects_provider_freshness_state": False,
        "outage_claimed": False,
    }
