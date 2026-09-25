from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .canonical_serialization import CanonicalSerializationError, canonical_sha256
from .verification_resampling import ResamplingError, resampling_lineage_binding


REPORT_LINEAGE_SCHEMA_VERSION = 1
REPORT_LINEAGE_CONTRACT = "verification-report-lineage-v1"
_REPORT_LINEAGE_CORE_KEYS = (
    "schema_version",
    "contract",
    "source_sha",
    "report_schema",
    "window",
    "corpus_manifest",
    "truth_revision_set",
    "provider_models",
    "configuration",
    "configuration_sha256",
    "sample_evidence",
    "artifact",
)
_RESAMPLING_CORE_KEYS = (
    "schema_version",
    "contract",
    "algorithm",
    "seed_identity_sha256",
    "sample_identity_sha256",
    "binding",
    "sample_count",
    "sample_sufficiency_state",
    "metric_configuration",
    "metric_configuration_sha256",
    "statistic",
    "confidence_level",
    "point_estimate",
    "interval",
    "interpretation",
    "ranking_verdict",
)


class ReportResamplingError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _sha256(value: object) -> str:
    try:
        return canonical_sha256(value)
    except CanonicalSerializationError as exc:
        raise ReportResamplingError(
            "REPORT_LINEAGE_NON_CANONICAL_VALUE",
            "report lineage must contain canonical finite JSON values",
        ) from exc


def _core(receipt: Mapping[str, object]) -> dict[str, object]:
    missing = [key for key in _REPORT_LINEAGE_CORE_KEYS if key not in receipt]
    if missing:
        raise ReportResamplingError(
            "REPORT_LINEAGE_CONTRACT_MISMATCH",
            f"report lineage receipt is missing required fields: {missing}",
        )
    return {key: receipt[key] for key in _REPORT_LINEAGE_CORE_KEYS}


def _validate_resampling_receipt_identity(receipt: Mapping[str, object]) -> None:
    missing = [key for key in _RESAMPLING_CORE_KEYS if key not in receipt]
    if missing:
        raise ReportResamplingError(
            "RESAMPLING_RECEIPT_CONTRACT_MISMATCH",
            f"resampling receipt is missing required fields: {missing}",
        )
    core = {key: receipt[key] for key in _RESAMPLING_CORE_KEYS}
    if receipt.get("resampling_receipt_identity_sha256") != _sha256(core):
        raise ReportResamplingError(
            "INVALID_RESAMPLING_RECEIPT_IDENTITY",
            "resampling receipt identity does not match its canonical receipt core",
        )


def bind_resampling_receipts_to_report_lineage(
    lineage_receipt: Mapping[str, object],
    *,
    resampling_receipts: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    """Bind validated resampling identities into an existing report-lineage receipt.

    The base ``verification-report-lineage-v1`` schema is preserved. Only its
    configuration is extended with privacy-safe resampling lineage, then the
    configuration and lineage identities are deterministically recomputed.
    """

    if (
        lineage_receipt.get("contract") != REPORT_LINEAGE_CONTRACT
        or lineage_receipt.get("schema_version") != REPORT_LINEAGE_SCHEMA_VERSION
    ):
        raise ReportResamplingError(
            "REPORT_LINEAGE_CONTRACT_MISMATCH",
            "unsupported report-lineage receipt contract",
        )
    base_core = _core(lineage_receipt)
    if lineage_receipt.get("lineage_identity_sha256") != _sha256(base_core):
        raise ReportResamplingError(
            "REPORT_LINEAGE_IDENTITY_MISMATCH",
            "base report-lineage identity is not reproducible",
        )
    configuration = lineage_receipt.get("configuration")
    if not isinstance(configuration, Mapping):
        raise ReportResamplingError(
            "REPORT_LINEAGE_CONTRACT_MISMATCH",
            "report-lineage configuration must be a mapping",
        )
    if not resampling_receipts:
        raise ReportResamplingError(
            "MISSING_RESAMPLING_LINEAGE",
            "at least one resampling receipt is required",
        )
    if "resampling" in configuration:
        raise ReportResamplingError(
            "RESAMPLING_LINEAGE_ALREADY_BOUND",
            "report lineage already contains resampling evidence",
        )

    normalized: list[dict[str, object]] = []
    for receipt in resampling_receipts:
        _validate_resampling_receipt_identity(receipt)
        try:
            normalized.append(resampling_lineage_binding(receipt))
        except ResamplingError as exc:
            raise ReportResamplingError(exc.reason_code, str(exc)) from exc
    normalized.sort(key=lambda item: str(item["resampling_receipt_identity_sha256"]))

    updated_configuration = dict(configuration)
    updated_configuration["resampling"] = normalized
    updated_core = dict(base_core)
    updated_core["configuration"] = updated_configuration
    updated_core["configuration_sha256"] = _sha256(updated_configuration)
    updated_identity = _sha256(updated_core)

    result: dict[str, Any] = dict(lineage_receipt)
    result["configuration"] = updated_configuration
    result["configuration_sha256"] = updated_core["configuration_sha256"]
    result["lineage_identity_sha256"] = updated_identity
    result["reproducible"] = True
    return result
