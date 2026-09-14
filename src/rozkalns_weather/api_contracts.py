from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

API_CONTRACT_VERSION = "api-contract-v1"
CONTRACT_INVARIANTS = {
    "severe_weather_warning_authority": "DWD",
    "weathernext_warning_authority": False,
    "pwa_data_states": ["fresh", "stale", "error", "offline"],
    "private_coordinates_allowed": False,
}

_DATETIME = {"type": "string", "format": "date-time"}
_NULLABLE_DATETIME = {"type": "string", "format": "date-time", "nullable": True}
_LOCATION = {
    "type": "object",
    "required": ["id", "label", "coordinates_exposed"],
    "properties": {
        "id": {"type": "string"},
        "label": {"type": "string"},
        "coordinates_exposed": {"type": "boolean", "enum": [False]},
    },
}
_HOME_LOCATION = {
    "type": "object",
    "required": ["id", "label", "configured", "coordinates_exposed", "timezone"],
    "properties": {
        "id": {"type": "string", "enum": ["home"]},
        "label": {"type": "string"},
        "configured": {"type": "boolean"},
        "coordinates_exposed": {"type": "boolean", "enum": [False]},
        "timezone": {"type": "string"},
    },
}
_DB_STATE = {
    "type": "object",
    "required": ["state", "exists", "required_tables_present", "missing_tables", "tables"],
    "properties": {
        "state": {"type": "string", "enum": ["ready", "missing", "schema_incomplete", "error"]},
        "exists": {"type": "boolean"},
        "required_tables_present": {"type": "boolean"},
        "missing_tables": {"type": "array", "items": {"type": "string"}},
        "tables": {"type": "array", "items": {"type": "string"}},
        "detail": {"type": "string", "nullable": True},
    },
}
_READINESS = {
    "type": "object",
    "required": [
        "schema_version", "ready", "status", "runtime_mode", "database_init_mode",
        "database", "storage", "home", "weathernext", "providers", "privacy",
    ],
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "ready": {"type": "boolean"},
        "status": {"type": "string", "enum": ["ready", "not_ready"]},
        "runtime_mode": {"type": "string"},
        "database_init_mode": {"type": "string", "enum": ["auto", "require-existing"]},
        "database": _DB_STATE,
        "storage": {
            "type": "object",
            "required": ["class", "persistent", "writable", "path_exposed"],
            "properties": {
                "class": {"type": "string", "enum": ["ephemeral_memory", "persistent_sqlite_file"]},
                "persistent": {"type": "boolean"},
                "writable": {"type": "boolean"},
                "path_exposed": {"type": "boolean", "enum": [False]},
            },
        },
        "home": {
            "type": "object",
            "required": ["configured", "required_for_public_runtime", "coordinates_exposed"],
            "properties": {
                "configured": {"type": "boolean"},
                "required_for_public_runtime": {"type": "boolean", "enum": [False]},
                "coordinates_exposed": {"type": "boolean", "enum": [False]},
            },
        },
        "weathernext": {
            "type": "object",
            "required": ["configured", "required_for_public_runtime", "values_fabricated"],
            "properties": {
                "configured": {"type": "boolean"},
                "required_for_public_runtime": {"type": "boolean", "enum": [False]},
                "values_fabricated": {"type": "boolean", "enum": [False]},
            },
        },
        "providers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "role", "state", "required_for_runtime", "last_success_at_utc"],
                "properties": {
                    "id": {"type": "string"},
                    "role": {"type": "string"},
                    "state": {"type": "string"},
                    "required_for_runtime": {"type": "boolean"},
                    "last_success_at_utc": _NULLABLE_DATETIME,
                },
            },
        },
        "privacy": {
            "type": "object",
            "required": ["coordinates_exposed", "credentials_exposed", "database_path_exposed"],
            "properties": {
                "coordinates_exposed": {"type": "boolean", "enum": [False]},
                "credentials_exposed": {"type": "boolean", "enum": [False]},
                "database_path_exposed": {"type": "boolean", "enum": [False]},
            },
        },
    },
}

API_CONTRACTS: dict[str, dict[str, Any]] = {
    "/health": {
        "type": "object",
        "required": ["status", "runtime_mode", "database", "home_configured", "weathernext_required"],
        "properties": {
            "status": {"type": "string", "enum": ["ok"]},
            "runtime_mode": {"type": "string"},
            "database": {"type": "string", "enum": ["ready", "missing", "schema_incomplete", "error"]},
            "home_configured": {"type": "boolean"},
            "weathernext_required": {"type": "boolean", "enum": [False]},
        },
    },
    "/ready": deepcopy(_READINESS),
    "/api/readiness": deepcopy(_READINESS),
    "/api/health/providers": {
        "type": "object",
        "required": ["runtime_mode", "health_contract", "home", "location", "verification_reference", "database", "providers"],
        "properties": {
            "runtime_mode": {"type": "string"},
            "health_contract": {"type": "string", "enum": ["provider-freshness-v1"]},
            "home": _HOME_LOCATION,
            "location": _HOME_LOCATION,
            "verification_reference": {
                "type": "object",
                "required": ["id", "label", "station_id", "coordinates_exposed"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "station_id": {"type": "string", "enum": ["10416"]},
                    "coordinates_exposed": {"type": "boolean", "enum": [False]},
                },
            },
            "database": _DB_STATE,
            "providers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "id", "model_name", "state", "tracked", "ingest_state", "freshness_state",
                        "failure_domain", "reason_code", "last_attempt_at_utc", "last_success_at_utc",
                        "last_init_time_utc", "last_retrieved_at_utc", "latest_valid_time_utc",
                        "last_observed_at_utc",
                    ],
                    "properties": {
                        "id": {"type": "string"},
                        "model_name": {"type": "string"},
                        "state": {"type": "string"},
                        "tracked": {"type": "boolean"},
                        "ingest_state": {"type": "string"},
                        "freshness_state": {
                            "type": "string",
                            "enum": ["fresh", "lagging", "degraded", "stale", "error", "unknown", "not_ingested", "not_tracked"],
                        },
                        "failure_domain": {"type": "string"},
                        "reason_code": {"type": "string"},
                        "last_attempt_at_utc": _NULLABLE_DATETIME,
                        "last_success_at_utc": _NULLABLE_DATETIME,
                        "last_init_time_utc": _NULLABLE_DATETIME,
                        "last_retrieved_at_utc": _NULLABLE_DATETIME,
                        "latest_valid_time_utc": _NULLABLE_DATETIME,
                        "last_observed_at_utc": _NULLABLE_DATETIME,
                    },
                },
            },
        },
    },
    "/api/current": {
        "type": "object",
        "required": ["location", "truth_source", "observations", "state", "note"],
        "properties": {
            "location": {
                "type": "object",
                "required": ["id", "label", "station_id", "coordinates_exposed"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "station_id": {"type": "string", "enum": ["10416"]},
                    "coordinates_exposed": {"type": "boolean", "enum": [False]},
                },
            },
            "truth_source": {"type": "string", "enum": ["DWD WMO 10416"]},
            "observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["observed_at_utc", "variable", "value", "unit"],
                    "properties": {
                        "observed_at_utc": _DATETIME,
                        "variable": {"type": "string"},
                        "value": {"type": "number"},
                        "unit": {"type": "string"},
                        "source_provider": {"type": "string"},
                        "station_id": {"type": "string"},
                    },
                },
            },
            "state": {"type": "string", "enum": ["observed", "not_observed_yet"]},
            "note": {"type": "string"},
        },
    },
    "/api/hourly": {
        "type": "object",
        "required": ["hours", "variable", "location", "series"],
        "properties": {
            "hours": {"type": "integer"},
            "variable": {"type": "string"},
            "location": _LOCATION,
            "series": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "provider", "model_name", "init_time_utc", "valid_time_utc", "lead_hours",
                        "variable", "statistic", "value", "unit", "retrieved_at_utc",
                    ],
                    "properties": {
                        "provider": {"type": "string"},
                        "model_name": {"type": "string"},
                        "model_version": {"type": "string", "nullable": True},
                        "init_time_utc": _NULLABLE_DATETIME,
                        "valid_time_utc": _DATETIME,
                        "lead_hours": {"type": "number"},
                        "variable": {"type": "string"},
                        "statistic": {"type": "string"},
                        "value": {"type": "number"},
                        "unit": {"type": "string"},
                        "retrieved_at_utc": _DATETIME,
                    },
                },
            },
        },
    },
    "/api/daily": {
        "type": "object",
        "required": ["days", "timezone", "location", "days_by_provider"],
        "properties": {
            "days": {"type": "integer"},
            "timezone": {"type": "string"},
            "location": _LOCATION,
            "days_by_provider": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "provider", "model_name", "date", "temperature_min_c", "temperature_max_c",
                        "precipitation_total_mm", "init_time_utc", "init_time_quality", "retrieved_at_utc",
                    ],
                    "properties": {
                        "provider": {"type": "string"},
                        "model_name": {"type": "string"},
                        "date": {"type": "string", "format": "date"},
                        "temperature_min_c": {"type": "number", "nullable": True},
                        "temperature_max_c": {"type": "number", "nullable": True},
                        "precipitation_total_mm": {"type": "number"},
                        "init_time_utc": _NULLABLE_DATETIME,
                        "init_time_quality": {"type": "string"},
                        "retrieved_at_utc": _DATETIME,
                    },
                },
            },
        },
    },
    "/api/verification/summary": {
        "type": "object",
        "required": [
            "window_days", "variable", "comparison_mode", "sample_sufficiency_contract",
            "comparison_location", "matching_tolerance_minutes", "verification_ready",
            "truth_quality", "common_sample_slices", "providers", "note",
        ],
        "properties": {
            "window_days": {"type": "integer"},
            "variable": {"type": "string", "enum": ["temperature_2m"]},
            "comparison_mode": {"type": "string", "enum": ["station_run_skill"]},
            "sample_sufficiency_contract": {"type": "string", "enum": ["common-sample-sufficiency-v1"]},
            "comparison_location": {
                "type": "object",
                "required": ["id", "station_id"],
                "properties": {
                    "id": {"type": "string"},
                    "station_id": {"type": "string", "enum": ["10416"]},
                },
            },
            "matching_tolerance_minutes": {"type": "integer", "enum": [0]},
            "verification_ready": {"type": "boolean"},
            "truth_quality": {"type": "object"},
            "common_sample_slices": {"type": "array", "items": {"type": "object"}},
            "providers": {"type": "object"},
            "note": {"type": "string"},
        },
    },
}


def contract_snapshot() -> dict[str, Any]:
    return {
        "schema": API_CONTRACT_VERSION,
        "invariants": deepcopy(CONTRACT_INVARIANTS),
        "endpoints": deepcopy(API_CONTRACTS),
    }


def _type_matches(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _format_valid(fmt: str, value: str) -> bool:
    if fmt == "date-time":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    if fmt == "date":
        try:
            datetime.fromisoformat(value + "T00:00:00")
            return len(value) == 10
        except ValueError:
            return False
    return True


def _validate(schema: Mapping[str, Any], value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if value is None:
        if schema.get("nullable") is True:
            return
        errors.append({"code": "NULL_NOT_ALLOWED", "path": path})
        return
    expected = schema.get("type")
    if isinstance(expected, str) and not _type_matches(expected, value):
        errors.append({"code": "TYPE_MISMATCH", "path": path})
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append({"code": "ENUM_VALUE_UNKNOWN", "path": path})
        return
    fmt = schema.get("format")
    if isinstance(fmt, str) and isinstance(value, str) and not _format_valid(fmt, value):
        errors.append({"code": "FORMAT_INVALID", "path": path})
    if expected == "object":
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append({"code": "REQUIRED_FIELD_MISSING", "path": f"{path}.{key}"})
        for key, child in schema.get("properties", {}).items():
            if key in value:
                _validate(child, value[key], f"{path}.{key}", errors)
    elif expected == "array":
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate(item_schema, item, f"{path}[{index}]", errors)


def validate_payload(endpoint: str, payload: Any, contracts: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, str]]:
    registry = contracts or API_CONTRACTS
    if endpoint not in registry:
        return [{"code": "CONTRACT_ENDPOINT_UNKNOWN", "path": endpoint}]
    errors: list[dict[str, str]] = []
    _validate(registry[endpoint], payload, endpoint, errors)
    return errors


def _compare_schema(old: Mapping[str, Any], new: Mapping[str, Any], path: str, changes: list[dict[str, str]]) -> None:
    if old.get("type") != new.get("type"):
        changes.append({"classification": "BREAKING", "code": "TYPE_CHANGED", "path": path})
        return
    if old.get("nullable") is True and new.get("nullable") is not True:
        changes.append({"classification": "BREAKING", "code": "NULLABILITY_NARROWED", "path": path})
    old_enum = old.get("enum")
    new_enum = new.get("enum")
    if isinstance(old_enum, list) and isinstance(new_enum, list):
        for value in old_enum:
            if value not in new_enum:
                changes.append({"classification": "BREAKING", "code": "ENUM_VALUE_REMOVED", "path": path})
        for value in new_enum:
            if value not in old_enum:
                changes.append({"classification": "ADDITIVE_COMPATIBLE", "code": "ENUM_VALUE_ADDED", "path": path})
    if old.get("type") == "object":
        old_required = set(old.get("required", []))
        new_required = set(new.get("required", []))
        for field in sorted(old_required - new_required):
            changes.append({"classification": "BREAKING", "code": "REQUIRED_GUARANTEE_REMOVED", "path": f"{path}.{field}"})
        old_props = old.get("properties", {})
        new_props = new.get("properties", {})
        for field in sorted(set(old_props) - set(new_props)):
            changes.append({"classification": "BREAKING", "code": "PROPERTY_REMOVED", "path": f"{path}.{field}"})
        for field in sorted(set(new_props) - set(old_props)):
            changes.append({"classification": "ADDITIVE_COMPATIBLE", "code": "PROPERTY_ADDED", "path": f"{path}.{field}"})
        for field in sorted(set(old_props) & set(new_props)):
            _compare_schema(old_props[field], new_props[field], f"{path}.{field}", changes)
    elif old.get("type") == "array" and old.get("items") and new.get("items"):
        _compare_schema(old["items"], new["items"], f"{path}[]", changes)


def classify_contract_change(
    baseline: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    changes: list[dict[str, str]] = []
    for endpoint in sorted(set(baseline) - set(candidate)):
        changes.append({"classification": "BREAKING", "code": "ENDPOINT_REMOVED", "path": endpoint})
    for endpoint in sorted(set(candidate) - set(baseline)):
        changes.append({"classification": "ADDITIVE_COMPATIBLE", "code": "ENDPOINT_ADDED", "path": endpoint})
    for endpoint in sorted(set(baseline) & set(candidate)):
        _compare_schema(baseline[endpoint], candidate[endpoint], endpoint, changes)
    breaking = any(change["classification"] == "BREAKING" for change in changes)
    return {
        "schema": "api-contract-compatibility-v1",
        "classification": "BREAKING" if breaking else ("ADDITIVE_COMPATIBLE" if changes else "IDENTICAL"),
        "changes": changes,
    }


_FORBIDDEN_KEYS = {
    "home_lat", "home_lon", "password", "token", "credential", "credentials",
    "secret", "database_url", "database_path", "raw_log", "raw_logs",
}
_FORBIDDEN_TEXT = ("sqlite:///", "/home/", "authorization: bearer ", "api_key=", "token=")


def privacy_violations(value: Any, path: str = "$") -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in _FORBIDDEN_KEYS:
                violations.append({"code": "PROHIBITED_FIELD", "path": f"{path}.{key}"})
                continue
            violations.extend(privacy_violations(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(privacy_violations(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _FORBIDDEN_TEXT):
            violations.append({"code": "PROHIBITED_VALUE_PATTERN", "path": path})
    return violations
