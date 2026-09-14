from __future__ import annotations

import copy

import pytest

from rozkalns_weather.release_readiness import (
    CAPABILITY_SPECS,
    evaluate_release_readiness_matrix,
)

SHA = "a" * 40
CHECKED_AT = "2026-09-14T07:00:00Z"


def _capability(
    capability_id: str,
    *,
    state: str = "PASS",
    source_sha: str = SHA,
    checked_at_utc: str = "2026-09-14T06:55:00Z",
    block_reasons: list[str] | None = None,
    warn_reasons: list[str] | None = None,
) -> dict[str, object]:
    invariants = dict(CAPABILITY_SPECS[capability_id]["invariants"])
    if block_reasons is None:
        block_reasons = ["NOT_READY"] if state == "BLOCKED" else []
    if warn_reasons is None:
        warn_reasons = ["PENDING"] if state == "WARN" else []
    return {
        "id": capability_id,
        "state": state,
        "source_sha": source_sha,
        "evidence_ref": f"src/rozkalns_weather/{capability_id}.py",
        "checked_at_utc": checked_at_utc,
        "max_age_seconds": 86_400,
        "block_reasons": block_reasons,
        "warn_reasons": warn_reasons,
        "invariants": invariants,
    }


@pytest.fixture
def matrix_evidence() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_sha": SHA,
        "checked_at_utc": CHECKED_AT,
        "capabilities": [_capability(capability_id) for capability_id in CAPABILITY_SPECS],
    }


def _row(payload: dict[str, object], capability_id: str) -> dict[str, object]:
    return next(
        item for item in payload["capabilities"] if item["id"] == capability_id
    )


def _result_row(result: dict[str, object], capability_id: str) -> dict[str, object]:
    return next(
        item for item in result["capabilities"] if item["id"] == capability_id
    )


def test_tracks_are_independent_and_no_global_pass_hides_private_blocker(
    matrix_evidence: dict[str, object],
) -> None:
    _row(matrix_evidence, "weathernext_research").update(
        state="WARN", warn_reasons=["ACCESS_PENDING"]
    )
    _row(matrix_evidence, "private_home_runtime").update(
        state="BLOCKED",
        block_reasons=["PRIVATE_RUNTIME_OWNER_GATE_REQUIRED"],
    )
    _row(matrix_evidence, "production_data_write").update(
        state="BLOCKED",
        block_reasons=["PRODUCTION_DATA_OWNER_GATE_REQUIRED"],
    )

    result = evaluate_release_readiness_matrix(matrix_evidence)

    assert "state" not in result
    assert result["tracks"]["public_release"]["state"] == "PASS"
    assert result["tracks"]["weathernext_research"]["state"] == "WARN"
    assert result["tracks"]["private_activation"]["state"] == "BLOCKED"
    assert result["tracks"]["production_data_write"]["state"] == "BLOCKED"
    assert result["authority_boundary"]["grants_live_authority"] is False
    assert result["authority_boundary"]["grants_production_data_authority"] is False


def test_mixed_source_sha_blocks_capability_and_dependents(
    matrix_evidence: dict[str, object],
) -> None:
    _row(matrix_evidence, "public_corpus")["source_sha"] = "b" * 40

    result = evaluate_release_readiness_matrix(matrix_evidence)

    corpus = _result_row(result, "public_corpus")
    verification = _result_row(result, "verification")
    assert corpus["state"] == "BLOCKED"
    assert "SOURCE_SHA_MISMATCH" in corpus["block_reasons"]
    assert verification["state"] == "BLOCKED"
    assert "DEPENDENCY_BLOCKED:PUBLIC_CORPUS" in verification["block_reasons"]
    assert result["tracks"]["public_release"]["state"] == "BLOCKED"


def test_stale_evidence_blocks_public_release(
    matrix_evidence: dict[str, object],
) -> None:
    provider = _row(matrix_evidence, "provider_health")
    provider["checked_at_utc"] = "2026-09-12T06:55:00Z"
    provider["max_age_seconds"] = 86_400

    result = evaluate_release_readiness_matrix(matrix_evidence)

    row = _result_row(result, "provider_health")
    assert row["state"] == "BLOCKED"
    assert "STALE_EVIDENCE" in row["block_reasons"]
    assert result["tracks"]["public_release"]["state"] == "BLOCKED"


def test_missing_capability_is_explicitly_blocked(
    matrix_evidence: dict[str, object],
) -> None:
    matrix_evidence["capabilities"] = [
        item
        for item in matrix_evidence["capabilities"]
        if item["id"] != "reporting_exports"
    ]

    result = evaluate_release_readiness_matrix(matrix_evidence)

    row = _result_row(result, "reporting_exports")
    assert row["state"] == "BLOCKED"
    assert row["evidence_ref"] is None
    assert row["block_reasons"] == ["CAPABILITY_EVIDENCE_MISSING"]
    assert result["tracks"]["public_release"]["state"] == "BLOCKED"


@pytest.mark.parametrize(
    "private_fragment",
    [
        {"home_lat": 51.0},
        {"credentials": "material"},
        {"nested": {"host_path": "/private/weather"}},
        {"nested": {"value": "file:///home/andris/weather.db"}},
    ],
)
def test_private_field_or_path_leak_is_rejected(
    matrix_evidence: dict[str, object],
    private_fragment: dict[str, object],
) -> None:
    value = copy.deepcopy(matrix_evidence)
    value.update(private_fragment)
    with pytest.raises(ValueError):
        evaluate_release_readiness_matrix(value)


def test_contradictory_pass_with_block_reason_is_rejected(
    matrix_evidence: dict[str, object],
) -> None:
    _row(matrix_evidence, "verification")["block_reasons"] = ["NOT_READY"]
    with pytest.raises(ValueError, match="PASS contradicts"):
        evaluate_release_readiness_matrix(matrix_evidence)


def test_dwd_warning_authority_drift_blocks_public_release(
    matrix_evidence: dict[str, object],
) -> None:
    _row(matrix_evidence, "dwd_safety_radar")["invariants"][
        "official_warning_authority"
    ] = "model"

    result = evaluate_release_readiness_matrix(matrix_evidence)

    row = _result_row(result, "dwd_safety_radar")
    assert row["state"] == "BLOCKED"
    assert "INVARIANT_OFFICIAL_WARNING_AUTHORITY" in row["block_reasons"]
    assert result["tracks"]["public_release"]["state"] == "BLOCKED"


def test_weathernext_fabrication_blocks_research_not_public_release(
    matrix_evidence: dict[str, object],
) -> None:
    _row(matrix_evidence, "weathernext_research")["invariants"][
        "values_fabricated"
    ] = True

    result = evaluate_release_readiness_matrix(matrix_evidence)

    row = _result_row(result, "weathernext_research")
    assert row["state"] == "BLOCKED"
    assert "INVARIANT_VALUES_FABRICATED" in row["block_reasons"]
    assert result["tracks"]["weathernext_research"]["state"] == "BLOCKED"
    assert result["tracks"]["public_release"]["state"] == "PASS"
    assert result["tracks"]["private_activation"]["state"] == "BLOCKED"


def test_public_corpus_provenance_drift_blocks_verification_chain(
    matrix_evidence: dict[str, object],
) -> None:
    _row(matrix_evidence, "public_corpus")["invariants"][
        "immutable_history_preserved"
    ] = False

    result = evaluate_release_readiness_matrix(matrix_evidence)

    assert _result_row(result, "public_corpus")["state"] == "BLOCKED"
    assert _result_row(result, "provider_health")["state"] == "BLOCKED"
    assert _result_row(result, "verification")["state"] == "BLOCKED"


def test_handoff_summary_contains_only_track_state_and_public_capability_ids(
    matrix_evidence: dict[str, object],
) -> None:
    result = evaluate_release_readiness_matrix(matrix_evidence)

    assert set(result["handoff_summary"]) == {
        "public_release",
        "weathernext_research",
        "private_activation",
        "production_data_write",
        "public_blocked_capabilities",
        "public_warn_capabilities",
    }
    serialized = str(result["handoff_summary"]).lower()
    assert "authority_granted" not in serialized
    assert "home_lat" not in serialized
    assert "credential" not in serialized


def test_unknown_extra_invariant_is_rejected(
    matrix_evidence: dict[str, object],
) -> None:
    _row(matrix_evidence, "pwa")["invariants"]["unexpected"] = True
    with pytest.raises(ValueError, match="schema mismatch"):
        evaluate_release_readiness_matrix(matrix_evidence)
