from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from .models import parse_time


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    source_fresh_hours: float
    source_stale_hours: float


# Public recurring ingest runs every 30 minutes with <=60 seconds jitter. Two hours
# allows several missed cycles before the local scheduler/ingest path is called stale.
SCHEDULER_STALE_AFTER_HOURS = 2.0

PUBLIC_PROVIDER_HEALTH_POLICIES: dict[str, FreshnessPolicy] = {
    "dwd_observations": FreshnessPolicy(source_fresh_hours=2.0, source_stale_hours=4.0),
    "dwd_mosmix_l": FreshnessPolicy(source_fresh_hours=8.0, source_stale_hours=14.0),
    "icon_d2": FreshnessPolicy(source_fresh_hours=4.5, source_stale_hours=8.0),
    "ecmwf_ifs": FreshnessPolicy(source_fresh_hours=8.0, source_stale_hours=14.0),
    "ecmwf_aifs": FreshnessPolicy(source_fresh_hours=8.0, source_stale_hours=14.0),
}


def _age_hours(value: object, *, now: datetime) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    timestamp = parse_time(value)
    return max(0.0, (now - timestamp).total_seconds() / 3600.0)


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def _failure_domain_from_detail(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    domains: set[str] = set()
    for item in value.split(";"):
        for token in item.split(":"):
            if token in {"upstream_or_transport", "local_persistence"}:
                domains.add(token)
    if not domains:
        return None
    if len(domains) > 1:
        return "mixed"
    return next(iter(domains))


def _reason_for_recent_failure(*, partial: bool, failure_domain: str) -> str:
    if partial:
        return {
            "upstream_or_transport": "PARTIAL_INGEST_UPSTREAM_OR_TRANSPORT",
            "local_persistence": "PARTIAL_INGEST_LOCAL_PERSISTENCE",
            "mixed": "PARTIAL_INGEST_MIXED_FAILURES",
        }.get(failure_domain, "PARTIAL_INGEST_UNCLASSIFIED")
    return {
        "upstream_or_transport": "RECENT_UPSTREAM_OR_TRANSPORT_ERROR",
        "local_persistence": "RECENT_LOCAL_PERSISTENCE_ERROR",
        "mixed": "RECENT_MIXED_INGEST_ERROR",
    }.get(failure_domain, "RECENT_INGEST_ERROR_UNCLASSIFIED")


def classify_public_provider_health(
    provider: str,
    saved: Mapping[str, object] | None,
    evidence: Mapping[str, object] | None,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    if provider not in PUBLIC_PROVIDER_HEALTH_POLICIES:
        raise ValueError(f"provider is not in public recurring health scope: {provider}")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    saved = saved or {}
    evidence = evidence or {}
    policy = PUBLIC_PROVIDER_HEALTH_POLICIES[provider]

    last_attempt = saved.get("last_attempt_at_utc")
    last_success = saved.get("last_success_at_utc")
    last_init = evidence.get("last_init_time_utc") or saved.get("last_init_time_utc")
    last_retrieved = evidence.get("last_retrieved_at_utc")
    latest_valid = evidence.get("latest_valid_time_utc")
    last_observed = evidence.get("last_observed_at_utc")
    source_time = last_observed if provider == "dwd_observations" else last_init

    attempt_age = _age_hours(last_attempt, now=now)
    success_age = _age_hours(last_success, now=now)
    source_age = _age_hours(source_time, now=now)
    ingest_state = str(saved.get("state") or "adapter_ready_not_ingested")
    recorded_failure_domain = _failure_domain_from_detail(saved.get("detail"))

    freshness_state = "fresh"
    failure_domain = "none"
    reason_code = "FRESH"

    if last_attempt is None:
        freshness_state = "not_ingested"
        failure_domain = "local_ingest_not_started"
        reason_code = "NO_INGEST_ATTEMPT"
    elif attempt_age is not None and attempt_age > SCHEDULER_STALE_AFTER_HOURS:
        freshness_state = "stale"
        failure_domain = "local_scheduler_or_ingest"
        reason_code = "INGEST_ATTEMPT_STALE"
    elif ingest_state == "error":
        freshness_state = "error"
        failure_domain = recorded_failure_domain or "unknown_ingest_error"
        reason_code = _reason_for_recent_failure(partial=False, failure_domain=failure_domain)
    elif ingest_state == "partial":
        freshness_state = "degraded"
        failure_domain = recorded_failure_domain or "unknown_ingest_error"
        reason_code = _reason_for_recent_failure(partial=True, failure_domain=failure_domain)
    elif last_success is None:
        freshness_state = "error"
        failure_domain = "local_ingest"
        reason_code = "NO_SUCCESSFUL_INGEST"
    elif success_age is not None and success_age > SCHEDULER_STALE_AFTER_HOURS:
        freshness_state = "stale"
        failure_domain = "local_scheduler_or_ingest"
        reason_code = "INGEST_SUCCESS_STALE"
    elif source_age is None:
        freshness_state = "unknown"
        failure_domain = "provenance"
        reason_code = "SOURCE_TIME_MISSING"
    elif source_age > policy.source_stale_hours:
        freshness_state = "stale"
        failure_domain = "upstream_data"
        reason_code = "SOURCE_DATA_STALE"
    elif source_age > policy.source_fresh_hours:
        freshness_state = "lagging"
        failure_domain = "upstream_data"
        reason_code = "SOURCE_DATA_LAGGING"

    return {
        "tracked": True,
        "ingest_state": ingest_state,
        "freshness_state": freshness_state,
        "failure_domain": failure_domain,
        "reason_code": reason_code,
        "last_attempt_at_utc": last_attempt,
        "last_success_at_utc": last_success,
        "last_init_time_utc": last_init,
        "last_retrieved_at_utc": last_retrieved,
        "latest_valid_time_utc": latest_valid,
        "last_observed_at_utc": last_observed,
        "attempt_age_hours": _rounded(attempt_age),
        "success_age_hours": _rounded(success_age),
        "source_age_hours": _rounded(source_age),
        "scheduler_stale_after_hours": SCHEDULER_STALE_AFTER_HOURS,
        "source_fresh_after_hours": policy.source_fresh_hours,
        "source_stale_after_hours": policy.source_stale_hours,
        "detail": saved.get("detail"),
    }
