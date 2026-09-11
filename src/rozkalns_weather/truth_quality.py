from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import json
from math import isfinite
from typing import Any

from .models import Observation, utc_iso
from .semantics import VARIABLES

TRUTH_QUALITY_CONTRACT = "dwd-truth-quality-v1"
EXPECTED_STATION_ID = "10416"
EXPECTED_LOCATION_ID = "station_10416"

_VALUE_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature_2m": (-80.0, 60.0),
    "dew_point_2m": (-100.0, 60.0),
    "relative_humidity_2m": (0.0, 100.0),
    "pressure_msl": (850.0, 1100.0),
    "wind_speed_10m": (0.0, 100.0),
    "wind_gust_10m": (0.0, 150.0),
    "cloud_cover": (0.0, 100.0),
    "precipitation_1h": (0.0, 500.0),
}
_ACCEPTED_QUALITY = {None, "", "observed", "valid", "ok"}
_BLOCKING_QUALITY = {"invalid", "rejected", "bad", "failed", "error"}


def _strict_timestamp(value: object) -> tuple[datetime | None, str | None]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None, "TIMESTAMP_INVALID"
    else:
        return None, "TIMESTAMP_INVALID"
    if parsed.tzinfo is None:
        return None, "TIMESTAMP_NAIVE"
    offset = parsed.utcoffset()
    if offset is None:
        return None, "TIMESTAMP_NAIVE"
    if offset.total_seconds() != 0:
        return parsed.astimezone(timezone.utc), "TIMESTAMP_NOT_UTC"
    return parsed.astimezone(timezone.utc), None


def _record(record: Observation | Mapping[str, object]) -> dict[str, Any]:
    if isinstance(record, Observation):
        return {
            "source_provider": record.source_provider,
            "station_id": record.station_id,
            "location_id": record.location_id,
            "observed_at_utc": record.observed_at_utc,
            "variable": record.variable,
            "value": record.value,
            "unit": record.unit,
            "quality_status": record.quality_status,
            "source_metadata": record.source_metadata,
        }
    item = dict(record)
    metadata = item.get("source_metadata")
    if metadata is None and item.get("source_metadata_json") is not None:
        raw = item.get("source_metadata_json")
        try:
            metadata = json.loads(str(raw)) if raw else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
            item["_metadata_invalid"] = True
    item["source_metadata"] = metadata if isinstance(metadata, dict) else {}
    return item


def assess_dwd_truth(
    records: Iterable[Observation | Mapping[str, object]],
    *,
    expected_station_id: str = EXPECTED_STATION_ID,
    expected_location_id: str = EXPECTED_LOCATION_ID,
    max_temperature_gap_hours: float = 2.01,
) -> dict[str, object]:
    blocking: set[str] = set()
    incomplete: set[str] = set()
    suspect: set[str] = set()
    items = [_record(record) for record in records]

    if not items:
        incomplete.add("NO_OBSERVATIONS")

    timestamps: list[datetime] = []
    temperature_times: set[datetime] = set()
    previous_by_variable: dict[str, datetime] = {}
    identity_rows: dict[tuple[str, str, str], tuple[float, str, str | None]] = {}
    station_names: set[str] = set()
    dwd_station_ids: set[str] = set()
    quality_statuses: set[str] = set()
    variables: set[str] = set()

    for item in items:
        if item.get("_metadata_invalid"):
            suspect.add("SOURCE_METADATA_INVALID")

        if str(item.get("source_provider") or "") != "DWD":
            blocking.add("SOURCE_PROVIDER_MISMATCH")
        if str(item.get("station_id") or "") != expected_station_id:
            blocking.add("STATION_ID_MISMATCH")
        if str(item.get("location_id") or "") != expected_location_id:
            blocking.add("REFERENCE_LOCATION_MISMATCH")

        timestamp, timestamp_reason = _strict_timestamp(item.get("observed_at_utc"))
        if timestamp_reason == "TIMESTAMP_NOT_UTC":
            suspect.add(timestamp_reason)
        elif timestamp_reason:
            blocking.add(timestamp_reason)
        if timestamp is not None:
            timestamps.append(timestamp)

        variable = str(item.get("variable") or "")
        variables.add(variable)
        definition = VARIABLES.get(variable)
        if definition is None or variable == "precipitation_probability_1h":
            blocking.add("VARIABLE_UNSUPPORTED_FOR_TRUTH")
        elif str(item.get("unit") or "") != str(definition["unit"]):
            blocking.add("UNIT_MISMATCH")

        value: float | None
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            blocking.add("VALUE_INVALID")
            value = None
        if value is not None:
            if not isfinite(value):
                blocking.add("VALUE_NONFINITE")
            bounds = _VALUE_BOUNDS.get(variable)
            if bounds is not None and not bounds[0] <= value <= bounds[1]:
                blocking.add("VALUE_OUT_OF_BOUNDS")

        quality = item.get("quality_status")
        normalized_quality = None if quality is None else str(quality).strip().lower()
        if normalized_quality:
            quality_statuses.add(normalized_quality)
        if normalized_quality in _BLOCKING_QUALITY:
            blocking.add("QUALITY_STATUS_REJECTED")
        elif normalized_quality not in _ACCEPTED_QUALITY:
            suspect.add("QUALITY_STATUS_UNKNOWN")

        metadata = item.get("source_metadata")
        if isinstance(metadata, dict):
            authority = metadata.get("source_authority")
            if authority is not None and str(authority) != "DWD":
                blocking.add("SOURCE_AUTHORITY_MISMATCH")
            metadata_wmo = metadata.get("wmo_station_id")
            if metadata_wmo is not None and str(metadata_wmo) != expected_station_id:
                blocking.add("SOURCE_WMO_MISMATCH")
            reference_location = metadata.get("reference_location_id")
            if reference_location is not None and str(reference_location) != expected_location_id:
                blocking.add("SOURCE_REFERENCE_LOCATION_MISMATCH")
            if metadata.get("station_identity_pinned") is False:
                blocking.add("STATION_IDENTITY_NOT_PINNED")
            station_name = metadata.get("station_name")
            if station_name:
                station_names.add(str(station_name))
            dwd_station_id = metadata.get("dwd_station_id")
            if dwd_station_id:
                dwd_station_ids.add(str(dwd_station_id))

        if timestamp is None:
            continue

        previous = previous_by_variable.get(variable)
        if previous is not None and timestamp < previous:
            suspect.add("TIMESTAMP_OUT_OF_ORDER")
        previous_by_variable[variable] = timestamp

        if variable == "temperature_2m":
            temperature_times.add(timestamp)

        if value is None:
            continue

        key = (expected_station_id, utc_iso(timestamp), variable)
        identity = (value, str(item.get("unit") or ""), normalized_quality)
        existing = identity_rows.get(key)
        if existing is not None:
            if existing == identity:
                suspect.add("DUPLICATE_OBSERVATION")
            else:
                blocking.add("CONFLICTING_DUPLICATE")
        else:
            identity_rows[key] = identity

    if len(quality_statuses) > 1:
        suspect.add("QUALITY_STATUS_DRIFT")
    if len(station_names) > 1 or len(dwd_station_ids) > 1:
        suspect.add("STATION_METADATA_DRIFT")

    max_gap_hours: float | None = None
    if "temperature_2m" not in variables:
        incomplete.add("TEMPERATURE_TRUTH_MISSING")
    elif len(temperature_times) < 2:
        incomplete.add("TEMPERATURE_COVERAGE_INSUFFICIENT")
    else:
        ordered = sorted(temperature_times)
        gaps = [
            (later - earlier).total_seconds() / 3600.0
            for earlier, later in zip(ordered, ordered[1:])
        ]
        max_gap_hours = max(gaps) if gaps else 0.0
        if max_gap_hours > max_temperature_gap_hours:
            incomplete.add("TEMPERATURE_COVERAGE_GAP")

    if blocking:
        state = "blocking"
    elif incomplete:
        state = "incomplete"
    elif suspect:
        state = "suspect"
    else:
        state = "valid"

    reason_codes = sorted(blocking | incomplete | suspect)
    return {
        "contract": TRUTH_QUALITY_CONTRACT,
        "state": state,
        "verification_ready": state == "valid",
        "station_id": expected_station_id,
        "location_id": expected_location_id,
        "observation_count": len(items),
        "variables": sorted(variables),
        "first_observed_at_utc": utc_iso(min(timestamps)) if timestamps else None,
        "last_observed_at_utc": utc_iso(max(timestamps)) if timestamps else None,
        "max_temperature_gap_hours": round(max_gap_hours, 6) if max_gap_hours is not None else None,
        "reason_codes": reason_codes,
    }


def database_truth_quality(
    database: Any,
    *,
    days: int = 90,
    location_id: str = EXPECTED_LOCATION_ID,
) -> dict[str, object]:
    if days < 1:
        raise ValueError("days must be >= 1")
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT source_provider,station_id,location_id,observed_at_utc,variable,value,unit,
                      quality_status,source_metadata_json
               FROM observations
               WHERE source_provider='DWD' AND location_id=?
                 AND julianday(observed_at_utc)>=julianday('now',?)
               ORDER BY observed_at_utc,variable,id""",
            (location_id, f"-{days} days"),
        ).fetchall()
    return assess_dwd_truth([dict(row) for row in rows], expected_location_id=location_id)
