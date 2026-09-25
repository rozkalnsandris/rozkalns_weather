from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from typing import Mapping, Sequence

from .canonical_serialization import CanonicalSerializationError, canonical_sha256

CONTRACT = "api-query-bounds-v1"
SCHEMA_VERSION = 1

MAX_HOURLY_HOURS = 360
MAX_DAILY_DAYS = 15
MAX_VERIFICATION_DAYS = 366
MAX_REPORT_WINDOW_DAYS = 31
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 200
MAX_PROVIDER_SELECTIONS = 8
MAX_MODEL_SELECTIONS = 8
MAX_HOURLY_SOURCE_ROWS = 5_000
MAX_VERIFICATION_SAMPLES = 50_000
MAX_RESPONSE_BYTES = 512 * 1024


class QueryGuardError(ValueError):
    def __init__(self, reason_code: str, detail: str, *, status_code: int = 422) -> None:
        super().__init__(detail)
        self.reason_code = reason_code
        self.status_code = status_code


def limits() -> dict[str, int]:
    return {
        "max_hourly_hours": MAX_HOURLY_HOURS,
        "max_daily_days": MAX_DAILY_DAYS,
        "max_verification_days": MAX_VERIFICATION_DAYS,
        "max_report_window_days": MAX_REPORT_WINDOW_DAYS,
        "default_page_size": DEFAULT_PAGE_SIZE,
        "max_page_size": MAX_PAGE_SIZE,
        "max_provider_selections": MAX_PROVIDER_SELECTIONS,
        "max_model_selections": MAX_MODEL_SELECTIONS,
        "max_hourly_source_rows": MAX_HOURLY_SOURCE_ROWS,
        "max_verification_samples": MAX_VERIFICATION_SAMPLES,
        "max_response_bytes": MAX_RESPONSE_BYTES,
    }


def blocked_query_response(exc: QueryGuardError) -> dict[str, object]:
    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "state": "BLOCKED",
        "reason_codes": [exc.reason_code],
        "limits": limits(),
        "privacy": {
            "request_values_echoed": False,
            "coordinates_exposed": False,
            "database_path_exposed": False,
            "credentials_exposed": False,
            "raw_logs_exposed": False,
        },
    }


def bounded_integer(name: str, value: int, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QueryGuardError("INVALID_QUERY_RANGE", f"{name} must be an integer")
    if value < minimum:
        raise QueryGuardError("INVALID_QUERY_RANGE", f"{name} is below the supported minimum")
    if value > maximum:
        raise QueryGuardError("QUERY_WINDOW_TOO_LARGE", f"{name} exceeds the supported maximum")
    return value


def bounded_page_size(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise QueryGuardError("INVALID_PAGE_SIZE", "page_size must be a positive integer")
    if value > MAX_PAGE_SIZE:
        raise QueryGuardError("PAGE_SIZE_TOO_LARGE", "page_size exceeds the response envelope")
    return value


def parse_selection(raw: str | None, *, kind: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    values = [item.strip() for item in raw.split(",")]
    if not values or any(not item for item in values):
        raise QueryGuardError("INVALID_SELECTION", f"{kind} selection contains an empty value")
    if any(len(item) > 96 for item in values):
        raise QueryGuardError("INVALID_SELECTION", f"{kind} selection contains an oversized identifier")
    normalized = tuple(sorted(set(values)))
    maximum = MAX_PROVIDER_SELECTIONS if kind == "provider" else MAX_MODEL_SELECTIONS
    if len(normalized) > maximum:
        raise QueryGuardError("SELECTION_TOO_BROAD", f"{kind} selection exceeds the supported breadth")
    return normalized


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QueryGuardError("INVALID_QUERY_WINDOW", "window timestamps must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise QueryGuardError("INVALID_QUERY_WINDOW", "window timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def validate_date_window(start_utc: str, end_utc: str, *, max_days: int = MAX_REPORT_WINDOW_DAYS) -> int:
    start = _utc(start_utc)
    end = _utc(end_utc)
    if end <= start:
        raise QueryGuardError("INVALID_QUERY_WINDOW", "window end must be after start")
    seconds = (end - start).total_seconds()
    if seconds > max_days * 86400:
        raise QueryGuardError("QUERY_WINDOW_TOO_LARGE", "window exceeds the supported duration")
    return int(seconds)


def enforce_sample_count(count: int, *, maximum: int, reason_code: str = "SAMPLE_COUNT_TOO_LARGE") -> int:
    if count < 0:
        raise QueryGuardError("INVALID_SAMPLE_COUNT", "sample count cannot be negative")
    if count > maximum:
        raise QueryGuardError(reason_code, "query sample count exceeds the supported envelope")
    return count


def query_identity(query: Mapping[str, object]) -> str:
    try:
        return canonical_sha256({"contract": CONTRACT, "query": dict(query)})
    except CanonicalSerializationError as exc:
        raise QueryGuardError("INVALID_QUERY_IDENTITY", "query inputs are not canonical") from exc


def snapshot_identity(rows: Sequence[Mapping[str, object]]) -> str:
    identity_rows = [
        {
            "provider": row.get("provider"),
            "model_name": row.get("model_name"),
            "model_version": row.get("model_version"),
            "init_time_utc": row.get("init_time_utc"),
            "retrieved_at_utc": row.get("retrieved_at_utc"),
            "valid_time_utc": row.get("valid_time_utc"),
            "variable": row.get("variable"),
            "statistic": row.get("statistic"),
            "value": row.get("value"),
            "unit": row.get("unit"),
        }
        for row in rows
    ]
    try:
        return canonical_sha256(identity_rows)
    except CanonicalSerializationError as exc:
        raise QueryGuardError("INVALID_QUERY_SNAPSHOT", "query result identity is not canonical") from exc


def _encode_cursor(payload: Mapping[str, object]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, object]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise QueryGuardError("INVALID_CURSOR", "cursor is not a supported continuation token") from exc
    if not isinstance(payload, dict):
        raise QueryGuardError("INVALID_CURSOR", "cursor payload must be an object")
    return payload


def paginate_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    page_size: int,
    query_identity_sha256: str,
    snapshot_identity_sha256: str,
    cursor: str | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    size = bounded_page_size(page_size)
    offset = 0
    if cursor:
        payload = _decode_cursor(cursor)
        if payload.get("contract") != CONTRACT or payload.get("schema_version") != SCHEMA_VERSION:
            raise QueryGuardError("INVALID_CURSOR", "cursor contract is unsupported")
        if payload.get("query_identity_sha256") != query_identity_sha256:
            raise QueryGuardError("CURSOR_QUERY_MISMATCH", "cursor belongs to a different query")
        if payload.get("snapshot_identity_sha256") != snapshot_identity_sha256:
            raise QueryGuardError(
                "CURSOR_SNAPSHOT_MISMATCH",
                "query snapshot changed between continuation requests",
                status_code=409,
            )
        raw_offset = payload.get("offset")
        if isinstance(raw_offset, bool) or not isinstance(raw_offset, int) or raw_offset < 0:
            raise QueryGuardError("INVALID_CURSOR", "cursor offset is invalid")
        offset = raw_offset
    if offset > len(rows):
        raise QueryGuardError("INVALID_CURSOR", "cursor offset exceeds the query result")

    page = [dict(row) for row in rows[offset : offset + size]]
    next_offset = offset + len(page)
    complete = next_offset >= len(rows)
    next_cursor = None
    if not complete:
        next_cursor = _encode_cursor(
            {
                "contract": CONTRACT,
                "schema_version": SCHEMA_VERSION,
                "query_identity_sha256": query_identity_sha256,
                "snapshot_identity_sha256": snapshot_identity_sha256,
                "offset": next_offset,
            }
        )
    return page, {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "query_identity_sha256": query_identity_sha256,
        "snapshot_identity_sha256": snapshot_identity_sha256,
        "total_rows": len(rows),
        "offset": offset,
        "page_size": size,
        "returned_rows": len(page),
        "complete": complete,
        "next_cursor": next_cursor,
    }


def ensure_response_size(payload: Mapping[str, object], *, maximum_bytes: int = MAX_RESPONSE_BYTES) -> int:
    try:
        encoded = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise QueryGuardError("INVALID_RESPONSE_PAYLOAD", "response payload is not finite JSON") from exc
    size = len(encoded)
    if size > maximum_bytes:
        raise QueryGuardError(
            "RESPONSE_PAYLOAD_TOO_LARGE",
            "response payload exceeds the supported byte envelope",
            status_code=413,
        )
    return size
