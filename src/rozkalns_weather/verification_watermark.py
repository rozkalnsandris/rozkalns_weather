from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone

from .canonical_serialization import CanonicalSerializationError, canonical_sha256

WATERMARK_CONTRACT = "verification-data-watermark-v1"
WATERMARK_SCHEMA_VERSION = 1

ON_TIME = "ON_TIME"
LATE_FORECAST_RETRIEVAL = "LATE_FORECAST_RETRIEVAL"
LATE_TRUTH_ARRIVAL = "LATE_TRUTH_ARRIVAL"
POST_CUTOFF_TRUTH_REVISION = "POST_CUTOFF_TRUTH_REVISION"
FORECAST_MISSING = "FORECAST_MISSING"
TRUTH_MISSING = "TRUTH_MISSING"


class VerificationWatermarkError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _sha256(value: object) -> str:
    try:
        return canonical_sha256(value)
    except CanonicalSerializationError as exc:
        raise VerificationWatermarkError(
            "NON_CANONICAL_WATERMARK_INPUT",
            "watermark inputs must be canonical finite JSON-compatible values",
        ) from exc


def _utc(value: object, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationWatermarkError("INVALID_TIMESTAMP", f"{field} must be ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise VerificationWatermarkError("INVALID_TIMESTAMP", f"{field} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_sha256(value: object, *, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise VerificationWatermarkError("INVALID_REVISION_IDENTITY", f"{field} must be a lowercase SHA-256 digest")
    return text


def _latency_context(latency_report: Mapping[str, object] | None) -> dict[str, object]:
    if latency_report is None:
        return {
            "contract": None,
            "state": "UNKNOWN",
            "reason_codes": ["LATENCY_EVIDENCE_UNAVAILABLE"],
            "affects_cutoff_selection": False,
        }
    if latency_report.get("contract") != "provider-availability-latency-v1":
        raise VerificationWatermarkError("LATENCY_CONTRACT_MISMATCH", "unsupported latency evidence contract")
    return {
        "contract": "provider-availability-latency-v1",
        "state": str(latency_report.get("state") or "UNKNOWN"),
        "reason_codes": sorted({str(code) for code in latency_report.get("reason_codes", [])}),
        "affects_cutoff_selection": False,
    }


def _normalize_revisions(raw: object, *, sample_id: str) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise VerificationWatermarkError("INVALID_TRUTH_REVISIONS", f"{sample_id}: truth_revisions must be a sequence")
    normalized: list[dict[str, str]] = []
    previous: datetime | None = None
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise VerificationWatermarkError("INVALID_TRUTH_REVISIONS", f"{sample_id}: truth revision must be a mapping")
        retrieved = _utc(item.get("retrieved_at_utc"), field=f"truth_revisions[{index}].retrieved_at_utc")
        if previous is not None and retrieved <= previous:
            raise VerificationWatermarkError(
                "TRUTH_REVISION_ORDER_INVALID",
                f"{sample_id}: truth revisions must be strictly ordered by retrieval time",
            )
        previous = retrieved
        normalized.append(
            {
                "retrieved_at_utc": _iso(retrieved),
                "revision_identity_sha256": _require_sha256(
                    item.get("revision_identity_sha256"),
                    field=f"truth_revisions[{index}].revision_identity_sha256",
                ),
            }
        )
    return normalized


def _normalize_sample(raw: Mapping[str, object], *, as_of: datetime) -> dict[str, object]:
    sample_id = str(raw.get("sample_id") or "").strip()
    provider = str(raw.get("provider") or "").strip()
    model_version = str(raw.get("model_version") or "").strip()
    valid_time = _utc(raw.get("valid_time_utc"), field="valid_time_utc")
    if not sample_id or not provider or not model_version:
        raise VerificationWatermarkError(
            "INCOMPLETE_SAMPLE_IDENTITY",
            "sample_id, provider and model_version are required",
        )

    forecast_raw = raw.get("forecast_retrieved_at_utc")
    forecast_retrieved = None if forecast_raw in (None, "") else _utc(forecast_raw, field="forecast_retrieved_at_utc")
    revisions = _normalize_revisions(raw.get("truth_revisions"), sample_id=sample_id)

    reasons: list[str] = []
    forecast_available = forecast_retrieved is not None and forecast_retrieved <= as_of
    if forecast_retrieved is None:
        reasons.append(FORECAST_MISSING)
    elif forecast_retrieved > as_of:
        reasons.append(LATE_FORECAST_RETRIEVAL)

    selected_revision: dict[str, str] | None = None
    post_cutoff_revision = False
    for revision in revisions:
        retrieved = _utc(revision["retrieved_at_utc"], field="truth_revision.retrieved_at_utc")
        if retrieved <= as_of:
            selected_revision = revision
        else:
            post_cutoff_revision = selected_revision is not None
            break

    truth_available = selected_revision is not None
    if not revisions:
        reasons.append(TRUTH_MISSING)
    elif not truth_available:
        reasons.append(LATE_TRUTH_ARRIVAL)
    if post_cutoff_revision:
        reasons.append(POST_CUTOFF_TRUTH_REVISION)
    if not reasons:
        reasons.append(ON_TIME)

    eligible = forecast_available and truth_available
    direct_reason_codes = [
        code
        for code in reasons
        if code in {LATE_FORECAST_RETRIEVAL, LATE_TRUTH_ARRIVAL, FORECAST_MISSING, TRUTH_MISSING}
    ]
    return {
        "sample_id": sample_id,
        "provider": provider,
        "model_version": model_version,
        "valid_time_utc": _iso(valid_time),
        "forecast_retrieved_at_utc": _iso(forecast_retrieved) if forecast_retrieved else None,
        "forecast_available_by_cutoff": forecast_available,
        "truth_available_by_cutoff": truth_available,
        "selected_truth_revision_identity_sha256": (
            selected_revision["revision_identity_sha256"] if selected_revision else None
        ),
        "selected_truth_retrieved_at_utc": selected_revision["retrieved_at_utc"] if selected_revision else None,
        "post_cutoff_truth_revision_present": post_cutoff_revision,
        "eligible_by_cutoff": eligible,
        "reason_codes": reasons,
        "missingness": {
            "forecast_available": forecast_available,
            "truth_available": truth_available,
            "verification_included": eligible,
            "reason_codes": direct_reason_codes,
        },
    }


def build_verification_watermark(
    samples: Sequence[Mapping[str, object]],
    *,
    as_of_utc: object,
    report_generated_at_utc: object,
    latency_report: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build deterministic as-of verification eligibility without rewriting corpus history."""

    as_of = _utc(as_of_utc, field="as_of_utc")
    generated = _utc(report_generated_at_utc, field="report_generated_at_utc")
    if generated < as_of:
        raise VerificationWatermarkError(
            "REPORT_GENERATED_BEFORE_WATERMARK",
            "report_generated_at_utc must be at or after as_of_utc",
        )
    if not samples:
        raise VerificationWatermarkError("NO_WATERMARK_SAMPLES", "at least one expected sample is required")

    normalized = [_normalize_sample(item, as_of=as_of) for item in samples]
    ids = [str(item["sample_id"]) for item in normalized]
    if len(ids) != len(set(ids)):
        raise VerificationWatermarkError("DUPLICATE_SAMPLE_ID", "sample_id must be unique")
    normalized.sort(key=lambda item: (str(item["valid_time_utc"]), str(item["provider"]), str(item["sample_id"])))

    eligible_ids = [str(item["sample_id"]) for item in normalized if item["eligible_by_cutoff"] is True]
    excluded = [item for item in normalized if item["eligible_by_cutoff"] is not True]
    reason_counts: dict[str, int] = {}
    for item in normalized:
        for code in item["reason_codes"]:
            reason_counts[str(code)] = reason_counts.get(str(code), 0) + 1

    identity_core = {
        "contract": WATERMARK_CONTRACT,
        "schema_version": WATERMARK_SCHEMA_VERSION,
        "as_of_utc": _iso(as_of),
        "samples": [
            {
                "sample_id": item["sample_id"],
                "provider": item["provider"],
                "model_version": item["model_version"],
                "forecast_retrieved_at_utc": item["forecast_retrieved_at_utc"],
                "selected_truth_revision_identity_sha256": item["selected_truth_revision_identity_sha256"],
                "selected_truth_retrieved_at_utc": item["selected_truth_retrieved_at_utc"],
                "eligible_by_cutoff": item["eligible_by_cutoff"],
                "reason_codes": item["reason_codes"],
            }
            for item in normalized
        ],
    }
    watermark_identity = _sha256(identity_core)
    matched_set_identity = _sha256(
        {
            "contract": WATERMARK_CONTRACT,
            "watermark_identity_sha256": watermark_identity,
            "eligible_sample_ids": eligible_ids,
        }
    )

    return {
        "schema_version": WATERMARK_SCHEMA_VERSION,
        "contract": WATERMARK_CONTRACT,
        "state": "PASS" if not excluded else "WARN",
        "read_only": True,
        "as_of_utc": _iso(as_of),
        "report_generated_at_utc": _iso(generated),
        "watermark_identity_sha256": watermark_identity,
        "matched_set_identity_sha256": matched_set_identity,
        "eligible_sample_ids": eligible_ids,
        "summary": {
            "expected_n": len(normalized),
            "eligible_n": len(eligible_ids),
            "excluded_n": len(excluded),
            "reason_counts": dict(sorted(reason_counts.items())),
        },
        "samples": normalized,
        "latency_context": _latency_context(latency_report),
        "history_policy": {
            "late_data_deleted": False,
            "corpus_history_mutated": False,
            "post_cutoff_revisions_preserved": True,
            "availability_timestamps_fabricated": False,
        },
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
            "raw_logs_exposed": False,
        },
    }


def validate_verification_watermark(evidence: Mapping[str, object]) -> dict[str, object]:
    if evidence.get("contract") != WATERMARK_CONTRACT or evidence.get("schema_version") != WATERMARK_SCHEMA_VERSION:
        raise VerificationWatermarkError("WATERMARK_CONTRACT_MISMATCH", "unsupported watermark contract")
    if evidence.get("read_only") is not True:
        raise VerificationWatermarkError("WATERMARK_NOT_READ_ONLY", "watermark evidence must be read-only")
    identity = str(evidence.get("watermark_identity_sha256") or "")
    matched = str(evidence.get("matched_set_identity_sha256") or "")
    _require_sha256(identity, field="watermark_identity_sha256")
    _require_sha256(matched, field="matched_set_identity_sha256")
    return {
        "contract": WATERMARK_CONTRACT,
        "schema_version": WATERMARK_SCHEMA_VERSION,
        "state": "PASS",
        "as_of_utc": str(evidence.get("as_of_utc") or ""),
        "watermark_identity_sha256": identity,
        "matched_set_identity_sha256": matched,
        "read_only": True,
    }
