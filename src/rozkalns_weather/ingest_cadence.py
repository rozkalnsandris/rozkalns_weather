from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Sequence

from .models import parse_time
from .provider_health import PUBLIC_PROVIDER_HEALTH_POLICIES


CADENCE_CONTRACT = "public-ingest-cadence-v1"
CADENCE_SECONDS = 30 * 60
RANDOMIZED_DELAY_SECONDS = 60
ACCURACY_SECONDS = 60
JITTER_BUDGET_SECONDS = RANDOMIZED_DELAY_SECONDS + ACCURACY_SECONDS
PUBLIC_PROVIDER_IDS = tuple(PUBLIC_PROVIDER_HEALTH_POLICIES)
VALID_OUTCOMES = frozenset({"success", "failure", "overlap_rejected"})
_STATE_SEVERITY = {"PASS": 0, "WARN": 1, "BLOCKED": 2}


def public_ingest_schedule_contract() -> dict[str, object]:
    """Return the reviewed source contract without claiming live timer state."""

    return {
        "contract": CADENCE_CONTRACT,
        "scheduler_owner": "RPi5_main",
        "cadence": "PT30M",
        "cadence_seconds": CADENCE_SECONDS,
        "bounded_jitter_seconds": JITTER_BUDGET_SECONDS,
        "randomized_delay_seconds": RANDOMIZED_DELAY_SECONDS,
        "accuracy_seconds": ACCURACY_SECONDS,
        "persistent": True,
        "missed_run_policy": "catch_up_once_after_downtime",
        "overlap_policy": "systemd_single_oneshot_plus_application_file_lock_rejects_overlap",
        "live_timer_state_asserted": False,
        "runtime_authority_granted": False,
    }


def _utc(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        parsed = parse_time(value)
    else:
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _aligned_slot(value: datetime) -> bool:
    return value.second == 0 and value.microsecond == 0 and value.minute in {0, 30}


def _expected_slots(start: datetime, end: datetime) -> list[datetime]:
    if end <= start:
        raise ValueError("window_end_utc must be after window_start_utc")
    slot = start.replace(second=0, microsecond=0)
    remainder = slot.minute % 30
    if remainder:
        slot += timedelta(minutes=30 - remainder)
    if slot < start:
        slot += timedelta(minutes=30)
    return list(_iter_slots(slot, end))


def _iter_slots(start: datetime, end: datetime) -> Iterable[datetime]:
    cursor = start
    while cursor < end:
        yield cursor
        cursor += timedelta(seconds=CADENCE_SECONDS)


def _blocked_payload(
    *,
    start: datetime,
    end: datetime,
    now: datetime,
    reason_code: str,
) -> dict[str, object]:
    return {
        "contract": CADENCE_CONTRACT,
        "state": "BLOCKED",
        "reason_codes": [reason_code],
        "read_only": True,
        "schedule": public_ingest_schedule_contract(),
        "window": {
            "start_inclusive_utc": _iso(start),
            "end_exclusive_utc": _iso(end),
            "evaluated_at_utc": _iso(now),
        },
        "summary": {
            "expected": 0,
            "attempted": 0,
            "successful": 0,
            "missed": 0,
            "overlapping": 0,
            "delayed": 0,
            "failed": 0,
            "pending": 0,
        },
        "providers": [],
        "ledger": [],
        "evidence_boundaries": {
            "host_state_assumed": False,
            "upstream_publication_freshness_evaluated": False,
            "provider_data_age_evaluated": False,
            "application_database_cycle_history_available": False,
        },
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "runtime_paths_exposed": False,
            "raw_logs_exposed": False,
        },
    }


def public_ingest_cadence_report(
    evidence: Sequence[Mapping[str, object]] | None,
    *,
    window_start_utc: datetime | str,
    window_end_utc: datetime | str,
    now: datetime | str,
) -> dict[str, object]:
    """Build a deterministic, read-only cycle-conformance ledger.

    Evidence is sanitized and explicit: one record per provider/scheduled cycle with
    provider, scheduled_for_utc, attempted_at_utc and outcome. The helper never
    reads host/systemd state and never infers historical cycles from provider
    freshness or the latest provider_status row.
    """

    start = _utc(window_start_utc, field="window_start_utc")
    end = _utc(window_end_utc, field="window_end_utc")
    evaluated_at = _utc(now, field="now")
    slots = _expected_slots(start, end)

    if evidence is None:
        return _blocked_payload(
            start=start,
            end=end,
            now=evaluated_at,
            reason_code="CYCLE_HISTORY_EVIDENCE_UNAVAILABLE",
        )

    indexed: dict[tuple[str, str], dict[str, object]] = {}
    try:
        for raw in evidence:
            provider = str(raw.get("provider") or "")
            if provider not in PUBLIC_PROVIDER_IDS:
                raise ValueError("cycle evidence provider is outside public recurring scope")
            scheduled = _utc(raw.get("scheduled_for_utc"), field="scheduled_for_utc")
            if not _aligned_slot(scheduled):
                raise ValueError("scheduled_for_utc must align to the 00/30 minute cadence")
            if not (start <= scheduled < end):
                continue
            outcome = str(raw.get("outcome") or "")
            if outcome not in VALID_OUTCOMES:
                raise ValueError("cycle evidence outcome is unsupported")
            attempted = _utc(raw.get("attempted_at_utc"), field="attempted_at_utc")
            completed_raw = raw.get("completed_at_utc")
            completed = _utc(completed_raw, field="completed_at_utc") if completed_raw not in (None, "") else None
            if attempted < scheduled:
                raise ValueError("attempted_at_utc cannot precede scheduled_for_utc")
            if completed is not None and completed < attempted:
                raise ValueError("completed_at_utc cannot precede attempted_at_utc")
            key = (provider, _iso(scheduled))
            if key in indexed:
                raise ValueError("duplicate cycle evidence identity")
            indexed[key] = {
                "attempted_at_utc": _iso(attempted),
                "completed_at_utc": _iso(completed) if completed is not None else None,
                "outcome": outcome,
            }
    except (ValueError, TypeError):
        return _blocked_payload(
            start=start,
            end=end,
            now=evaluated_at,
            reason_code="CYCLE_EVIDENCE_INVALID",
        )

    ledger: list[dict[str, object]] = []
    by_provider: dict[str, list[dict[str, object]]] = {provider: [] for provider in PUBLIC_PROVIDER_IDS}
    jitter = timedelta(seconds=JITTER_BUDGET_SECONDS)

    for provider in PUBLIC_PROVIDER_IDS:
        for slot in slots:
            slot_iso = _iso(slot)
            record = indexed.get((provider, slot_iso))
            deadline = slot + jitter
            if record is None:
                pending = evaluated_at <= deadline
                item = {
                    "provider": provider,
                    "scheduled_for_utc": slot_iso,
                    "attempted_at_utc": None,
                    "completed_at_utc": None,
                    "outcome": None,
                    "expected": True,
                    "attempted": False,
                    "successful": False,
                    "missed": not pending,
                    "overlapping": False,
                    "delayed": False,
                    "failed": False,
                    "pending": pending,
                }
            else:
                attempted = _utc(record["attempted_at_utc"], field="attempted_at_utc")
                outcome = str(record["outcome"])
                item = {
                    "provider": provider,
                    "scheduled_for_utc": slot_iso,
                    "attempted_at_utc": record["attempted_at_utc"],
                    "completed_at_utc": record["completed_at_utc"],
                    "outcome": outcome,
                    "expected": True,
                    "attempted": True,
                    "successful": outcome == "success",
                    "missed": False,
                    "overlapping": outcome == "overlap_rejected",
                    "delayed": attempted > deadline,
                    "failed": outcome == "failure",
                    "pending": False,
                }
            ledger.append(item)
            by_provider[provider].append(item)

    provider_summaries: list[dict[str, object]] = []
    for provider, items in by_provider.items():
        mature = [item for item in items if not item["pending"]]
        missed = sum(bool(item["missed"]) for item in mature)
        overlapping = sum(bool(item["overlapping"]) for item in mature)
        delayed = sum(bool(item["delayed"]) for item in mature)
        failed = sum(bool(item["failed"]) for item in mature)
        successful = sum(bool(item["successful"]) for item in mature)
        attempted = sum(bool(item["attempted"]) for item in mature)
        pending = sum(bool(item["pending"]) for item in items)

        failure_streak = 0
        max_failure_streak = 0
        saw_failure = False
        saw_success_after_failure = False
        for item in mature:
            if item["failed"]:
                saw_failure = True
                failure_streak += 1
                max_failure_streak = max(max_failure_streak, failure_streak)
            elif item["successful"]:
                if saw_failure:
                    saw_success_after_failure = True
                failure_streak = 0
            elif item["overlapping"]:
                failure_streak = 0

        latest = mature[-1] if mature else None
        resumed = bool(
            saw_success_after_failure
            and latest is not None
            and latest["successful"]
            and not latest["delayed"]
        )

        if missed:
            state = "BLOCKED"
            reason = "MISSED_EXPECTED_CYCLE"
        elif latest is not None and latest["overlapping"]:
            state = "WARN"
            reason = "OVERLAP_REJECTED"
        elif latest is not None and latest["delayed"]:
            state = "WARN"
            reason = "DELAYED_CYCLE_ATTEMPT"
        elif latest is not None and latest["failed"] and max_failure_streak >= 2:
            state = "WARN"
            reason = "REPEATED_PROVIDER_FAILURE"
        elif latest is not None and latest["failed"]:
            state = "WARN"
            reason = "PROVIDER_CYCLE_FAILED"
        elif resumed:
            state = "PASS"
            reason = "NORMAL_OPERATION_RESUMED"
        elif mature:
            state = "PASS"
            reason = "CADENCE_CONFORMANT"
        else:
            state = "PASS"
            reason = "CYCLE_WINDOW_PENDING"

        provider_summaries.append(
            {
                "provider": provider,
                "state": state,
                "reason_code": reason,
                "expected": len(items),
                "attempted": attempted,
                "successful": successful,
                "missed": missed,
                "overlapping": overlapping,
                "delayed": delayed,
                "failed": failed,
                "pending": pending,
                "max_consecutive_failures": max_failure_streak,
                "normal_operation_resumed": resumed,
            }
        )

    state = max((str(item["state"]) for item in provider_summaries), key=lambda item: _STATE_SEVERITY[item], default="PASS")
    reason_codes = sorted({str(item["reason_code"]) for item in provider_summaries})
    summary = {
        key: sum(int(item[key]) for item in provider_summaries)
        for key in ("expected", "attempted", "successful", "missed", "overlapping", "delayed", "failed", "pending")
    }

    return {
        "contract": CADENCE_CONTRACT,
        "state": state,
        "reason_codes": reason_codes,
        "read_only": True,
        "schedule": public_ingest_schedule_contract(),
        "window": {
            "start_inclusive_utc": _iso(start),
            "end_exclusive_utc": _iso(end),
            "evaluated_at_utc": _iso(evaluated_at),
        },
        "summary": summary,
        "providers": provider_summaries,
        "ledger": ledger,
        "evidence_boundaries": {
            "host_state_assumed": False,
            "upstream_publication_freshness_evaluated": False,
            "provider_data_age_evaluated": False,
            "application_database_cycle_history_available": False,
        },
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "runtime_paths_exposed": False,
            "raw_logs_exposed": False,
        },
    }


def public_ingest_cadence_api_payload(
    evidence: Sequence[Mapping[str, object]] | None,
    *,
    window_start_utc: datetime | str,
    window_end_utc: datetime | str,
    now: datetime | str,
    recent_cycles_per_provider: int = 4,
) -> dict[str, object]:
    """Return a compact privacy-safe API surface derived from the full report."""

    if recent_cycles_per_provider < 1 or recent_cycles_per_provider > 48:
        raise ValueError("recent_cycles_per_provider must be between 1 and 48")
    report = public_ingest_cadence_report(
        evidence,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        now=now,
    )
    compact = dict(report)
    ledger = list(report["ledger"])
    recent: list[dict[str, object]] = []
    for provider in PUBLIC_PROVIDER_IDS:
        rows = [row for row in ledger if row["provider"] == provider]
        recent.extend(rows[-recent_cycles_per_provider:])
    compact["ledger"] = recent
    compact["ledger_truncated"] = len(recent) < len(ledger)
    return compact
