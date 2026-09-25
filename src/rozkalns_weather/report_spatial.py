from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical_serialization import CanonicalSerializationError, canonical_sha256
from .spatial_provenance import SPATIAL_CONTRACT, SPATIAL_SCHEMA_VERSION

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


class ReportSpatialError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _sha256(value: object) -> str:
    try:
        return canonical_sha256(value)
    except CanonicalSerializationError as exc:
        raise ReportSpatialError("SPATIAL_LINEAGE_NON_CANONICAL_VALUE", "spatial lineage must be canonical JSON") from exc


def _lineage_core(receipt: Mapping[str, object]) -> dict[str, object]:
    missing = [key for key in _REPORT_LINEAGE_CORE_KEYS if key not in receipt]
    if missing:
        raise ReportSpatialError("REPORT_LINEAGE_CONTRACT_MISMATCH", f"report lineage fields missing: {missing}")
    return {key: receipt[key] for key in _REPORT_LINEAGE_CORE_KEYS}


def _validate_spatial_sample(sample: Mapping[str, object]) -> dict[str, object]:
    if sample.get("contract") != SPATIAL_CONTRACT or sample.get("schema_version") != SPATIAL_SCHEMA_VERSION:
        raise ReportSpatialError("SPATIAL_SAMPLE_CONTRACT_MISMATCH", "unsupported spatial sample contract")
    if sample.get("state") != "PASS" or sample.get("complete") is not True:
        raise ReportSpatialError("SPATIAL_SAMPLE_NOT_ADMISSIBLE", "spatial sample evidence must be complete PASS evidence")
    benchmark = sample.get("benchmark_location")
    if not isinstance(benchmark, Mapping) or benchmark.get("id") != "station_05480" or benchmark.get("station_id") != "05480":
        raise ReportSpatialError("SPATIAL_SAMPLE_LOCATION_MISMATCH", "report lineage requires canonical station_05480 benchmark")
    privacy = sample.get("privacy")
    if not isinstance(privacy, Mapping) or privacy.get("coordinates_exposed") is not False:
        raise ReportSpatialError("SPATIAL_SAMPLE_PRIVACY_VIOLATION", "spatial report lineage must remain coordinate-free")
    identity = str(sample.get("spatial_common_sample_identity_sha256") or "")
    if len(identity) != 64:
        raise ReportSpatialError("SPATIAL_SAMPLE_IDENTITY_MISSING", "spatial common-sample identity is required")
    forecasts = sample.get("forecasts")
    truth = sample.get("truth")
    if not isinstance(forecasts, list) or not forecasts or not isinstance(truth, Mapping):
        raise ReportSpatialError("SPATIAL_SAMPLE_NOT_ADMISSIBLE", "spatial forecast/truth bindings are required")
    return {
        "contract": SPATIAL_CONTRACT,
        "schema_version": SPATIAL_SCHEMA_VERSION,
        "benchmark_location": dict(benchmark),
        "spatial_common_sample_identity_sha256": identity,
        "truth_spatial_identity_sha256": truth.get("spatial_identity_sha256"),
        "forecast_spatial_identities_sha256": sorted(
            str(item.get("spatial_identity_sha256") or "")
            for item in forecasts
            if isinstance(item, Mapping)
        ),
        "privacy": {
            "coordinates_exposed": False,
            "private_home_identity_exposed": False,
        },
    }


def bind_spatial_sample_to_report_lineage(
    lineage_receipt: Mapping[str, object],
    *,
    spatial_sample: Mapping[str, object],
) -> dict[str, Any]:
    if (
        lineage_receipt.get("contract") != REPORT_LINEAGE_CONTRACT
        or lineage_receipt.get("schema_version") != REPORT_LINEAGE_SCHEMA_VERSION
    ):
        raise ReportSpatialError("REPORT_LINEAGE_CONTRACT_MISMATCH", "unsupported report-lineage receipt contract")
    base_core = _lineage_core(lineage_receipt)
    if lineage_receipt.get("lineage_identity_sha256") != _sha256(base_core):
        raise ReportSpatialError("REPORT_LINEAGE_IDENTITY_MISMATCH", "base report-lineage identity is not reproducible")
    configuration = lineage_receipt.get("configuration")
    if not isinstance(configuration, Mapping):
        raise ReportSpatialError("REPORT_LINEAGE_CONTRACT_MISMATCH", "report-lineage configuration must be a mapping")
    if "spatial_collocation" in configuration:
        raise ReportSpatialError("SPATIAL_LINEAGE_ALREADY_BOUND", "report lineage already contains spatial collocation evidence")

    spatial_binding = _validate_spatial_sample(spatial_sample)
    updated_configuration = dict(configuration)
    updated_configuration["spatial_collocation"] = spatial_binding
    updated_core = dict(base_core)
    updated_core["configuration"] = updated_configuration
    updated_core["configuration_sha256"] = _sha256(updated_configuration)
    updated_identity = _sha256(updated_core)

    result: dict[str, Any] = dict(lineage_receipt)
    result["configuration"] = updated_configuration
    result["configuration_sha256"] = updated_core["configuration_sha256"]
    result["lineage_identity_sha256"] = updated_identity
    result["reproducible"] = True
    privacy = dict(result.get("privacy") or {})
    privacy["coordinates_exposed"] = False
    result["privacy"] = privacy
    return result
