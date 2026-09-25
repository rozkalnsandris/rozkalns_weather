from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from typing import Any

from .locations import BENCHMARK_LOCATION
from .models import Observation, utc_iso
from .providers.dwd_cdc_observations import CDC_STATION_ID

OBSERVATION_REVISION_CONTRACT = "dwd-observation-revision-v1"
OBSERVATION_REVISION_SCHEMA_VERSION = 1
EXPECTED_STATION_ID = CDC_STATION_ID
EXPECTED_LOCATION_ID = BENCHMARK_LOCATION.id

_REQUIRED_PROVENANCE_FIELDS = (
    "source_authority",
    "transport",
    "cdc_product_family",
    "cdc_archive_code",
    "cdc_value_column",
    "source_url",
    "retrieved_at_utc",
)


class ObservationRevisionError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _canonical_json(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ObservationRevisionError(
            "NON_CANONICAL_REVISION_INPUT",
            "revision evidence must contain finite JSON-compatible values",
        ) from exc
    return (encoded + "\n").encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _utc(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ObservationRevisionError(
                "INVALID_TIMESTAMP",
                f"{field} must be ISO-8601 UTC",
            ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ObservationRevisionError(
            "INVALID_TIMESTAMP",
            f"{field} must be timezone-aware UTC",
        )
    return parsed.astimezone(timezone.utc)


def _metadata(item: Mapping[str, object]) -> dict[str, object]:
    raw = item.get("source_metadata")
    if isinstance(raw, Mapping):
        return dict(raw)
    raw_json = item.get("source_metadata_json")
    if raw_json in (None, ""):
        return {}
    try:
        parsed = json.loads(str(raw_json))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _record(value: Observation | Mapping[str, object]) -> dict[str, object]:
    if isinstance(value, Observation):
        return {
            "source_provider": value.source_provider,
            "station_id": value.station_id,
            "location_id": value.location_id,
            "observed_at_utc": value.observed_at_utc,
            "variable": value.variable,
            "value": value.value,
            "unit": value.unit,
            "quality_status": value.quality_status,
            "source_metadata": value.source_metadata,
        }
    return dict(value)


def _normalize_observation(
    raw: Observation | Mapping[str, object],
    *,
    retrieval_at: datetime,
    expected_station_id: str,
    expected_location_id: str,
) -> tuple[dict[str, object], list[str]]:
    item = _record(raw)
    reasons: list[str] = []
    if str(item.get("source_provider") or "") != "DWD":
        reasons.append("SOURCE_PROVIDER_MISMATCH")
    if str(item.get("station_id") or "") != expected_station_id:
        reasons.append("STATION_ID_MISMATCH")
    if str(item.get("location_id") or "") != expected_location_id:
        reasons.append("REFERENCE_LOCATION_MISMATCH")

    observed_at = _utc(item.get("observed_at_utc"), field="observed_at_utc")
    variable = str(item.get("variable") or "").strip()
    unit = str(item.get("unit") or "").strip()
    quality_status = None if item.get("quality_status") is None else str(item.get("quality_status"))
    if not variable or not unit:
        reasons.append("OBSERVATION_IDENTITY_INCOMPLETE")

    try:
        numeric_value = float(item.get("value"))
    except (TypeError, ValueError) as exc:
        raise ObservationRevisionError("INVALID_OBSERVATION_VALUE", "observation value must be numeric") from exc
    if not isfinite(numeric_value):
        raise ObservationRevisionError("INVALID_OBSERVATION_VALUE", "observation value must be finite")

    metadata = _metadata(item)
    missing_provenance = [field for field in _REQUIRED_PROVENANCE_FIELDS if metadata.get(field) in (None, "")]
    if missing_provenance:
        reasons.append("SOURCE_PROVENANCE_LOST")
    if metadata.get("source_authority") not in (None, "DWD"):
        reasons.append("SOURCE_AUTHORITY_MISMATCH")
    metadata_retrieved = metadata.get("retrieved_at_utc")
    if metadata_retrieved not in (None, ""):
        if _utc(metadata_retrieved, field="source_metadata.retrieved_at_utc") != retrieval_at:
            reasons.append("RETRIEVAL_PROVENANCE_MISMATCH")

    provenance = {
        field: metadata.get(field)
        for field in _REQUIRED_PROVENANCE_FIELDS
        if metadata.get(field) not in (None, "")
    }
    sample_key = {
        "source_provider": "DWD",
        "station_id": expected_station_id,
        "location_id": expected_location_id,
        "observed_at_utc": utc_iso(observed_at),
        "variable": variable,
    }
    content = {
        "value": numeric_value,
        "unit": unit,
        "quality_status": quality_status,
        "provenance_sha256": _sha256(provenance),
    }
    revision = {
        "sample_key": sample_key,
        "sample_key_sha256": _sha256(sample_key),
        "content_sha256": _sha256(content),
        "quality_status": quality_status,
        "value_unit_sha256": _sha256({"value": numeric_value, "unit": unit}),
        "provenance_sha256": content["provenance_sha256"],
        "observed_at": observed_at,
        "retrieved_at": retrieval_at,
    }
    revision["revision_identity_sha256"] = _sha256(
        {
            "sample_key_sha256": revision["sample_key_sha256"],
            "content_sha256": revision["content_sha256"],
            "retrieved_at_utc": utc_iso(retrieval_at),
        }
    )
    return revision, reasons


def build_dwd_observation_revision_evidence(
    retrievals: Sequence[Mapping[str, object]],
    *,
    expected_station_id: str = EXPECTED_STATION_ID,
    expected_location_id: str = EXPECTED_LOCATION_ID,
    stable_after_hours: float = 48.0,
    revision_window_hours: float = 168.0,
) -> dict[str, object]:
    if stable_after_hours <= 0 or revision_window_hours <= 0:
        raise ValueError("stable_after_hours and revision_window_hours must be positive")
    if not retrievals:
        raise ObservationRevisionError("NO_RETRIEVALS", "at least one retrieval snapshot is required")

    normalized_snapshots: list[tuple[datetime, dict[str, dict[str, object]]]] = []
    blockers: set[str] = set()
    warnings: set[str] = set()
    informational: set[str] = set()

    previous_retrieval: datetime | None = None
    for snapshot in retrievals:
        retrieval_at = _utc(snapshot.get("retrieved_at_utc"), field="retrieved_at_utc")
        if previous_retrieval is not None and retrieval_at <= previous_retrieval:
            raise ObservationRevisionError(
                "RETRIEVAL_ORDER_INVALID",
                "retrieval snapshots must be strictly increasing",
            )
        previous_retrieval = retrieval_at
        rows = snapshot.get("observations")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ObservationRevisionError("OBSERVATIONS_INVALID", "snapshot observations must be a sequence")

        by_key: dict[str, dict[str, object]] = {}
        for raw in rows:
            if not isinstance(raw, (Observation, Mapping)):
                raise ObservationRevisionError("OBSERVATIONS_INVALID", "observation rows must be mappings or Observation")
            revision, reasons = _normalize_observation(
                raw,
                retrieval_at=retrieval_at,
                expected_station_id=expected_station_id,
                expected_location_id=expected_location_id,
            )
            for reason in reasons:
                if reason in {
                    "SOURCE_PROVIDER_MISMATCH",
                    "STATION_ID_MISMATCH",
                    "REFERENCE_LOCATION_MISMATCH",
                    "OBSERVATION_IDENTITY_INCOMPLETE",
                    "SOURCE_PROVENANCE_LOST",
                    "SOURCE_AUTHORITY_MISMATCH",
                    "RETRIEVAL_PROVENANCE_MISMATCH",
                }:
                    blockers.add(reason)
                else:
                    warnings.add(reason)
            key = str(revision["sample_key_sha256"])
            existing = by_key.get(key)
            if existing is not None and existing["content_sha256"] != revision["content_sha256"]:
                blockers.add("CONFLICTING_REVISION")
            by_key[key] = revision
        normalized_snapshots.append((retrieval_at, by_key))

    histories: dict[str, list[dict[str, object]]] = {}
    for _retrieval_at, snapshot in normalized_snapshots:
        for key, revision in snapshot.items():
            histories.setdefault(key, []).append(revision)

    for (_prior_at, prior), (_current_at, current) in zip(normalized_snapshots, normalized_snapshots[1:]):
        if set(prior) - set(current):
            blockers.add("SAMPLE_DISAPPEARED")
        for key in set(prior) & set(current):
            before = prior[key]
            after = current[key]
            if before["content_sha256"] == after["content_sha256"]:
                continue
            informational.add("OBSERVATION_REVISED")
            if before["quality_status"] != after["quality_status"]:
                warnings.add("QUALITY_STATUS_CHANGED")
            if before["provenance_sha256"] != after["provenance_sha256"]:
                warnings.add("SOURCE_PROVENANCE_CHANGED")
            age_hours = (
                after["retrieved_at"] - after["observed_at"]
            ).total_seconds() / 3600.0
            if age_hours > revision_window_hours:
                blockers.add("LATE_REVISION_OUTSIDE_WINDOW")

    latest_retrieval = normalized_snapshots[-1][0]
    finality_counts = {"provisional": 0, "revised": 0, "stable": 0}
    selected: list[dict[str, object]] = []
    for key, history in sorted(histories.items()):
        latest = history[-1]
        content_hashes = [str(item["content_sha256"]) for item in history]
        last_change_at = history[0]["retrieved_at"]
        for before, after in zip(history, history[1:]):
            if before["content_sha256"] != after["content_sha256"]:
                last_change_at = after["retrieved_at"]
        unchanged_hours = (latest_retrieval - last_change_at).total_seconds() / 3600.0
        observation_age_hours = (latest_retrieval - latest["observed_at"]).total_seconds() / 3600.0
        if len(history) >= 2 and unchanged_hours >= stable_after_hours and observation_age_hours >= stable_after_hours:
            finality = "stable"
        elif len(set(content_hashes)) > 1:
            finality = "revised"
        else:
            finality = "provisional"
        finality_counts[finality] += 1
        selected.append(
            {
                "sample_key_sha256": key,
                "revision_identity_sha256": latest["revision_identity_sha256"],
                "content_sha256": latest["content_sha256"],
                "finality": finality,
            }
        )

    truth_revision_set_sha256 = _sha256(selected)
    reason_codes = sorted(blockers | warnings | informational)
    state = "BLOCKED" if blockers else ("WARN" if warnings or informational else "PASS")
    all_stable = bool(selected) and finality_counts["stable"] == len(selected)
    return {
        "schema_version": OBSERVATION_REVISION_SCHEMA_VERSION,
        "contract": OBSERVATION_REVISION_CONTRACT,
        "state": state,
        "read_only": True,
        "verification_ready": not blockers and all_stable,
        "station_id": expected_station_id,
        "location_id": expected_location_id,
        "retrieval_count": len(normalized_snapshots),
        "sample_count": len(selected),
        "first_retrieved_at_utc": utc_iso(normalized_snapshots[0][0]),
        "last_retrieved_at_utc": utc_iso(latest_retrieval),
        "stable_after_hours": stable_after_hours,
        "revision_window_hours": revision_window_hours,
        "contract_finality": "repository policy; not an official DWD publication/finality timestamp",
        "finality_counts": finality_counts,
        "truth_revision_set_sha256": truth_revision_set_sha256,
        "reason_codes": reason_codes,
        "privacy": {
            "raw_values_exposed": False,
            "source_urls_exposed": False,
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "raw_logs_exposed": False,
        },
    }
