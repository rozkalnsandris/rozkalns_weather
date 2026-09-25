from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.schema_evolution import (
    CONTRACT,
    CURRENT_SCHEMA_VERSION,
    REQUIRED_IMMUTABILITY_TRIGGERS,
    REQUIRED_UNIQUE_KEYS,
    SUPPORTED_TRANSITIONS,
    build_fixture_database,
    example_additive_contract,
    main,
    plan_schema_transition,
)


def _apply_additive_fixture_transition(connection) -> None:
    connection.execute("ALTER TABLE provider_ingest_status ADD COLUMN last_latency_seconds REAL")
    connection.execute(
        "CREATE INDEX idx_fixture_location_provider_retrieved "
        "ON forecast_runs(location_id, provider, retrieved_at_utc)"
    )
    connection.commit()


def test_supported_v1_fixture_plans_additive_transition_deterministically() -> None:
    connection = build_fixture_database()
    try:
        first = plan_schema_transition(connection, example_additive_contract())
        second = plan_schema_transition(connection, example_additive_contract())
    finally:
        connection.close()

    assert CURRENT_SCHEMA_VERSION == 1
    assert SUPPORTED_TRANSITIONS == {(1, 2)}
    assert first == second
    assert first["contract"] == CONTRACT
    assert first["state"] == "PASS"
    assert first["decision"] == "PLAN"
    assert [item["state"] for item in first["operations"]] == ["PENDING", "PENDING"]
    assert first["preserved_invariants"] == {
        "forecast_runs_immutable": True,
        "forecast_values_immutable": True,
        "location_aware_uniqueness": True,
        "provider_model_provenance": True,
        "observation_identity": True,
        "provider_health_identity": True,
    }
    assert first["production_mutation_performed"] is False
    assert first["authority"]["production_schema_mutation_granted"] is False
    assert first["privacy"]["production_rows_read"] is False


def test_rerunning_already_applied_transition_is_idempotent() -> None:
    connection = build_fixture_database()
    try:
        _apply_additive_fixture_transition(connection)
        evidence = plan_schema_transition(connection, example_additive_contract())
    finally:
        connection.close()

    assert evidence["state"] == "PASS"
    assert evidence["decision"] == "ALREADY_APPLIED"
    assert evidence["reason_codes"] == ["IDEMPOTENT_RERUN"]
    assert all(item["state"] == "APPLIED" for item in evidence["operations"])


def test_partial_migration_is_blocked() -> None:
    connection = build_fixture_database()
    try:
        connection.execute("ALTER TABLE provider_ingest_status ADD COLUMN last_latency_seconds REAL")
        connection.commit()
        evidence = plan_schema_transition(connection, example_additive_contract())
    finally:
        connection.close()

    assert evidence["state"] == "BLOCKED"
    assert evidence["reason_codes"] == ["PARTIAL_MIGRATION_DETECTED"]
    assert [item["state"] for item in evidence["operations"]] == ["APPLIED", "PENDING"]


def test_missing_migration_metadata_is_blocked() -> None:
    connection = build_fixture_database()
    try:
        evidence = plan_schema_transition(connection, None)
    finally:
        connection.close()

    assert evidence["state"] == "BLOCKED"
    assert evidence["reason_codes"] == ["MISSING_MIGRATION_METADATA"]


def test_incompatible_unique_constraint_is_blocked() -> None:
    migration = example_additive_contract()
    migration["operations"] = [
        {
            "kind": "create_index",
            "table": "forecast_runs",
            "name": "idx_unsafe_unique_provider_model",
            "columns": ["provider", "model_name"],
            "unique": True,
        }
    ]
    connection = build_fixture_database()
    try:
        evidence = plan_schema_transition(connection, migration)
    finally:
        connection.close()

    assert evidence["state"] == "BLOCKED"
    assert evidence["reason_codes"] == ["NEW_UNIQUE_CONSTRAINT_REQUIRES_EXPLICIT_MIGRATION_CONTRACT"]


def test_destructive_provenance_change_is_blocked_with_specific_reason() -> None:
    migration = example_additive_contract()
    migration["operations"] = [
        {
            "kind": "drop_column",
            "table": "forecast_runs",
            "name": "model_name",
        }
    ]
    connection = build_fixture_database()
    try:
        evidence = plan_schema_transition(connection, migration)
    finally:
        connection.close()

    assert evidence["state"] == "BLOCKED"
    assert "DESTRUCTIVE_OR_AMBIGUOUS_OPERATION_REQUIRES_EXPLICIT_MIGRATION_CONTRACT" in evidence["reason_codes"]
    assert "PROVENANCE_LOSS_RISK" in evidence["reason_codes"]


def test_baseline_with_missing_immutability_trigger_is_blocked() -> None:
    connection = build_fixture_database()
    try:
        connection.execute("DROP TRIGGER forecast_values_no_delete")
        evidence = plan_schema_transition(connection, example_additive_contract())
    finally:
        connection.close()

    assert evidence["state"] == "BLOCKED"
    assert "BASELINE_INVARIANT_FAILURE" in evidence["reason_codes"]
    assert "IMMUTABILITY_TRIGGER_MISSING:forecast_values_no_delete" in evidence["reason_codes"]


def test_contract_declares_current_identity_guarantees() -> None:
    assert REQUIRED_IMMUTABILITY_TRIGGERS == {
        "forecast_runs_no_update",
        "forecast_runs_no_delete",
        "forecast_values_no_update",
        "forecast_values_no_delete",
    }
    assert "location_id" in REQUIRED_UNIQUE_KEYS["forecast_runs"]
    assert "location_id" in REQUIRED_UNIQUE_KEYS["forecast_values"]


def test_machine_contract_matches_source_gate() -> None:
    path = Path(__file__).resolve().parents[1] / "contracts" / "sqlite-schema-evolution-v1.json"
    contract = json.loads(path.read_text(encoding="utf-8"))

    assert contract["contract"] == CONTRACT
    assert contract["current_schema_version"] == CURRENT_SCHEMA_VERSION
    assert contract["supported_transitions"] == [
        {
            "from_version": 1,
            "to_version": 2,
            "allowed_operation_classes": ["add_column", "create_non_unique_index"],
        }
    ]
    assert contract["authority"]["production_schema_mutation_granted"] is False
    assert contract["authority"]["production_data_mutation_granted"] is False
    assert contract["authority"]["runtime_live_authority_granted"] is False
    assert contract["privacy"]["production_database_paths_allowed_in_evidence"] is False


def test_evidence_is_privacy_safe_and_cli_is_source_only(capsys) -> None:
    connection = build_fixture_database()
    try:
        evidence = plan_schema_transition(connection, example_additive_contract())
    finally:
        connection.close()

    encoded = json.dumps(evidence, sort_keys=True)
    assert ":memory:" not in encoded
    assert "51.5" not in encoded
    assert "7.6" not in encoded
    assert "HOME_LAT" not in encoded
    assert "HOME_LON" not in encoded

    rc = main()
    output = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert output["state"] == "PASS"
    assert output["source_only"] is True
    assert output["production_mutation_performed"] is False
