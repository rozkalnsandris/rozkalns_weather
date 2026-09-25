from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping, Sequence

CONTRACT = "verification-report-schema-compatibility-v1"
EVIDENCE_SCHEMA_VERSION = 1

ARTIFACT_CONTRACTS: dict[str, tuple[str, int]] = {
    "verification-summary-v1": ("verification_summary", 1),
    "public-monthly-benchmark-report-v1": ("public_monthly_benchmark_report", 1),
    "public-benchmark-export-v1": ("public_benchmark_export", 1),
    "verification-report-lineage-v1": ("verification_report_lineage", 1),
    "station-benchmark-monthly-v3": ("station_benchmark_monthly", 3),
}

_LEGACY_REPORT_TYPE_RE = re.compile(r"^station_benchmark_monthly_v(?P<version>[1-9][0-9]*)$")


class ArtifactSchemaError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class FieldSpec:
    required: bool
    nullable: bool
    field_type: str
    enum: tuple[str, ...] = ()
    has_default: bool = False
    default: object = None


@dataclass(frozen=True, slots=True)
class SchemaSpec:
    family: str
    name: str
    contract: str
    version: int
    fields: dict[str, FieldSpec]


def _canonical_json(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ArtifactSchemaError("NON_CANONICAL_SCHEMA_VALUE", "schema evidence must be finite JSON") from exc
    return (text + "\n").encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def artifact_schema_identity(artifact: Mapping[str, object]) -> dict[str, object]:
    """Return the explicit machine-readable schema identity carried by an artifact.

    The pre-contract station benchmark report used an explicit version in report_type;
    that single historical shape remains readable without rewriting the artifact.
    """

    contract = artifact.get("contract")
    version = artifact.get("schema_version")
    if contract not in (None, "") or version not in (None, ""):
        if not isinstance(contract, str) or contract not in ARTIFACT_CONTRACTS:
            raise ArtifactSchemaError("UNSUPPORTED_ARTIFACT_CONTRACT", "artifact contract is unsupported")
        expected_name, expected_version = ARTIFACT_CONTRACTS[contract]
        if not isinstance(version, int) or isinstance(version, bool):
            raise ArtifactSchemaError("INVALID_ARTIFACT_SCHEMA_VERSION", "schema_version must be an integer")
        if version != expected_version:
            raise ArtifactSchemaError(
                "ARTIFACT_CONTRACT_VERSION_MISMATCH",
                "artifact contract and schema_version do not describe the same registered schema",
            )
        return {"name": expected_name, "version": version, "contract": contract}

    report_type = artifact.get("report_type")
    match = _LEGACY_REPORT_TYPE_RE.fullmatch(str(report_type or ""))
    if match:
        parsed_version = int(match.group("version"))
        contract_name = f"station-benchmark-monthly-v{parsed_version}"
        if contract_name not in ARTIFACT_CONTRACTS:
            raise ArtifactSchemaError("UNSUPPORTED_HISTORICAL_SCHEMA", "historical report_type is not registered")
        return {
            "name": "station_benchmark_monthly",
            "version": parsed_version,
            "contract": contract_name,
            "historical_identity_source": "report_type",
        }

    raise ArtifactSchemaError(
        "MISSING_ARTIFACT_SCHEMA_IDENTITY",
        "machine-readable artifact must carry contract/schema_version or a registered historical report_type",
    )


def _field_spec(name: str, raw: object) -> FieldSpec:
    if not isinstance(raw, Mapping):
        raise ArtifactSchemaError("INVALID_SCHEMA_DESCRIPTOR", f"field descriptor {name} must be an object")
    required = raw.get("required")
    nullable = raw.get("nullable")
    field_type = raw.get("type")
    enum_raw = raw.get("enum", [])
    if not isinstance(required, bool) or not isinstance(nullable, bool) or not isinstance(field_type, str) or not field_type:
        raise ArtifactSchemaError("INVALID_SCHEMA_DESCRIPTOR", f"field descriptor {name} is incomplete")
    if not isinstance(enum_raw, list) or any(not isinstance(value, str) for value in enum_raw):
        raise ArtifactSchemaError("INVALID_SCHEMA_DESCRIPTOR", f"field descriptor {name} enum must be strings")
    return FieldSpec(
        required=required,
        nullable=nullable,
        field_type=field_type,
        enum=tuple(sorted(set(enum_raw))),
        has_default="default" in raw,
        default=raw.get("default"),
    )


def normalize_schema_descriptor(raw: Mapping[str, object]) -> SchemaSpec:
    family = str(raw.get("family") or "")
    name = str(raw.get("name") or "")
    contract = str(raw.get("contract") or "")
    version = raw.get("version")
    fields_raw = raw.get("fields")
    if not family or not name or not contract or not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ArtifactSchemaError("INVALID_SCHEMA_DESCRIPTOR", "schema family/name/contract/version are required")
    if not isinstance(fields_raw, Mapping) or not fields_raw:
        raise ArtifactSchemaError("INVALID_SCHEMA_DESCRIPTOR", "schema fields mapping is required")
    fields = {str(field): _field_spec(str(field), spec) for field, spec in fields_raw.items()}
    return SchemaSpec(family=family, name=name, contract=contract, version=version, fields=fields)


def _descriptor_payload(spec: SchemaSpec) -> dict[str, object]:
    return {
        "family": spec.family,
        "name": spec.name,
        "contract": spec.contract,
        "version": spec.version,
        "fields": {
            name: {
                "required": field.required,
                "nullable": field.nullable,
                "type": field.field_type,
                "enum": list(field.enum),
                **({"default": field.default} if field.has_default else {}),
            }
            for name, field in sorted(spec.fields.items())
        },
    }


def classify_schema_change(
    previous: Mapping[str, object],
    current: Mapping[str, object],
) -> dict[str, object]:
    """Classify producer evolution from previous -> current.

    `reader-compatible` means the current reader can consume supported historical
    artifacts without rewriting them. `additive-compatible` is the stronger case
    where the producer only adds optional fields. Any ambiguity fails closed.
    """

    old = normalize_schema_descriptor(previous)
    new = normalize_schema_descriptor(current)
    reasons: list[str] = []
    breaking = False
    reader_only = False
    additive = False

    if old.family != new.family or old.name != new.name:
        breaking = True
        reasons.append("SCHEMA_FAMILY_CHANGED")
    if new.version < old.version:
        breaking = True
        reasons.append("SCHEMA_VERSION_REGRESSION")

    old_names = set(old.fields)
    new_names = set(new.fields)
    for name in sorted(old_names - new_names):
        if old.fields[name].required:
            breaking = True
            reasons.append(f"REQUIRED_FIELD_REMOVED:{name}")
        else:
            reader_only = True
            reasons.append(f"OPTIONAL_FIELD_REMOVED:{name}")
    for name in sorted(new_names - old_names):
        if new.fields[name].required:
            breaking = True
            reasons.append(f"REQUIRED_FIELD_ADDED:{name}")
        else:
            additive = True
            reasons.append(f"OPTIONAL_FIELD_ADDED:{name}")

    for name in sorted(old_names & new_names):
        before = old.fields[name]
        after = new.fields[name]
        if before.field_type != after.field_type:
            breaking = True
            reasons.append(f"FIELD_TYPE_CHANGED:{name}")
        if before.required != after.required:
            breaking = True
            reasons.append(f"FIELD_REQUIREDNESS_CHANGED:{name}")
        if before.nullable != after.nullable:
            breaking = True
            reasons.append(f"FIELD_NULLABILITY_CHANGED:{name}")
        removed_enum = sorted(set(before.enum) - set(after.enum))
        added_enum = sorted(set(after.enum) - set(before.enum))
        if removed_enum:
            breaking = True
            reasons.append(f"ENUM_VALUE_REMOVED:{name}")
        if added_enum:
            reader_only = True
            reasons.append(f"ENUM_VALUE_ADDED:{name}")

    if breaking:
        classification = "breaking"
        state = "BLOCKED"
    elif reader_only:
        classification = "reader-compatible"
        state = "PASS"
    elif additive:
        classification = "additive-compatible"
        state = "PASS"
    else:
        classification = "reader-compatible"
        state = "PASS"
        reasons.append("SCHEMA_IDENTICAL")

    old_payload = _descriptor_payload(old)
    new_payload = _descriptor_payload(new)
    evidence_core = {
        "contract": CONTRACT,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "state": state,
        "classification": classification,
        "from": {"contract": old.contract, "version": old.version, "sha256": _sha256(old_payload)},
        "to": {"contract": new.contract, "version": new.version, "sha256": _sha256(new_payload)},
        "reason_codes": sorted(set(reasons)),
        "source_artifact_rewrite_performed": False,
        "human_readable_contract_evaluated": False,
    }
    return {**evidence_core, "evidence_sha256": _sha256(evidence_core)}


def read_historical_artifact(
    artifact: Mapping[str, object],
    *,
    source_schema: Mapping[str, object],
    current_schema: Mapping[str, object],
) -> dict[str, object]:
    """Return a deterministic in-memory reader view; never rewrite source evidence."""

    compatibility = classify_schema_change(source_schema, current_schema)
    if compatibility["state"] != "PASS":
        raise ArtifactSchemaError("BREAKING_SCHEMA_CHANGE", "historical artifact cannot be read by the current schema")
    source = normalize_schema_descriptor(source_schema)
    current = normalize_schema_descriptor(current_schema)
    view = deepcopy(dict(artifact))
    for name, field in sorted(current.fields.items()):
        if name in view:
            continue
        if field.has_default:
            view[name] = deepcopy(field.default)
        elif field.required:
            raise ArtifactSchemaError(
                "HISTORICAL_REQUIRED_FIELD_MISSING",
                f"historical artifact is missing required field {name}",
            )
    return {
        "contract": CONTRACT,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "state": "PASS",
        "source_schema": {"contract": source.contract, "version": source.version},
        "reader_schema": {"contract": current.contract, "version": current.version},
        "artifact_view": view,
        "source_artifact_rewrite_performed": False,
        "compatibility": compatibility,
    }


def validate_bundle_schema_versions(artifacts: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if not artifacts:
        raise ArtifactSchemaError("EMPTY_ARTIFACT_BUNDLE", "artifact bundle must not be empty")
    identities = [artifact_schema_identity(artifact) for artifact in artifacts]
    distinct = sorted({(str(item["name"]), int(item["version"])) for item in identities})
    if len(distinct) != 1:
        return {
            "contract": CONTRACT,
            "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
            "state": "BLOCKED",
            "reason_codes": ["MIXED_BUNDLE_SCHEMA_VERSION"],
            "schema_identities": [{"name": name, "version": version} for name, version in distinct],
            "source_artifact_rewrite_performed": False,
        }
    name, version = distinct[0]
    return {
        "contract": CONTRACT,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "state": "PASS",
        "reason_codes": [],
        "schema_identity": {"name": name, "version": version},
        "artifact_count": len(artifacts),
        "source_artifact_rewrite_performed": False,
    }
