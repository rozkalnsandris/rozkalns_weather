from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from rozkalns_weather.source_runtime_parity import (
    CONTRACT,
    evaluate_source_runtime_parity,
    load_source_parity_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
CURRENT_SOURCE_SHA = "a" * 40
FIXTURES = json.loads(
    (ROOT / "tests" / "fixtures" / "source_runtime_parity_cases.json").read_text()
)
CASES = FIXTURES["cases"]


def _set_path(payload: dict[str, object], dotted_path: str, value: object) -> None:
    parts = dotted_path.split(".")
    target: dict[str, object] = payload
    for part in parts[:-1]:
        child = target[part]
        assert isinstance(child, dict)
        target = child
    target[parts[-1]] = value


def _bundle() -> dict[str, object]:
    return load_source_parity_bundle(ROOT, current_source_sha=CURRENT_SOURCE_SHA)


def test_current_reviewed_source_contracts_are_internally_consistent() -> None:
    result = evaluate_source_runtime_parity(_bundle())

    assert result["contract"] == CONTRACT
    assert result["state"] == "PASS"
    assert result["reason_codes"] == []
    assert result["source_identity"]["legacy_source_binding_recognized"] is True
    assert result["parity"]["compose_services"] == [
        "corpus-check",
        "public-ingest",
        "readiness",
        "schema-init",
        "weather",
    ]
    assert result["parity"]["application_service"] == "weather"
    assert result["parity"]["public_ingest_service"] == "public-ingest"
    assert result["parity"]["health_endpoint"] == "/health"
    assert result["parity"]["readiness_endpoint"] == "/ready"
    assert result["parity"]["database_init_mode"] == "require-existing"
    assert result["parity"]["systemd_service_unit"] == "rozkalns-weather-public-ingest.service"
    assert result["parity"]["systemd_timer_unit"] == "rozkalns-weather-public-ingest.timer"
    assert result["parity"]["on_calendar"] == "*:0/30"


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_fixture_cases_are_deterministic_and_fail_closed(case: dict[str, object]) -> None:
    first_bundle = _bundle()
    second_bundle = deepcopy(first_bundle)
    for mutation in case["mutations"]:
        assert mutation["op"] == "set"
        _set_path(first_bundle, mutation["path"], mutation["value"])
        _set_path(second_bundle, mutation["path"], mutation["value"])

    first = evaluate_source_runtime_parity(first_bundle)
    second = evaluate_source_runtime_parity(second_bundle)

    assert first == second
    assert first["state"] == case["expected_state"]
    assert set(case["expected_reason_codes"]).issubset(first["reason_codes"])
    if case["expected_state"] == "PASS":
        assert first["reason_codes"] == []


def test_source_parity_never_claims_live_deployment_or_health() -> None:
    result = evaluate_source_runtime_parity(_bundle())

    assert result["runtime_evidence"] == {
        "source_parity_proven": True,
        "runtime_deployed_proven": False,
        "runtime_healthy_proven": False,
        "host_state_observed": False,
    }
    assert result["authority"] == {
        "live_authority_granted": False,
        "runtime_mutation_performed": False,
        "production_data_mutation_performed": False,
    }


def test_evidence_is_sanitized_and_contains_no_private_runtime_material() -> None:
    result = evaluate_source_runtime_parity(_bundle())
    serialized = json.dumps(result, sort_keys=True)

    assert result["privacy"] == {
        "private_host_paths_exposed": False,
        "host_inventory_exposed": False,
        "credentials_or_secrets_exposed": False,
        "home_coordinates_exposed": False,
    }
    assert "/opt/rozkalns_weather" not in serialized
    assert "HOME_LAT" not in serialized
    assert "HOME_LON" not in serialized
    assert ".env" not in serialized


def test_machine_readable_contract_matches_executable_identity() -> None:
    contract = json.loads(
        (ROOT / "contracts" / "source-runtime-descriptor-parity-v1.json").read_text()
    )

    assert contract["contract"] == CONTRACT
    assert contract["schema_version"] == 1
    assert contract["runtime_evidence_boundary"]["runtime_deployed_can_be_proven_from_source"] is False
    assert contract["runtime_evidence_boundary"]["runtime_healthy_can_be_proven_from_source"] is False
    assert contract["authority"]["live_authority_granted"] is False
    assert "STALE_SOURCE_BINDING" in contract["stable_reason_codes"]
    assert "TIMER_JOB_IDENTITY_MISMATCH" in contract["stable_reason_codes"]
