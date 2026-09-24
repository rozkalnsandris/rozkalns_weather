from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

CONTRACT_VERSION = "timezone-dst-v1"
DISPLAY_TIMEZONE = "Europe/Berlin"
UTC = timezone.utc
BERLIN = ZoneInfo(DISPLAY_TIMEZONE)
_OFFSET_RE = re.compile(r"([+-])(\d{2}):(\d{2})$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


class TimestampContractError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _offset_text(value: datetime) -> str:
    offset = value.utcoffset()
    if offset is None:
        raise TimestampContractError("TIMEZONE_NAIVE", "timestamp must have a UTC offset")
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def validate_utc_timestamp(value: object) -> dict[str, object]:
    raw = str(value).strip() if value is not None else ""
    if not raw:
        return {"state": "BLOCKED", "reason_code": "INVALID_TIMESTAMP"}

    offset_match = _OFFSET_RE.search(raw)
    if offset_match:
        hours = int(offset_match.group(2))
        minutes = int(offset_match.group(3))
        if hours > 23 or minutes > 59:
            return {"state": "BLOCKED", "reason_code": "INVALID_OFFSET"}

    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        reason = "INVALID_OFFSET" if re.search(r"[+-]\d{2}:\d{2}$", raw) else "INVALID_TIMESTAMP"
        return {"state": "BLOCKED", "reason_code": reason}

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return {"state": "BLOCKED", "reason_code": "TIMEZONE_NAIVE"}

    offset = parsed.utcoffset()
    if offset != timedelta(0):
        instant = parsed.astimezone(UTC)
        berlin_offset = instant.astimezone(BERLIN).utcoffset()
        reason = (
            "LOCAL_TIME_PERSISTENCE_FORBIDDEN"
            if berlin_offset == offset
            else "CANONICAL_TIMESTAMP_NOT_UTC"
        )
        return {"state": "BLOCKED", "reason_code": reason}

    return {
        "state": "PASS",
        "reason_code": "OK",
        "canonical_utc": _utc_iso(parsed),
    }


def parse_canonical_utc(value: object) -> datetime:
    evidence = validate_utc_timestamp(value)
    if evidence["state"] != "PASS":
        raise TimestampContractError(
            str(evidence["reason_code"]),
            f"canonical timestamp rejected: {evidence['reason_code']}",
        )
    return datetime.fromisoformat(str(evidence["canonical_utc"]).replace("Z", "+00:00"))


def berlin_timestamp_view(value: object) -> dict[str, object]:
    utc_value = parse_canonical_utc(value)
    local = utc_value.astimezone(BERLIN)
    offset = _offset_text(local)
    utc_iso = _utc_iso(utc_value)
    wall = local.strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "contract": CONTRACT_VERSION,
        "utc": utc_iso,
        "timezone": DISPLAY_TIMEZONE,
        "local_iso": local.isoformat(timespec="seconds"),
        "local_date": local.strftime("%Y-%m-%d"),
        "local_month": local.strftime("%Y-%m"),
        "local_clock": local.strftime("%H:%M:%S"),
        "utc_offset": offset,
        "fold": local.fold,
        "display_identity": f"{wall}{offset}|{utc_iso}",
    }


def berlin_day_key(value: object) -> str:
    return str(berlin_timestamp_view(value)["local_date"])


def berlin_month_key(value: object) -> str:
    return str(berlin_timestamp_view(value)["local_month"])


def berlin_local_day_utc_bounds(day: str) -> dict[str, object]:
    try:
        local_date = date.fromisoformat(day)
    except ValueError as exc:
        raise TimestampContractError("INVALID_LOCAL_DATE", "day must be YYYY-MM-DD") from exc
    start_local = datetime.combine(local_date, datetime.min.time(), tzinfo=BERLIN)
    end_local = datetime.combine(local_date + timedelta(days=1), datetime.min.time(), tzinfo=BERLIN)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    return {
        "contract": CONTRACT_VERSION,
        "period_type": "berlin_local_day",
        "local_day": day,
        "timezone": DISPLAY_TIMEZONE,
        "start_utc": _utc_iso(start_utc),
        "end_utc_exclusive": _utc_iso(end_utc),
        "duration_hours": (end_utc - start_utc).total_seconds() / 3600,
    }


def berlin_local_month_utc_bounds(month: str) -> dict[str, object]:
    match = _MONTH_RE.fullmatch(month)
    if not match:
        raise TimestampContractError("INVALID_LOCAL_MONTH", "month must be YYYY-MM")
    year = int(match.group(1))
    month_number = int(match.group(2))
    if not 1 <= month_number <= 12:
        raise TimestampContractError("INVALID_LOCAL_MONTH", "month must be YYYY-MM")
    start_local = datetime(year, month_number, 1, tzinfo=BERLIN)
    if month_number == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=BERLIN)
    else:
        end_local = datetime(year, month_number + 1, 1, tzinfo=BERLIN)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    return {
        "contract": CONTRACT_VERSION,
        "period_type": "berlin_local_month",
        "local_month": month,
        "timezone": DISPLAY_TIMEZONE,
        "start_utc": _utc_iso(start_utc),
        "end_utc_exclusive": _utc_iso(end_utc),
        "duration_hours": (end_utc - start_utc).total_seconds() / 3600,
    }
