from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

VALUE_PROVENANCE_CONTRACT = "value-provenance-trace-v1"
VALUE_PROVENANCE_SCHEMA_VERSION = 1
_HASH64_RE = re.compile(r"^[0-9a-f]{64}$")


class ValueProvenanceError(ValueError):
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
        raise ValueProvenanceError("NON_CANONICAL_TRACE_VALUE", "trace inputs must be finite JSON values") from exc
    return (encoded + "\n").encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _required(row: Mapping[str, object], field: str, *, reason_code: str = "INCOMPLETE_PROVENANCE") -> object:
    value = row.get(field)
    if value in (None, ""):
        raise ValueProvenanceError(reason_code, f"required provenance field is missing: {field}")
    return value


def _snapshot_id(row: Mapping[str, object]) -> str:
    value = row.get("raw_payload_hash")
    if value in (None, ""):
        raise ValueProvenanceError("MISSING_SNAPSHOT_ID", "raw_payload_hash is required as the immutable snapshot identity")
    snapshot_id = str(value)
    if not _HASH64_RE.fullmatch(snapshot_id):
        raise ValueProvenanceError("INVALID_SNAPSHOT_ID", "raw_payload_hash must be a lowercase SHA-256 digest")
    return snapshot_id


def _location_identity(location_id: object) -> dict[str, object]:
    location = str(location_id or "")
    if not location:
        raise ValueProvenanceError("MISSING_LOCATION_IDENTITY", "location_id is required")
    if location == "home":
        return {
            "id": "home",
            "scope": "private_home",
            "coordinates_exposed": False,
        }
    if location == "station_05480":
        return {
            "id": "station_05480",
            "scope": "public_benchmark",
            "station_id": "05480",
            "coordinates_exposed": False,
        }
    if location == "station_10416":
        return {
            "id": "station_10416",
            "scope": "legacy_compatibility",
            "station_id": "10416",
            "coordinates_exposed": False,
        }
    return {
        "id": location,
        "scope": "named_location",
        "coordinates_exposed": False,
    }


def _lineage_identity(report_lineage: Mapping[str, object] | None) -> dict[str, object] | None:
    if report_lineage is None:
        return None
    identity = report_lineage.get("lineage_identity_sha256")
    if identity in (None, ""):
        raise ValueProvenanceError("MISSING_VERIFICATION_RECEIPT", "report lineage identity is required")
    identity_text = str(identity)
    if not _HASH64_RE.fullmatch(identity_text):
        raise ValueProvenanceError("INVALID_VERIFICATION_RECEIPT", "lineage identity must be a lowercase SHA-256 digest")
    return {
        "contract": report_lineage.get("contract"),
        "schema_version": report_lineage.get("schema_version"),
        "lineage_identity_sha256": identity_text,
    }


def build_forecast_value_trace(
    row: Mapping[str, object],
    *,
    report_lineage: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    model_version = _required(row, "model_version", reason_code="MISSING_MODEL_VERSION")
    core: dict[str, object] = {
        "schema_version": VALUE_PROVENANCE_SCHEMA_VERSION,
        "contract": VALUE_PROVENANCE_CONTRACT,
        "kind": "forecast_value",
        "snapshot": {
            "id": _snapshot_id(row),
            "revision": int(_required(row, "revision")),
        },
        "source": {
            "provider": str(_required(row, "provider")),
            "model_provider": str(_required(row, "model_provider")),
            "model_name": str(_required(row, "model_name")),
            "model_version": str(model_version),
            "source_surface": str(_required(row, "source_surface")),
            "transport_provider": row.get("transport_provider"),
        },
        "time": {
            "init_time_utc": str(_required(row, "init_time_utc")),
            "retrieved_at_utc": str(_required(row, "retrieved_at_utc")),
            "upstream_available_at_utc": row.get("upstream_available_at_utc"),
            "valid_time_utc": str(_required(row, "valid_time_utc")),
            "lead_hours": float(_required(row, "lead_hours")),
            "init_time_quality": row.get("init_time_quality"),
        },
        "location": _location_identity(_required(row, "location_id")),
        "normalized_value": {
            "variable": str(_required(row, "variable")),
            "statistic": str(_required(row, "statistic")),
            "value": float(_required(row, "value")),
            "unit": str(_required(row, "unit")),
            "accumulation_window_minutes": row.get("accumulation_window_minutes"),
            "quality_status": row.get("quality_status"),
        },
        "normalization": {
            "native_value": row.get("native_value"),
            "native_unit": row.get("native_unit"),
            "semantics_preserved": True,
        },
        "report_lineage": _lineage_identity(report_lineage),
        "privacy": {
            "coordinates_exposed": False,
            "database_path_exposed": False,
            "credentials_exposed": False,
            "raw_logs_exposed": False,
        },
    }
    identity = _sha256(core)
    return {
        **core,
        "trace_identity_sha256": identity,
        "state": "PASS",
        "reason_codes": [],
    }


def forecast_trace_evidence(row: Mapping[str, object]) -> dict[str, object]:
    try:
        return build_forecast_value_trace(row)
    except (ValueProvenanceError, TypeError, ValueError) as exc:
        return {
            "schema_version": VALUE_PROVENANCE_SCHEMA_VERSION,
            "contract": VALUE_PROVENANCE_CONTRACT,
            "kind": "forecast_value",
            "state": "BLOCKED",
            "reason_codes": [getattr(exc, "reason_code", "INVALID_TRACE_INPUT")],
            "location": _location_identity(row.get("location_id") or "unknown"),
            "privacy": {
                "coordinates_exposed": False,
                "database_path_exposed": False,
                "credentials_exposed": False,
                "raw_logs_exposed": False,
            },
        }


def build_truth_value_trace(row: Mapping[str, object]) -> dict[str, Any]:
    core: dict[str, object] = {
        "schema_version": VALUE_PROVENANCE_SCHEMA_VERSION,
        "contract": VALUE_PROVENANCE_CONTRACT,
        "kind": "observation_truth",
        "source": {
            "provider": str(_required(row, "source_provider", reason_code="MISSING_TRUTH_IDENTITY")),
            "station_id": row.get("station_id"),
        },
        "time": {
            "observed_at_utc": str(_required(row, "observed_at_utc", reason_code="MISSING_TRUTH_IDENTITY")),
        },
        "location": _location_identity(_required(row, "location_id", reason_code="MISSING_TRUTH_IDENTITY")),
        "normalized_value": {
            "variable": str(_required(row, "variable", reason_code="MISSING_TRUTH_IDENTITY")),
            "value": float(_required(row, "value", reason_code="MISSING_TRUTH_IDENTITY")),
            "unit": str(_required(row, "unit", reason_code="MISSING_TRUTH_IDENTITY")),
            "quality_status": row.get("quality_status"),
        },
        "privacy": {
            "coordinates_exposed": False,
            "database_path_exposed": False,
            "credentials_exposed": False,
            "raw_logs_exposed": False,
        },
    }
    identity = _sha256(core)
    return {
        **core,
        "trace_identity_sha256": identity,
        "state": "PASS",
        "reason_codes": [],
    }


def build_verification_value_trace(
    forecast_row: Mapping[str, object],
    observation_row: Mapping[str, object],
    *,
    metric_identity: Mapping[str, object],
    report_lineage: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    forecast = build_forecast_value_trace(forecast_row, report_lineage=report_lineage)
    truth = build_truth_value_trace(observation_row)
    if forecast["location"]["id"] != truth["location"]["id"]:
        raise ValueProvenanceError("BROKEN_LINEAGE", "forecast and truth location identities do not match")
    if forecast["time"]["valid_time_utc"] != truth["time"]["observed_at_utc"]:
        raise ValueProvenanceError("BROKEN_LINEAGE", "forecast valid time and truth observation time do not match")
    if forecast["normalized_value"]["variable"] != truth["normalized_value"]["variable"]:
        raise ValueProvenanceError("BROKEN_LINEAGE", "forecast and truth variables do not match")
    metric_name = str(metric_identity.get("name") or "")
    if not metric_name:
        raise ValueProvenanceError("MISSING_METRIC_IDENTITY", "metric identity requires a name")
    core: dict[str, object] = {
        "schema_version": VALUE_PROVENANCE_SCHEMA_VERSION,
        "contract": VALUE_PROVENANCE_CONTRACT,
        "kind": "verification_value",
        "forecast_trace_identity_sha256": forecast["trace_identity_sha256"],
        "truth_trace_identity_sha256": truth["trace_identity_sha256"],
        "forecast": forecast,
        "truth": truth,
        "metric_identity": dict(metric_identity),
        "report_lineage": _lineage_identity(report_lineage),
        "privacy": {
            "coordinates_exposed": False,
            "database_path_exposed": False,
            "credentials_exposed": False,
            "raw_logs_exposed": False,
        },
    }
    identity = _sha256(core)
    return {
        **core,
        "trace_identity_sha256": identity,
        "state": "PASS",
        "reason_codes": [],
    }


def validate_trace_bundle(
    traces: Sequence[Mapping[str, object]],
    *,
    expected_report_lineage_identity: str | None = None,
) -> dict[str, object]:
    if not traces:
        raise ValueProvenanceError("EMPTY_TRACE_BUNDLE", "at least one trace is required")
    versions: dict[str, set[str]] = defaultdict(set)
    receipt_ids: set[str] = set()
    identities: list[str] = []
    for trace in traces:
        if trace.get("contract") != VALUE_PROVENANCE_CONTRACT or trace.get("schema_version") != VALUE_PROVENANCE_SCHEMA_VERSION:
            raise ValueProvenanceError("BROKEN_LINEAGE", "unsupported trace contract or schema version")
        identity = str(trace.get("trace_identity_sha256") or "")
        if not _HASH64_RE.fullmatch(identity):
            raise ValueProvenanceError("BROKEN_LINEAGE", "trace identity is missing or malformed")
        core = {key: value for key, value in trace.items() if key not in {"trace_identity_sha256", "state", "reason_codes"}}
        if _sha256(core) != identity:
            raise ValueProvenanceError("BROKEN_LINEAGE", "trace identity does not reproduce from the trace payload")
        identities.append(identity)
        if trace.get("kind") == "forecast_value":
            source = trace.get("source")
            if isinstance(source, Mapping):
                versions[str(source.get("provider") or "unknown")].add(str(source.get("model_version") or "unknown"))
        lineage = trace.get("report_lineage")
        if isinstance(lineage, Mapping) and lineage.get("lineage_identity_sha256"):
            receipt_ids.add(str(lineage["lineage_identity_sha256"]))
    mixed = {provider: sorted(values) for provider, values in versions.items() if len(values) > 1}
    if mixed:
        raise ValueProvenanceError("MIXED_MODEL_VERSIONS", f"trace bundle contains mixed model versions: {mixed}")
    if len(receipt_ids) > 1:
        raise ValueProvenanceError("VERIFICATION_RECEIPT_MISMATCH", "trace bundle contains multiple verification receipt identities")
    if expected_report_lineage_identity is not None and receipt_ids != {expected_report_lineage_identity}:
        raise ValueProvenanceError("VERIFICATION_RECEIPT_MISMATCH", "trace bundle does not match the expected verification receipt")
    return {
        "schema_version": VALUE_PROVENANCE_SCHEMA_VERSION,
        "contract": VALUE_PROVENANCE_CONTRACT,
        "state": "PASS",
        "trace_count": len(identities),
        "trace_bundle_identity_sha256": _sha256(sorted(identities)),
        "model_versions": {provider: next(iter(values)) for provider, values in sorted(versions.items())},
        "report_lineage_identity_sha256": next(iter(receipt_ids)) if receipt_ids else None,
        "reason_codes": [],
        "privacy": {
            "coordinates_exposed": False,
            "database_path_exposed": False,
            "credentials_exposed": False,
            "raw_logs_exposed": False,
        },
    }
