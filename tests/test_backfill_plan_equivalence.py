from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from rozkalns_weather.backfill_plan_equivalence import (
    build_backfill_plan_receipt,
    validate_execution_equivalence,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "backfill_plan_equivalence_cases.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _plan() -> dict[str, object]:
    identity = _fixture()["base_identity"]
    return build_backfill_plan_receipt(
        source_sha=identity["source_sha"],
        start_date=identity["start_date"],
        end_date=identity["end_date"],
        providers_models=identity["providers_models"],
        run_hours_utc=identity["run_hours_utc"],
        truth_chunks=identity["truth_chunks"],
        rate_limits=identity["rate_limits"],
        checkpoint_namespace=identity["checkpoint_namespace"],
        recovery_decision=identity["recovery_decision"],
    )


def _evidence(plan: dict[str, object]) -> dict[str, object]:
    identity = copy.deepcopy(plan["identity"])
    return {
        "plan_digest_sha256": plan["plan_digest_sha256"],
        "identity": identity,
        "checkpoint": {
            "namespace": identity["checkpoint_namespace"],
            "completed_truth_chunks": list(identity["truth_chunks"]),
            "recovery_decision": identity["recovery_decision"],
        },
        "progress_metadata": {
            "started_at_utc": "2026-09-25T10:00:00Z",
            "updated_at_utc": "2026-09-25T10:05:00Z",
            "completed_count": 1,
            "attempt": 1,
        },
    }


def _set_path(payload: dict[str, object], dotted: str, value: object) -> None:
    head, key = dotted.split(".", 1)
    section = payload[head]
    assert isinstance(section, dict)
    section[key] = value


def test_plan_digest_is_deterministic_and_binds_material_scope() -> None:
    first = _plan()
    second = _plan()
    assert first["plan_digest_sha256"] == second["plan_digest_sha256"]
    assert len(first["plan_digest_sha256"]) == 64
    assert first["identity"]["rate_limits"]["forecast_requests_per_minute"] == 30
    assert first["authority"]["production_corpus_write_authorized"] is False


@pytest.mark.parametrize("case", _fixture()["cases"], ids=lambda case: case["name"])
def test_fixture_cases(case: dict[str, object]) -> None:
    plan = _plan()
    evidence = _evidence(plan)
    for dotted, value in case.get("mutations", {}).items():
        _set_path(evidence, dotted, value)
    result = validate_execution_equivalence(plan, evidence)
    if case.get("expected_state") == "PASS":
        assert result["state"] == "PASS"
        assert result["block_reasons"] == []
    else:
        assert result["state"] == "BLOCKED"
        assert case["expected_reason"] in result["block_reasons"]
    assert result["authority"]["production_corpus_write_authorized"] is False
    assert result["authority"]["runtime_live_authorized"] is False


def test_plan_digest_mismatch_blocks_even_when_identity_looks_equal() -> None:
    plan = _plan()
    evidence = _evidence(plan)
    evidence["plan_digest_sha256"] = "0" * 64
    result = validate_execution_equivalence(plan, evidence)
    assert result["state"] == "BLOCKED"
    assert "PLAN_DIGEST_MISMATCH" in result["block_reasons"]


def test_changed_rate_limit_is_material_drift() -> None:
    plan = _plan()
    evidence = _evidence(plan)
    evidence["identity"]["rate_limits"]["forecast_requests_per_minute"] = 60
    result = validate_execution_equivalence(plan, evidence)
    assert result["state"] == "BLOCKED"
    assert "RATE_LIMITS_DRIFT" in result["block_reasons"]


def test_material_progress_field_is_not_treated_as_harmless_metadata() -> None:
    plan = _plan()
    evidence = _evidence(plan)
    evidence["progress_metadata"]["provider"] = "extra"
    result = validate_execution_equivalence(plan, evidence)
    assert result["state"] == "BLOCKED"
    assert "PROGRESS_METADATA_MATERIAL_FIELD" in result["block_reasons"]


def test_private_execution_evidence_fails_closed_without_echoing_value() -> None:
    plan = _plan()
    evidence = _evidence(plan)
    evidence["database_path"] = "/private/runtime/value.sqlite"
    result = validate_execution_equivalence(plan, evidence)
    assert result["state"] == "BLOCKED"
    assert "PRIVATE_EVIDENCE_REJECTED" in result["block_reasons"]
    assert "/private/runtime/value.sqlite" not in json.dumps(result)
