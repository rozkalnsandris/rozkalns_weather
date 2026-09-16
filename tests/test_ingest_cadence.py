from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from rozkalns_weather.ingest_cadence import (
    PUBLIC_PROVIDER_IDS,
    public_ingest_cadence_api_payload,
    public_ingest_cadence_report,
    public_ingest_schedule_contract,
)


START = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=1, minutes=30)
NOW = END + timedelta(minutes=5)
SLOTS = tuple(START + timedelta(minutes=30 * index) for index in range(3))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _success_evidence() -> list[dict[str, object]]:
    return [
        {
            "provider": provider,
            "scheduled_for_utc": _iso(slot),
            "attempted_at_utc": _iso(slot + timedelta(seconds=30)),
            "completed_at_utc": _iso(slot + timedelta(minutes=2)),
            "outcome": "success",
        }
        for provider in PUBLIC_PROVIDER_IDS
        for slot in SLOTS
    ]


def _replace(
    evidence: list[dict[str, object]],
    *,
    provider: str,
    slot: datetime,
    **changes: object,
) -> list[dict[str, object]]:
    target = (provider, _iso(slot))
    result: list[dict[str, object]] = []
    for item in evidence:
        current = (str(item["provider"]), str(item["scheduled_for_utc"]))
        result.append({**item, **changes} if current == target else dict(item))
    return result


def _report(evidence: list[dict[str, object]] | None) -> dict[str, object]:
    return public_ingest_cadence_report(
        evidence,
        window_start_utc=START,
        window_end_utc=END,
        now=NOW,
    )


def _provider(report: dict[str, object], provider: str) -> dict[str, object]:
    return next(item for item in report["providers"] if item["provider"] == provider)  # type: ignore[index]


def test_source_schedule_contract_matches_deploy_contract() -> None:
    deployed = json.loads(Path("deploy/public-ingest-schedule.json").read_text(encoding="utf-8"))
    source = public_ingest_schedule_contract()
    assert source["cadence"] == deployed["public_ingest"]["cadence"] == "PT30M"
    assert source["scheduler_owner"] == deployed["scheduler_owner"] == "RPi5_main"
    assert source["randomized_delay_seconds"] == deployed["systemd_timer"]["randomized_delay_seconds"] == 60
    assert source["accuracy_seconds"] == deployed["systemd_timer"]["accuracy_seconds"] == 60
    assert source["bounded_jitter_seconds"] == 120
    assert source["persistent"] is deployed["systemd_timer"]["persistent"] is True
    assert source["missed_run_policy"] == deployed["systemd_timer"]["missed_run_policy"]
    assert source["overlap_policy"] == deployed["public_ingest"]["overlap_policy"]
    assert source["live_timer_state_asserted"] is False


def test_conformant_cycles_pass_for_every_public_provider() -> None:
    report = _report(_success_evidence())
    assert report["state"] == "PASS"
    assert report["reason_codes"] == ["CADENCE_CONFORMANT"]
    assert report["summary"] == {
        "expected": 15,
        "attempted": 15,
        "successful": 15,
        "missed": 0,
        "overlapping": 0,
        "delayed": 0,
        "failed": 0,
        "pending": 0,
    }


def test_missed_cycle_is_blocked_and_not_confused_with_upstream_freshness() -> None:
    evidence = [
        item
        for item in _success_evidence()
        if not (item["provider"] == "icon_d2" and item["scheduled_for_utc"] == _iso(SLOTS[-1]))
    ]
    report = _report(evidence)
    icon = _provider(report, "icon_d2")
    assert report["state"] == "BLOCKED"
    assert icon["reason_code"] == "MISSED_EXPECTED_CYCLE"
    assert icon["missed"] == 1
    assert report["evidence_boundaries"]["upstream_publication_freshness_evaluated"] is False  # type: ignore[index]
    assert report["evidence_boundaries"]["provider_data_age_evaluated"] is False  # type: ignore[index]


def test_delayed_attempt_is_warn_with_bounded_jitter_semantics() -> None:
    evidence = _replace(
        _success_evidence(),
        provider="ecmwf_ifs",
        slot=SLOTS[-1],
        attempted_at_utc=_iso(SLOTS[-1] + timedelta(minutes=3)),
        completed_at_utc=_iso(SLOTS[-1] + timedelta(minutes=4)),
    )
    report = _report(evidence)
    provider = _provider(report, "ecmwf_ifs")
    assert report["state"] == "WARN"
    assert provider["reason_code"] == "DELAYED_CYCLE_ATTEMPT"
    assert provider["delayed"] == 1


def test_overlap_rejection_is_attempted_but_not_successful() -> None:
    evidence = _replace(
        _success_evidence(),
        provider="dwd_mosmix_l",
        slot=SLOTS[-1],
        outcome="overlap_rejected",
    )
    report = _report(evidence)
    provider = _provider(report, "dwd_mosmix_l")
    assert report["state"] == "WARN"
    assert provider["reason_code"] == "OVERLAP_REJECTED"
    assert provider["attempted"] == 3
    assert provider["successful"] == 2
    assert provider["overlapping"] == 1


def test_repeated_provider_failure_is_distinct_from_scheduler_miss() -> None:
    evidence = _success_evidence()
    for slot in SLOTS[-2:]:
        evidence = _replace(
            evidence,
            provider="dwd_observations",
            slot=slot,
            outcome="failure",
        )
    report = _report(evidence)
    provider = _provider(report, "dwd_observations")
    assert report["state"] == "WARN"
    assert provider["reason_code"] == "REPEATED_PROVIDER_FAILURE"
    assert provider["max_consecutive_failures"] == 2
    assert provider["missed"] == 0


def test_success_after_repeated_failure_reports_resumed_normal_operation() -> None:
    evidence = _success_evidence()
    for slot in SLOTS[:2]:
        evidence = _replace(
            evidence,
            provider="ecmwf_aifs",
            slot=slot,
            outcome="failure",
        )
    report = _report(evidence)
    provider = _provider(report, "ecmwf_aifs")
    assert report["state"] == "PASS"
    assert provider["reason_code"] == "NORMAL_OPERATION_RESUMED"
    assert provider["normal_operation_resumed"] is True
    assert provider["max_consecutive_failures"] == 2
    assert provider["successful"] == 1


def test_missing_cycle_history_fails_closed_instead_of_inventing_host_state() -> None:
    report = _report(None)
    assert report["state"] == "BLOCKED"
    assert report["reason_codes"] == ["CYCLE_HISTORY_EVIDENCE_UNAVAILABLE"]
    assert report["ledger"] == []
    assert report["schedule"]["live_timer_state_asserted"] is False  # type: ignore[index]
    assert report["evidence_boundaries"]["host_state_assumed"] is False  # type: ignore[index]


def test_api_helper_is_privacy_safe_and_truncates_ledger() -> None:
    evidence = _success_evidence()
    evidence[0]["raw_log"] = "/private/runtime/path secret-token"
    payload = public_ingest_cadence_api_payload(
        evidence,
        window_start_utc=START,
        window_end_utc=END,
        now=NOW,
        recent_cycles_per_provider=1,
    )
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["ledger_truncated"] is True
    assert len(payload["ledger"]) == len(PUBLIC_PROVIDER_IDS)
    assert payload["privacy"] == {
        "coordinates_exposed": False,
        "credentials_exposed": False,
        "runtime_paths_exposed": False,
        "raw_logs_exposed": False,
    }
    assert "/private/runtime/path" not in serialized
    assert "secret-token" not in serialized
