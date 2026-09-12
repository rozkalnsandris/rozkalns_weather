from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from .models import ForecastRun, ForecastValue, utc_iso
from .providers.weathernext import STATS
from .weathernext_collection import validate_snapshot_admission

MAX_SUPPORTED_CANDIDATE_AGE_HOURS = 48

REASON_CANARY_INVALID = "CANARY_EVIDENCE_INVALID"
REASON_SCHEMA_MISMATCH = "SCHEMA_FINGERPRINT_MISMATCH"
REASON_MODEL_MISMATCH = "MODEL_PROVENANCE_MISMATCH"
REASON_TEMPORAL_INVALID = "TEMPORAL_PROVENANCE_INVALID"
REASON_STALE = "SNAPSHOT_STALE"
REASON_STATISTICS_INCOMPLETE = "STATISTICS_MATRIX_INCOMPLETE"
REASON_VALUE_DUPLICATE = "VALUE_IDENTITY_DUPLICATE"
REASON_SURFACE_DUPLICATE = "PRODUCT_SURFACE_DUPLICATE"
REASON_SNAPSHOT_DUPLICATE = "SNAPSHOT_IDENTITY_DUPLICATE"


class SnapshotAdmissionError(ValueError):
    """Stable fail-closed error for WeatherNext first-snapshot admission."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise SnapshotAdmissionError(REASON_TEMPORAL_INVALID, "datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_value(value: ForecastValue) -> dict[str, object]:
    return {
        "valid_time_utc": utc_iso(value.valid_time_utc),
        "lead_hours": round(float(value.lead_hours), 6),
        "variable": value.variable,
        "statistic": value.statistic,
        "value": round(float(value.value), 10),
        "unit": value.unit,
        "native_value": None if value.native_value is None else round(float(value.native_value), 10),
        "native_unit": value.native_unit,
        "accumulation_window_minutes": value.accumulation_window_minutes,
    }


def _semantic_run_hash(run: ForecastRun) -> str:
    values = [_canonical_value(value) for value in run.values]
    values.sort(
        key=lambda item: (
            str(item["valid_time_utc"]),
            str(item["variable"]),
            str(item["statistic"]),
            int(item["accumulation_window_minutes"] or -1),
        )
    )
    payload = {
        "provider": run.provider,
        "model_provider": run.model_provider,
        "model_name": run.model_name,
        "model_version": run.model_version,
        "init_time_utc": utc_iso(run.init_time_utc),
        "source_surface": run.source_surface,
        "resolution": run.source_metadata.get("resolution"),
        "raw_payload_hash": run.raw_payload_hash,
        "values": values,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_statistics_matrix(runs: Sequence[ForecastRun]) -> None:
    expected = set(STATS)
    for run in runs:
        grouped: dict[tuple[str, str, int | None], set[str]] = {}
        seen: set[tuple[str, str, str, int | None]] = set()
        for value in run.values:
            identity = (
                utc_iso(value.valid_time_utc),
                value.variable,
                value.statistic,
                value.accumulation_window_minutes,
            )
            if identity in seen:
                raise SnapshotAdmissionError(
                    REASON_VALUE_DUPLICATE,
                    "duplicate valid-time/variable/statistic/window identity",
                )
            seen.add(identity)
            key = (
                utc_iso(value.valid_time_utc),
                value.variable,
                value.accumulation_window_minutes,
            )
            grouped.setdefault(key, set()).add(value.statistic)
        if not grouped:
            raise SnapshotAdmissionError(REASON_STATISTICS_INCOMPLETE, "snapshot run has no values")
        for statistics in grouped.values():
            if statistics != expected:
                raise SnapshotAdmissionError(
                    REASON_STATISTICS_INCOMPLETE,
                    "each WeatherNext variable/valid-time requires mean/p10/p25/p50/p75/p90",
                )


def _validate_surface_identity(runs: Sequence[ForecastRun]) -> tuple[str, ...]:
    resolutions = tuple(str(run.source_metadata.get("resolution") or "") for run in runs)
    if "combined" in resolutions:
        if resolutions != ("combined",):
            raise SnapshotAdmissionError(
                REASON_SURFACE_DUPLICATE,
                "combined snapshot surface must be the only candidate run",
            )
        return resolutions
    if sorted(resolutions) != ["0p05", "0p1"]:
        raise SnapshotAdmissionError(
            REASON_SURFACE_DUPLICATE,
            "candidate must contain exactly one 0p05 and one 0p1 run",
        )
    return tuple(sorted(resolutions))


def _snapshot_fingerprint(
    *,
    selected_init_time_utc: str,
    schema_fingerprint: str,
    model_version: str,
    runs: Sequence[ForecastRun],
) -> str:
    run_hashes = sorted(_semantic_run_hash(run) for run in runs)
    payload = {
        "contract": "weathernext3-first-snapshot-admission.v1",
        "provider": "weathernext3",
        "model_version": model_version,
        "location_id": "station_10416",
        "selected_init_time_utc": selected_init_time_utc,
        "schema_fingerprint": schema_fingerprint,
        "run_hashes": run_hashes,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_first_snapshot_admission(
    *,
    first_access_evidence: Mapping[str, Any],
    runs: Sequence[ForecastRun],
    candidate_schema_fingerprint: str,
    admission_time_utc: datetime,
    maximum_candidate_age_hours: int,
    existing_admission_fingerprints: Iterable[str] = (),
) -> dict[str, object]:
    """Build a privacy-safe write plan without performing a production write."""

    if not 1 <= maximum_candidate_age_hours <= MAX_SUPPORTED_CANDIDATE_AGE_HOURS:
        raise ValueError(
            f"maximum_candidate_age_hours must be between 1 and {MAX_SUPPORTED_CANDIDATE_AGE_HOURS}"
        )
    try:
        base = validate_snapshot_admission(
            first_access_evidence=first_access_evidence,
            runs=runs,
        )
    except ValueError as exc:
        raise SnapshotAdmissionError(REASON_CANARY_INVALID, str(exc)) from exc

    expected_schema_fingerprint = str(base.get("schema_fingerprint") or "")
    if not expected_schema_fingerprint or candidate_schema_fingerprint != expected_schema_fingerprint:
        raise SnapshotAdmissionError(
            REASON_SCHEMA_MISMATCH,
            "candidate schema fingerprint does not match validated first-access evidence",
        )

    model_version = str(base.get("model_version") or "")
    if not model_version or any(str(run.model_version or "") != model_version for run in runs):
        raise SnapshotAdmissionError(
            REASON_MODEL_MISMATCH,
            "candidate model provenance is inconsistent",
        )

    _validate_surface_identity(runs)
    _validate_statistics_matrix(runs)

    admission_time = _ensure_utc(admission_time_utc)
    maximum_age_seconds = maximum_candidate_age_hours * 3600
    retrieval_ages: list[float] = []
    for run in runs:
        retrieved = _ensure_utc(run.retrieved_at_utc)
        init_time = _ensure_utc(run.init_time_utc)
        if retrieved < init_time or retrieved > admission_time:
            raise SnapshotAdmissionError(
                REASON_TEMPORAL_INVALID,
                "retrieval must be on/after init and on/before admission time",
            )
        age_seconds = (admission_time - retrieved).total_seconds()
        if age_seconds > maximum_age_seconds:
            raise SnapshotAdmissionError(
                REASON_STALE,
                "candidate retrieval exceeds the explicitly bound maximum age",
            )
        retrieval_ages.append(age_seconds)

    selected_init = str(base.get("selected_init_time_utc") or "")
    fingerprint = _snapshot_fingerprint(
        selected_init_time_utc=selected_init,
        schema_fingerprint=candidate_schema_fingerprint,
        model_version=model_version,
        runs=runs,
    )
    existing = {str(item) for item in existing_admission_fingerprints}
    if fingerprint in existing:
        raise SnapshotAdmissionError(
            REASON_SNAPSHOT_DUPLICATE,
            "snapshot identity is already admitted",
        )

    product_surfaces = _validate_surface_identity(runs)
    return {
        "schema_version": 1,
        "contract": "weathernext3-first-snapshot-admission.v1",
        "state": "snapshot_write_plan_ready",
        "provider": "weathernext3",
        "model_version": model_version,
        "location_id": str(base.get("location_id") or "station_10416"),
        "selected_init_time_utc": selected_init,
        "schema_fingerprint": candidate_schema_fingerprint,
        "snapshot_admission_fingerprint": fingerprint,
        "product_surfaces": list(product_surfaces),
        "run_count": len(runs),
        "maximum_candidate_age_hours": maximum_candidate_age_hours,
        "oldest_retrieval_age_minutes": round(max(retrieval_ages) / 60.0, 3),
        "canary_evidence_validated": True,
        "provenance_validated": True,
        "statistics_matrix_validated": True,
        "immutable_revision_required": True,
        "idempotency_checked": True,
        "mutation_class": "production_sqlite_forecast_snapshot_write",
        "requires_exact_private_live_data_authority": True,
        "production_write_performed": False,
        "real_values_exposed": False,
        "private_fields_exposed": False,
    }
