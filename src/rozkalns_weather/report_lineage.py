from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
import re
from typing import Any

REPORT_LINEAGE_SCHEMA_VERSION = 1
REPORT_LINEAGE_CONTRACT = "verification-report-lineage-v1"
CORPUS_MANIFEST_CONTRACT = "corpus-provenance-manifest-v1"
TRUTH_REVISION_CONTRACT = "dwd-observation-revision-v1"

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_ELIGIBILITY_CLASSES = (
    "deterministic",
    "ensemble_members",
    "weathernext_summary_quantiles",
)


class ReportLineageError(ValueError):
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
        raise ReportLineageError("NON_CANONICAL_VALUE", "lineage inputs must be finite JSON values") from exc
    return (encoded + "\n").encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_sha40(value: object, *, field: str) -> str:
    text = str(value)
    if not _SHA40_RE.fullmatch(text):
        raise ReportLineageError("INVALID_SOURCE_SHA", f"{field} must be an exact lowercase 40-character Git SHA")
    return text


def _require_sha256(value: object, *, reason_code: str, field: str) -> str:
    text = str(value)
    if not _SHA256_RE.fullmatch(text):
        raise ReportLineageError(reason_code, f"{field} must be a lowercase SHA-256 digest")
    return text


def _safe_human_reference(value: object) -> str:
    reference = str(value).strip()
    if not reference:
        raise ReportLineageError("MISSING_HUMAN_REFERENCE", "human-readable artifact reference is required")
    if reference.startswith(("/", "\\")) or "://" in reference or ".." in reference.split("/"):
        raise ReportLineageError(
            "UNSAFE_HUMAN_REFERENCE",
            "human-readable artifact reference must be a repository-relative logical reference",
        )
    return reference


def _validate_window(window: Mapping[str, object], corpus_manifest: Mapping[str, object]) -> dict[str, str]:
    start = str(window.get("start") or "")
    end = str(window.get("end") or "")
    if not start or not end or end < start:
        raise ReportLineageError("INVALID_REPORT_WINDOW", "report window must have ordered start/end dates")
    manifest_window = corpus_manifest.get("window")
    if not isinstance(manifest_window, Mapping):
        raise ReportLineageError("MISSING_CORPUS_PROVENANCE", "corpus manifest window is missing")
    if str(manifest_window.get("start") or "") != start or str(manifest_window.get("end") or "") != end:
        raise ReportLineageError(
            "CORPUS_WINDOW_MISMATCH",
            "report window must exactly match the frozen corpus provenance-manifest window",
        )
    return {"start": start, "end": end}


def _validate_corpus_manifest(corpus_manifest: Mapping[str, object]) -> dict[str, object]:
    if corpus_manifest.get("contract") != CORPUS_MANIFEST_CONTRACT:
        raise ReportLineageError("CORPUS_MANIFEST_CONTRACT_MISMATCH", "unsupported corpus manifest contract")
    state = str(corpus_manifest.get("state") or "")
    if state not in {"PASS", "WARN"}:
        raise ReportLineageError("CORPUS_MANIFEST_NOT_ADMISSIBLE", "corpus manifest must be PASS or WARN")
    if corpus_manifest.get("read_only") is not True:
        raise ReportLineageError("CORPUS_MANIFEST_NOT_READ_ONLY", "corpus manifest must explicitly be read-only evidence")
    aggregate = _require_sha256(
        corpus_manifest.get("aggregate_checksum_sha256"),
        reason_code="MISSING_CORPUS_PROVENANCE",
        field="aggregate_checksum_sha256",
    )
    schema = corpus_manifest.get("corpus_schema")
    if not isinstance(schema, Mapping):
        raise ReportLineageError("MISSING_CORPUS_PROVENANCE", "corpus schema identity is missing")
    schema_identity = _require_sha256(
        schema.get("identity_sha256"),
        reason_code="MISSING_CORPUS_PROVENANCE",
        field="corpus_schema.identity_sha256",
    )
    return {
        "contract": CORPUS_MANIFEST_CONTRACT,
        "state": state,
        "aggregate_checksum_sha256": aggregate,
        "schema_identity_sha256": schema_identity,
        "manifest_checksum_sha256": _sha256(corpus_manifest),
    }


def _validate_truth_revision_set(truth_revision_set: Mapping[str, object]) -> dict[str, object]:
    if truth_revision_set.get("contract") != TRUTH_REVISION_CONTRACT:
        raise ReportLineageError("TRUTH_REVISION_CONTRACT_MISMATCH", "unsupported truth revision contract")
    if truth_revision_set.get("read_only") is not True:
        raise ReportLineageError("TRUTH_REVISION_NOT_READ_ONLY", "truth revision evidence must be read-only")
    state = str(truth_revision_set.get("state") or "")
    if state not in {"PASS", "WARN"}:
        raise ReportLineageError(
            "TRUTH_REVISION_NOT_ADMISSIBLE",
            "truth revision evidence must be PASS or WARN for report lineage",
        )
    identity = _require_sha256(
        truth_revision_set.get("truth_revision_set_sha256"),
        reason_code="MISSING_TRUTH_REVISION_PROVENANCE",
        field="truth_revision_set_sha256",
    )
    station_id = str(truth_revision_set.get("station_id") or "")
    location_id = str(truth_revision_set.get("location_id") or "")
    if not station_id or not location_id:
        raise ReportLineageError(
            "MISSING_TRUTH_REVISION_PROVENANCE",
            "truth revision station/location identity is required",
        )
    return {
        "contract": TRUTH_REVISION_CONTRACT,
        "state": state,
        "station_id": station_id,
        "location_id": location_id,
        "truth_revision_set_sha256": identity,
        "verification_ready": truth_revision_set.get("verification_ready") is True,
        "evidence_checksum_sha256": _sha256(truth_revision_set),
    }


def _normalize_report_schema(report_schema: Mapping[str, object]) -> dict[str, object]:
    name = str(report_schema.get("name") or "")
    version = report_schema.get("version")
    if not name or version in (None, ""):
        raise ReportLineageError("MISSING_REPORT_SCHEMA", "report schema name/version are required")
    return {"name": name, "version": version}


def _normalize_provider_models(provider_models: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if not provider_models:
        raise ReportLineageError("MISSING_PROVIDER_PROVENANCE", "at least one provider/model identity is required")
    normalized: list[dict[str, object]] = []
    for item in provider_models:
        provider = str(item.get("provider") or "")
        model_name = str(item.get("model_name") or "")
        if not provider or not model_name or "model_version" not in item:
            raise ReportLineageError(
                "MISSING_PROVIDER_PROVENANCE",
                "provider, model_name and explicit model_version are required",
            )
        normalized.append(
            {
                "provider": provider,
                "model_name": model_name,
                "model_version": item.get("model_version"),
            }
        )
    normalized.sort(key=lambda item: (str(item["provider"]), str(item["model_name"]), str(item["model_version"])))
    return normalized


def _normalize_metric_eligibility(metric_eligibility: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    missing = [name for name in _ALLOWED_ELIGIBILITY_CLASSES if name not in metric_eligibility]
    if missing:
        raise ReportLineageError(
            "MISSING_METRIC_ELIGIBILITY",
            "metric eligibility must explicitly distinguish deterministic, ensemble members and WeatherNext summary quantiles",
        )
    unknown = sorted(set(metric_eligibility) - set(_ALLOWED_ELIGIBILITY_CLASSES))
    if unknown:
        raise ReportLineageError("UNSUPPORTED_METRIC_SEMANTICS", f"unsupported metric eligibility classes: {unknown}")
    normalized: dict[str, list[str]] = {}
    for name in _ALLOWED_ELIGIBILITY_CLASSES:
        values = metric_eligibility[name]
        if isinstance(values, (str, bytes)):
            raise ReportLineageError("UNSUPPORTED_METRIC_SEMANTICS", f"{name} eligibility must be a sequence of metric ids")
        normalized[name] = sorted({str(value) for value in values if str(value)})
    return normalized


def _validate_sample_evidence(sample_evidence: Mapping[str, object]) -> dict[str, object]:
    common_identity = _require_sha256(
        sample_evidence.get("common_sample_identity_sha256"),
        reason_code="MISSING_SAMPLE_PROVENANCE",
        field="common_sample_identity_sha256",
    )
    counts = sample_evidence.get("sample_counts")
    if not isinstance(counts, Mapping) or not counts:
        raise ReportLineageError("MISSING_SAMPLE_PROVENANCE", "sample_counts mapping is required")
    normalized_counts: dict[str, int] = {}
    for key, value in counts.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ReportLineageError("INVALID_SAMPLE_COUNT", "sample counts must be non-negative integers")
        normalized_counts[str(key)] = value
    return {
        "common_sample_identity_sha256": common_identity,
        "sample_counts": dict(sorted(normalized_counts.items())),
    }


def _validate_single_identity(
    identities: Sequence[str] | None,
    *,
    expected: str,
    reason_code: str,
) -> list[str]:
    values = [expected] if identities is None else [str(value) for value in identities]
    unique = sorted(set(values))
    if unique != [expected]:
        raise ReportLineageError(reason_code, "lineage inputs contain mixed or mismatched identities")
    return unique


def build_report_lineage_receipt(
    *,
    artifact: Mapping[str, object],
    source_sha: str,
    report_schema: Mapping[str, object],
    corpus_manifest: Mapping[str, object],
    truth_revision_set: Mapping[str, object],
    window: Mapping[str, object],
    provider_models: Sequence[Mapping[str, object]],
    lead_filters: Mapping[str, object],
    sample_filters: Mapping[str, object],
    metric_configuration: Mapping[str, object],
    sample_evidence: Mapping[str, object],
    metric_eligibility: Mapping[str, Sequence[str]],
    human_readable_reference: str,
    source_identities: Sequence[str] | None = None,
    configuration_identities: Sequence[str] | None = None,
) -> dict[str, Any]:
    if not artifact:
        raise ReportLineageError("MISSING_REPORT_ARTIFACT", "machine-readable report artifact is required")
    exact_source_sha = _require_sha40(source_sha, field="source_sha")
    corpus_identity = _validate_corpus_manifest(corpus_manifest)
    truth_revision_identity = _validate_truth_revision_set(truth_revision_set)
    normalized_window = _validate_window(window, corpus_manifest)
    normalized_schema = _normalize_report_schema(report_schema)
    normalized_models = _normalize_provider_models(provider_models)
    normalized_sample_evidence = _validate_sample_evidence(sample_evidence)
    normalized_eligibility = _normalize_metric_eligibility(metric_eligibility)
    if not metric_configuration:
        raise ReportLineageError("MISSING_METRIC_CONFIGURATION", "metric configuration is required")

    configuration = {
        "lead_filters": dict(lead_filters),
        "sample_filters": dict(sample_filters),
        "metric_configuration": dict(metric_configuration),
        "metric_eligibility": normalized_eligibility,
    }
    configuration_sha256 = _sha256(configuration)
    _validate_single_identity(
        source_identities,
        expected=exact_source_sha,
        reason_code="MIXED_SOURCE_IDENTITY",
    )
    _validate_single_identity(
        configuration_identities,
        expected=configuration_sha256,
        reason_code="MIXED_CONFIGURATION_IDENTITY",
    )

    artifact_checksum = _sha256(artifact)
    receipt_core: dict[str, object] = {
        "schema_version": REPORT_LINEAGE_SCHEMA_VERSION,
        "contract": REPORT_LINEAGE_CONTRACT,
        "source_sha": exact_source_sha,
        "report_schema": normalized_schema,
        "window": normalized_window,
        "corpus_manifest": corpus_identity,
        "truth_revision_set": truth_revision_identity,
        "provider_models": normalized_models,
        "configuration": configuration,
        "configuration_sha256": configuration_sha256,
        "sample_evidence": normalized_sample_evidence,
        "artifact": {
            "machine_readable_checksum_sha256": artifact_checksum,
            "human_readable_reference": _safe_human_reference(human_readable_reference),
        },
    }
    lineage_identity = _sha256(receipt_core)
    return {
        **receipt_core,
        "lineage_identity_sha256": lineage_identity,
        "reproducible": True,
        "authority": {
            "production_data_authority_granted": False,
            "runtime_live_authority_granted": False,
            "artifact_publication_authority_granted": False,
        },
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
            "raw_logs_exposed": False,
        },
    }


def validate_report_lineage_receipt(
    receipt: Mapping[str, object],
    *,
    artifact: Mapping[str, object],
    corpus_manifest: Mapping[str, object],
    truth_revision_set: Mapping[str, object],
) -> dict[str, object]:
    if receipt.get("contract") != REPORT_LINEAGE_CONTRACT or receipt.get("schema_version") != REPORT_LINEAGE_SCHEMA_VERSION:
        raise ReportLineageError("RECEIPT_CONTRACT_MISMATCH", "unsupported report lineage receipt contract")
    artifact_meta = receipt.get("artifact")
    corpus_meta = receipt.get("corpus_manifest")
    truth_meta = receipt.get("truth_revision_set")
    if not isinstance(artifact_meta, Mapping) or not isinstance(corpus_meta, Mapping) or not isinstance(truth_meta, Mapping):
        raise ReportLineageError("MISSING_RECEIPT_PROVENANCE", "receipt artifact/corpus/truth provenance is missing")
    if artifact_meta.get("machine_readable_checksum_sha256") != _sha256(artifact):
        raise ReportLineageError("REPORT_ARTIFACT_CHECKSUM_MISMATCH", "machine-readable report artifact changed")
    current_corpus = _validate_corpus_manifest(corpus_manifest)
    if corpus_meta.get("manifest_checksum_sha256") != current_corpus["manifest_checksum_sha256"]:
        raise ReportLineageError("CORPUS_MANIFEST_MISMATCH", "corpus provenance manifest changed")
    if corpus_meta.get("aggregate_checksum_sha256") != current_corpus["aggregate_checksum_sha256"]:
        raise ReportLineageError("CORPUS_MANIFEST_MISMATCH", "corpus aggregate identity changed")
    current_truth = _validate_truth_revision_set(truth_revision_set)
    if truth_meta.get("truth_revision_set_sha256") != current_truth["truth_revision_set_sha256"]:
        raise ReportLineageError("TRUTH_REVISION_SET_MISMATCH", "truth revision set changed")
    if truth_meta.get("evidence_checksum_sha256") != current_truth["evidence_checksum_sha256"]:
        raise ReportLineageError("TRUTH_REVISION_EVIDENCE_MISMATCH", "truth revision evidence changed")

    receipt_core = {
        key: receipt[key]
        for key in (
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
        if key in receipt
    }
    expected_identity = _sha256(receipt_core)
    if receipt.get("lineage_identity_sha256") != expected_identity:
        raise ReportLineageError("LINEAGE_IDENTITY_MISMATCH", "receipt lineage identity is not reproducible")
    return {
        "schema_version": REPORT_LINEAGE_SCHEMA_VERSION,
        "contract": REPORT_LINEAGE_CONTRACT,
        "state": "PASS",
        "lineage_identity_sha256": expected_identity,
        "artifact_checksum_sha256": artifact_meta["machine_readable_checksum_sha256"],
        "corpus_manifest_checksum_sha256": current_corpus["manifest_checksum_sha256"],
        "truth_revision_set_sha256": current_truth["truth_revision_set_sha256"],
        "reproducible": True,
        "read_only": True,
    }
