from __future__ import annotations

import json
from pathlib import Path

import pytest

from rozkalns_weather.query_bounds import (
    CONTRACT,
    DEFAULT_PAGE_SIZE,
    MAX_HOURLY_HOURS,
    MAX_PAGE_SIZE,
    MAX_PROVIDER_SELECTIONS,
    MAX_REPORT_WINDOW_DAYS,
    MAX_RESPONSE_BYTES,
    MAX_VERIFICATION_DAYS,
    QueryGuardError,
    blocked_query_response,
    bounded_integer,
    bounded_page_size,
    ensure_response_size,
    limits,
    paginate_rows,
    parse_selection,
    query_identity,
    snapshot_identity,
    validate_date_window,
)


def _rows(count: int = 5) -> list[dict[str, object]]:
    return [
        {
            "provider": "icon_d2" if index % 2 == 0 else "ecmwf_ifs",
            "model_name": "fixture",
            "model_version": "v1",
            "init_time_utc": "2026-09-01T00:00:00Z",
            "retrieved_at_utc": "2026-09-01T01:00:00Z",
            "valid_time_utc": f"2026-09-01T{index:02d}:00:00Z",
            "variable": "temperature_2m",
            "statistic": "deterministic",
            "value": float(index),
            "unit": "degC",
        }
        for index in range(count)
    ]


def test_machine_contract_matches_source_limits() -> None:
    path = Path(__file__).resolve().parents[1] / "contracts" / "api-query-bounds-v1.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    assert contract["contract"] == CONTRACT
    assert contract["limits"] == limits()
    assert contract["continuation"]["silent_truncation"] is False
    assert contract["authority"]["production_schema_or_index_mutation_authority_granted"] is False
    assert contract["authority"]["runtime_live_authority_granted"] is False


def test_normal_and_maximum_boundaries_are_accepted() -> None:
    assert bounded_integer("hours", 48, minimum=1, maximum=MAX_HOURLY_HOURS) == 48
    assert bounded_integer("hours", MAX_HOURLY_HOURS, minimum=1, maximum=MAX_HOURLY_HOURS) == MAX_HOURLY_HOURS
    assert bounded_integer("days", MAX_VERIFICATION_DAYS, minimum=1, maximum=MAX_VERIFICATION_DAYS) == MAX_VERIFICATION_DAYS
    assert bounded_page_size(DEFAULT_PAGE_SIZE) == DEFAULT_PAGE_SIZE
    assert bounded_page_size(MAX_PAGE_SIZE) == MAX_PAGE_SIZE


def test_over_limit_and_invalid_ranges_have_stable_reason_codes() -> None:
    with pytest.raises(QueryGuardError) as error:
        bounded_integer("hours", MAX_HOURLY_HOURS + 1, minimum=1, maximum=MAX_HOURLY_HOURS)
    assert error.value.reason_code == "QUERY_WINDOW_TOO_LARGE"

    with pytest.raises(QueryGuardError) as error:
        bounded_integer("hours", 0, minimum=1, maximum=MAX_HOURLY_HOURS)
    assert error.value.reason_code == "INVALID_QUERY_RANGE"

    with pytest.raises(QueryGuardError) as error:
        bounded_page_size(MAX_PAGE_SIZE + 1)
    assert error.value.reason_code == "PAGE_SIZE_TOO_LARGE"


def test_invalid_and_oversized_report_windows_fail_closed() -> None:
    assert validate_date_window(
        "2026-09-01T00:00:00Z",
        "2026-10-01T00:00:00Z",
        max_days=MAX_REPORT_WINDOW_DAYS,
    ) == 30 * 86400

    with pytest.raises(QueryGuardError) as error:
        validate_date_window("2026-09-02T00:00:00Z", "2026-09-01T00:00:00Z")
    assert error.value.reason_code == "INVALID_QUERY_WINDOW"

    with pytest.raises(QueryGuardError) as error:
        validate_date_window("2026-09-01T00:00:00Z", "2026-10-03T00:00:00Z")
    assert error.value.reason_code == "QUERY_WINDOW_TOO_LARGE"


def test_multi_provider_selection_is_canonical_and_breadth_limited() -> None:
    assert parse_selection("ecmwf_ifs,icon_d2,ecmwf_ifs", kind="provider") == (
        "ecmwf_ifs",
        "icon_d2",
    )
    oversized = ",".join(f"provider_{index}" for index in range(MAX_PROVIDER_SELECTIONS + 1))
    with pytest.raises(QueryGuardError) as error:
        parse_selection(oversized, kind="provider")
    assert error.value.reason_code == "SELECTION_TOO_BROAD"


def test_deterministic_continuation_preserves_completeness_metadata() -> None:
    rows = _rows(5)
    query_sha = query_identity(
        {
            "endpoint": "/api/hourly",
            "hours": 48,
            "variable": "temperature_2m",
            "location_id": "station_05480",
            "providers": ["ecmwf_ifs", "icon_d2"],
            "model_versions": [],
        }
    )
    snapshot_sha = snapshot_identity(rows)

    first, first_meta = paginate_rows(
        rows,
        page_size=2,
        query_identity_sha256=query_sha,
        snapshot_identity_sha256=snapshot_sha,
    )
    repeat, repeat_meta = paginate_rows(
        rows,
        page_size=2,
        query_identity_sha256=query_sha,
        snapshot_identity_sha256=snapshot_sha,
    )
    assert first == repeat
    assert first_meta == repeat_meta
    assert first_meta["total_rows"] == 5
    assert first_meta["returned_rows"] == 2
    assert first_meta["complete"] is False
    assert first_meta["next_cursor"]

    second, second_meta = paginate_rows(
        rows,
        page_size=2,
        query_identity_sha256=query_sha,
        snapshot_identity_sha256=snapshot_sha,
        cursor=str(first_meta["next_cursor"]),
    )
    third, third_meta = paginate_rows(
        rows,
        page_size=2,
        query_identity_sha256=query_sha,
        snapshot_identity_sha256=snapshot_sha,
        cursor=str(second_meta["next_cursor"]),
    )
    assert first + second + third == rows
    assert second_meta["offset"] == 2
    assert third_meta["offset"] == 4
    assert third_meta["complete"] is True
    assert third_meta["next_cursor"] is None


def test_cursor_rejects_query_or_snapshot_drift() -> None:
    rows = _rows(3)
    query_sha = query_identity({"endpoint": "/api/hourly", "hours": 48})
    snapshot_sha = snapshot_identity(rows)
    _, meta = paginate_rows(
        rows,
        page_size=1,
        query_identity_sha256=query_sha,
        snapshot_identity_sha256=snapshot_sha,
    )
    cursor = str(meta["next_cursor"])

    with pytest.raises(QueryGuardError) as error:
        paginate_rows(
            rows,
            page_size=1,
            query_identity_sha256=query_identity({"endpoint": "/api/hourly", "hours": 24}),
            snapshot_identity_sha256=snapshot_sha,
            cursor=cursor,
        )
    assert error.value.reason_code == "CURSOR_QUERY_MISMATCH"

    changed = list(rows)
    changed[0] = {**changed[0], "value": 99.0}
    with pytest.raises(QueryGuardError) as error:
        paginate_rows(
            changed,
            page_size=1,
            query_identity_sha256=query_sha,
            snapshot_identity_sha256=snapshot_identity(changed),
            cursor=cursor,
        )
    assert error.value.reason_code == "CURSOR_SNAPSHOT_MISMATCH"
    assert error.value.status_code == 409


def test_response_byte_guard_and_blocked_envelope_are_fail_closed() -> None:
    assert ensure_response_size({"ok": True}) < MAX_RESPONSE_BYTES
    with pytest.raises(QueryGuardError) as error:
        ensure_response_size({"payload": "x" * (MAX_RESPONSE_BYTES + 1)})
    assert error.value.reason_code == "RESPONSE_PAYLOAD_TOO_LARGE"
    assert error.value.status_code == 413

    blocked = blocked_query_response(error.value)
    assert blocked["state"] == "BLOCKED"
    assert blocked["reason_codes"] == ["RESPONSE_PAYLOAD_TOO_LARGE"]
    assert blocked["privacy"]["request_values_echoed"] is False
    assert "x" * 100 not in json.dumps(blocked)
