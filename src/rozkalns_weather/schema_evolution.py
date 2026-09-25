from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Mapping, Sequence

from .db import SCHEMA_SQL

CONTRACT = "sqlite-schema-evolution-v1"
EVIDENCE_SCHEMA_VERSION = 1
CURRENT_SCHEMA_VERSION = 1
SUPPORTED_TRANSITIONS = {(1, 2)}

CORE_TABLES = (
    "forecast_runs",
    "forecast_values",
    "observations",
    "provider_ingest_status",
)

PROVENANCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "forecast_runs": (
        "provider",
        "model_provider",
        "model_name",
        "model_version",
        "location_id",
        "init_time_utc",
        "retrieved_at_utc",
        "source_surface",
        "raw_payload_hash",
        "revision",
    ),
    "forecast_values": (
        "run_id",
        "location_id",
        "valid_time_utc",
        "lead_hours",
        "variable",
        "statistic",
        "value",
        "unit",
    ),
    "observations": (
        "source_provider",
        "station_id",
        "location_id",
        "observed_at_utc",
        "variable",
        "value",
        "unit",
    ),
    "provider_ingest_status": (
        "provider",
        "model_name",
        "last_attempt_at_utc",
        "last_success_at_utc",
        "last_init_time_utc",
        "state",
    ),
}

REQUIRED_UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
    "forecast_runs": (
        "provider",
        "model_name",
        "location_id",
        "init_time_utc",
        "retrieved_at_utc",
    ),
    "forecast_values": (
        "run_id",
        "location_id",
        "valid_time_utc",
        "variable",
        "statistic",
        "accumulation_window_minutes",
    ),
    "observations": (
        "source_provider",
        "station_id",
        "observed_at_utc",
        "variable",
    ),
}

REQUIRED_IMMUTABILITY_TRIGGERS = {
    "forecast_runs_no_update",
    "forecast_runs_no_delete",
    "forecast_values_no_update",
    "forecast_values_no_delete",
}

SAFE_COLUMN_TYPES = {"TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _safe_identifier(value: object) -> str | None:
    text = str(value)
    return text if _IDENTIFIER_RE.fullmatch(text) else None


def build_fixture_database() -> sqlite3.Connection:
    """Build a deterministic in-memory v1 fixture; never opens a runtime DB path."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_SQL)
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> dict[str, dict[str, object]]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {
        str(row["name"]): {
            "type": str(row["type"]).upper(),
            "notnull": bool(row["notnull"]),
            "default": row["dflt_value"],
            "pk": int(row["pk"]),
        }
        for row in rows
    }


def _index_specs(connection: sqlite3.Connection, table: str) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for row in connection.execute(f"PRAGMA index_list({table})").fetchall():
        name = str(row["name"])
        columns = tuple(str(item["name"]) for item in connection.execute(f"PRAGMA index_info({name})").fetchall())
        result[name] = {
            "columns": columns,
            "unique": bool(row["unique"]),
            "origin": str(row["origin"]),
        }
    return result


def _unique_keys(connection: sqlite3.Connection, table: str) -> set[tuple[str, ...]]:
    return {
        tuple(spec["columns"])
        for spec in _index_specs(connection, table).values()
        if bool(spec["unique"])
    }


def _schema_snapshot(connection: sqlite3.Connection) -> dict[str, object]:
    tables = sorted(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    )
    table_payload: dict[str, object] = {}
    for table in tables:
        columns = _table_columns(connection, table)
        indexes = _index_specs(connection, table)
        table_payload[table] = {
            "columns": {
                name: {
                    "type": spec["type"],
                    "notnull": spec["notnull"],
                    "default": spec["default"],
                    "pk": spec["pk"],
                }
                for name, spec in sorted(columns.items())
            },
            "indexes": {
                name: {
                    "columns": list(spec["columns"]),
                    "unique": spec["unique"],
                    "origin": spec["origin"],
                }
                for name, spec in sorted(indexes.items())
                if not name.startswith("sqlite_autoindex_")
            },
        }
    triggers = sorted(
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
    )
    return {"tables": table_payload, "triggers": triggers}


def _validate_core_invariants(connection: sqlite3.Connection) -> list[str]:
    reasons: list[str] = []
    existing_tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    for table in CORE_TABLES:
        if table not in existing_tables:
            reasons.append(f"MISSING_CORE_TABLE:{table}")
            continue
        columns = _table_columns(connection, table)
        for column in PROVENANCE_COLUMNS[table]:
            if column not in columns:
                reasons.append(f"MISSING_PROVENANCE_COLUMN:{table}.{column}")

    for table, expected in REQUIRED_UNIQUE_KEYS.items():
        if table in existing_tables and expected not in _unique_keys(connection, table):
            reasons.append(f"LOCATION_OR_IDENTITY_UNIQUENESS_MISSING:{table}")

    if "provider_ingest_status" in existing_tables:
        provider_column = _table_columns(connection, "provider_ingest_status").get("provider")
        if not provider_column or int(provider_column["pk"]) != 1:
            reasons.append("PROVIDER_HEALTH_IDENTITY_MISSING")

    actual_triggers = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
    }
    for trigger in sorted(REQUIRED_IMMUTABILITY_TRIGGERS - actual_triggers):
        reasons.append(f"IMMUTABILITY_TRIGGER_MISSING:{trigger}")
    return sorted(set(reasons))


def _blocked(
    *,
    connection: sqlite3.Connection,
    migration: Mapping[str, object] | None,
    reasons: Sequence[str],
    operation_states: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    snapshot = _schema_snapshot(connection)
    return {
        "contract": CONTRACT,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "state": "BLOCKED",
        "decision": "BLOCKED",
        "from_version": migration.get("from_version") if migration else None,
        "to_version": migration.get("to_version") if migration else None,
        "baseline_schema_sha256": _sha256(snapshot),
        "reason_codes": sorted(set(str(reason) for reason in reasons)),
        "operations": list(operation_states),
        "preconditions": sorted(str(item) for item in (migration or {}).get("preconditions", [])),
        "rollback_semantics": (migration or {}).get("rollback_semantics"),
        "authority": {
            "production_schema_mutation_granted": False,
            "production_data_mutation_granted": False,
            "runtime_live_authority_granted": False,
        },
        "privacy": {
            "database_path_included": False,
            "coordinates_included": False,
            "credentials_included": False,
            "production_rows_read": False,
        },
        "source_only": True,
        "production_mutation_performed": False,
    }


def _operation_target(operation: Mapping[str, object]) -> tuple[str, str, str] | None:
    kind = str(operation.get("kind", ""))
    table = _safe_identifier(operation.get("table", ""))
    name = _safe_identifier(operation.get("name", ""))
    if not kind or not table or not name:
        return None
    return kind, table, name


def _evaluate_operation(
    connection: sqlite3.Connection,
    operation: Mapping[str, object],
    planned_columns: set[tuple[str, str]],
) -> tuple[dict[str, object], list[str]]:
    target = _operation_target(operation)
    if target is None:
        return {"state": "BLOCKED", "kind": str(operation.get("kind", "UNKNOWN"))}, ["INVALID_OPERATION_METADATA"]
    kind, table, name = target
    existing_tables = {
        str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if table not in existing_tables:
        return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["TARGET_TABLE_MISSING"]

    if kind == "add_column":
        column_type = str(operation.get("column_type", "")).upper()
        nullable = operation.get("nullable")
        has_default = operation.get("default_sql") not in (None, "")
        if column_type not in SAFE_COLUMN_TYPES or not isinstance(nullable, bool):
            return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["INVALID_ADDITIVE_COLUMN_METADATA"]
        if not nullable and not has_default:
            return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["NON_NULL_COLUMN_WITHOUT_DEFAULT"]
        columns = _table_columns(connection, table)
        if name in columns:
            spec = columns[name]
            expected_notnull = not nullable
            if str(spec["type"]).upper() != column_type or bool(spec["notnull"]) != expected_notnull:
                return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["COLUMN_DEFINITION_CONFLICT"]
            return {"state": "APPLIED", "kind": kind, "table": table, "name": name}, []
        planned_columns.add((table, name))
        return {"state": "PENDING", "kind": kind, "table": table, "name": name}, []

    if kind == "create_index":
        columns_raw = operation.get("columns")
        unique = operation.get("unique")
        if not isinstance(columns_raw, list) or not columns_raw or not isinstance(unique, bool):
            return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["INVALID_INDEX_METADATA"]
        columns: list[str] = []
        for item in columns_raw:
            identifier = _safe_identifier(item)
            if identifier is None:
                return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["INVALID_INDEX_METADATA"]
            columns.append(identifier)
        if unique:
            return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["NEW_UNIQUE_CONSTRAINT_REQUIRES_EXPLICIT_MIGRATION_CONTRACT"]
        existing_columns = set(_table_columns(connection, table)) | {
            column for planned_table, column in planned_columns if planned_table == table
        }
        if any(column not in existing_columns for column in columns):
            return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["INDEX_COLUMN_MISSING"]
        indexes = _index_specs(connection, table)
        if name in indexes:
            spec = indexes[name]
            if tuple(columns) != tuple(spec["columns"]) or bool(spec["unique"]) is not False:
                return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, ["INDEX_DEFINITION_CONFLICT"]
            return {"state": "APPLIED", "kind": kind, "table": table, "name": name, "columns": columns}, []
        return {"state": "PENDING", "kind": kind, "table": table, "name": name, "columns": columns}, []

    reasons = ["DESTRUCTIVE_OR_AMBIGUOUS_OPERATION_REQUIRES_EXPLICIT_MIGRATION_CONTRACT"]
    if table in PROVENANCE_COLUMNS and name in PROVENANCE_COLUMNS[table]:
        reasons.append("PROVENANCE_LOSS_RISK")
    if name in REQUIRED_IMMUTABILITY_TRIGGERS:
        reasons.append("IMMUTABILITY_LOSS_RISK")
    return {"state": "BLOCKED", "kind": kind, "table": table, "name": name}, reasons


def plan_schema_transition(
    connection: sqlite3.Connection,
    migration: Mapping[str, object] | None,
) -> dict[str, object]:
    """Plan a transition without executing DDL or reading production data."""
    invariant_reasons = _validate_core_invariants(connection)
    if invariant_reasons:
        return _blocked(
            connection=connection,
            migration=migration,
            reasons=["BASELINE_INVARIANT_FAILURE", *invariant_reasons],
        )
    if not migration:
        return _blocked(connection=connection, migration=None, reasons=["MISSING_MIGRATION_METADATA"])

    required = {"contract_id", "from_version", "to_version", "operations", "preconditions", "rollback_semantics"}
    if any(key not in migration for key in required):
        return _blocked(connection=connection, migration=migration, reasons=["MISSING_MIGRATION_METADATA"])
    try:
        from_version = int(migration["from_version"])
        to_version = int(migration["to_version"])
    except (TypeError, ValueError):
        return _blocked(connection=connection, migration=migration, reasons=["INVALID_SCHEMA_VERSION"])
    if (from_version, to_version) not in SUPPORTED_TRANSITIONS:
        return _blocked(connection=connection, migration=migration, reasons=["UNSUPPORTED_SCHEMA_TRANSITION"])

    operations_raw = migration["operations"]
    if not isinstance(operations_raw, list) or not operations_raw:
        return _blocked(connection=connection, migration=migration, reasons=["EMPTY_OR_INVALID_OPERATION_SET"])
    preconditions = migration["preconditions"]
    if not isinstance(preconditions, list) or not preconditions or not str(migration["rollback_semantics"]).strip():
        return _blocked(connection=connection, migration=migration, reasons=["MISSING_MIGRATION_METADATA"])

    seen_targets: set[tuple[str, str]] = set()
    planned_columns: set[tuple[str, str]] = set()
    states: list[dict[str, object]] = []
    reasons: list[str] = []
    for raw in operations_raw:
        if not isinstance(raw, Mapping):
            reasons.append("INVALID_OPERATION_METADATA")
            continue
        target = _operation_target(raw)
        if target is not None:
            _, table, name = target
            key = (table, name)
            if key in seen_targets:
                reasons.append("AMBIGUOUS_DUPLICATE_OPERATION_TARGET")
            seen_targets.add(key)
        state, operation_reasons = _evaluate_operation(connection, raw, planned_columns)
        states.append(state)
        reasons.extend(operation_reasons)

    if reasons:
        return _blocked(connection=connection, migration=migration, reasons=reasons, operation_states=states)

    applied = sum(1 for item in states if item["state"] == "APPLIED")
    pending = sum(1 for item in states if item["state"] == "PENDING")
    if applied and pending:
        return _blocked(
            connection=connection,
            migration=migration,
            reasons=["PARTIAL_MIGRATION_DETECTED"],
            operation_states=states,
        )

    snapshot = _schema_snapshot(connection)
    decision = "ALREADY_APPLIED" if applied == len(states) else "PLAN"
    return {
        "contract": CONTRACT,
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "state": "PASS",
        "decision": decision,
        "from_version": from_version,
        "to_version": to_version,
        "baseline_schema_sha256": _sha256(snapshot),
        "reason_codes": ["IDEMPOTENT_RERUN"] if decision == "ALREADY_APPLIED" else [],
        "operations": states,
        "preconditions": sorted(str(item) for item in preconditions),
        "rollback_semantics": str(migration["rollback_semantics"]),
        "preserved_invariants": {
            "forecast_runs_immutable": True,
            "forecast_values_immutable": True,
            "location_aware_uniqueness": True,
            "provider_model_provenance": True,
            "observation_identity": True,
            "provider_health_identity": True,
        },
        "authority": {
            "production_schema_mutation_granted": False,
            "production_data_mutation_granted": False,
            "runtime_live_authority_granted": False,
        },
        "privacy": {
            "database_path_included": False,
            "coordinates_included": False,
            "credentials_included": False,
            "production_rows_read": False,
        },
        "source_only": True,
        "production_mutation_performed": False,
    }


def example_additive_contract() -> dict[str, object]:
    return {
        "contract_id": "fixture-v1-to-v2-additive",
        "from_version": 1,
        "to_version": 2,
        "operations": [
            {
                "kind": "add_column",
                "table": "provider_ingest_status",
                "name": "last_latency_seconds",
                "column_type": "REAL",
                "nullable": True,
                "default_sql": None,
            },
            {
                "kind": "create_index",
                "table": "forecast_runs",
                "name": "idx_fixture_location_provider_retrieved",
                "columns": ["location_id", "provider", "retrieved_at_utc"],
                "unique": False,
            },
        ],
        "preconditions": [
            "exact reviewed source schema identity",
            "separate production SQLite migration authorization before any DDL",
            "backup and rollback readiness proven out of band before production mutation",
        ],
        "rollback_semantics": (
            "No automatic column rollback. Index rollback may drop only the exact authorized new index; "
            "column reversal requires a separately reviewed rebuild/restore contract and separate authority."
        ),
    }


def main() -> int:
    connection = build_fixture_database()
    try:
        evidence = plan_schema_transition(connection, example_additive_contract())
    finally:
        connection.close()
    print(json.dumps(evidence, sort_keys=True, indent=2))
    return 0 if evidence["state"] == "PASS" else 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
