from __future__ import annotations

import copy

import pytest

from rozkalns_weather.post_rollout_acceptance import evaluate_post_rollout_acceptance

SHA = "a" * 40
RELEASE = "weather-public-2026-09-12.1"


def evidence() -> dict[str, object]:
    providers = [
        {"id": "dwd_mosmix_l", "freshness_state": "fresh", "reason_code": "FRESH"},
        {"id": "dwd_observations", "freshness_state": "fresh", "reason_code": "FRESH"},
        {"id": "icon_d2", "freshness_state": "fresh", "reason_code": "FRESH"},
        {"id": "ecmwf_ifs", "freshness_state": "fresh", "reason_code": "FRESH"},
        {"id": "ecmwf_aifs", "freshness_state": "fresh", "reason_code": "FRESH"},
        {
            "id": "weathernext3",
            "freshness_state": "access_pending",
            "reason_code": "ACCESS_PENDING",
            "required_for_runtime": False,
            "values_fabricated": False,
        },
    ]
    return {
        "source_sha": SHA,
        "release_identity": RELEASE,
        "target_alias": "rozkalns-weather-public-rpi5",
        "endpoints": {
            "health_status": 200,
            "ready_status": 200,
            "provider_health_status": 200,
            "api_current_status": 200,
            "pwa_status": 200,
        },
        "readiness": {"ready": True, "runtime_mode": "public-only"},
        "schema": {"state": "ready", "implicit_migration_performed": False},
        "storage": {"state": "ready", "persistent": True},
        "corpus_integrity": {"ok": True, "regression_detected": False},
        "providers": providers,
    }


def evaluate(value: dict[str, object]) -> dict[str, object]:
    return evaluate_post_rollout_acceptance(
        value,
        expected_source_sha=SHA,
        expected_release_identity=RELEASE,
    )


def test_pass_has_no_rollback_authority() -> None:
    result = evaluate(evidence())
    assert result["state"] == "PASS"
    assert result["block_reasons"] == []
    assert result["warn_reasons"] == []
    assert result["rollback_decision_inputs"]["application"]["candidate"] is False
    assert result["rollback_decision_inputs"]["production_corpus"]["candidate"] is False
    assert result["authority"]["live_authority_granted"] is False
    assert result["authority"]["rollback_authority_granted"] is False


def test_provider_degradation_is_warn_and_isolated() -> None:
    value = evidence()
    value["providers"][2]["freshness_state"] = "degraded"
    value["providers"][2]["reason_code"] = "PARTIAL_INGEST_UPSTREAM_OR_TRANSPORT"
    result = evaluate(value)
    assert result["state"] == "WARN"
    assert "ICON_D2_PROVIDER_DEGRADED" in result["warn_reasons"]
    assert result["rollback_decision_inputs"]["application"]["candidate"] is False


@pytest.mark.parametrize("field", ["source_sha", "release_identity", "target_alias"])
def test_identity_drift_blocks_and_marks_application_candidate(field: str) -> None:
    value = evidence()
    value[field] = "wrong"
    result = evaluate(value)
    assert result["state"] == "BLOCKED"
    assert result["rollback_decision_inputs"]["application"]["candidate"] is True
    assert result["rollback_decision_inputs"]["production_corpus"]["candidate"] is False


def test_partial_service_health_blocks_application_only() -> None:
    value = evidence()
    value["endpoints"]["ready_status"] = 503
    result = evaluate(value)
    assert result["state"] == "BLOCKED"
    assert "READY_ENDPOINT_FAILED" in result["block_reasons"]
    assert result["rollback_decision_inputs"]["application"]["candidate"] is True
    assert result["rollback_decision_inputs"]["production_corpus"]["candidate"] is False


def test_schema_mismatch_blocks_without_implying_corpus_rollback() -> None:
    value = evidence()
    value["schema"]["state"] = "mismatch"
    result = evaluate(value)
    assert result["state"] == "BLOCKED"
    assert "SCHEMA_NOT_READY" in result["block_reasons"]
    assert result["rollback_decision_inputs"]["production_corpus"]["candidate"] is False


def test_corpus_regression_is_separate_corpus_decision_input() -> None:
    value = evidence()
    value["corpus_integrity"]["regression_detected"] = True
    result = evaluate(value)
    assert result["state"] == "BLOCKED"
    corpus = result["rollback_decision_inputs"]["production_corpus"]
    assert corpus["candidate"] is True
    assert corpus["automatic_restore_allowed"] is False
    assert corpus["automatic_delete_allowed"] is False
    assert corpus["restore_or_delete_requires_separate_exact_live_data_authorization"] is True
    assert result["rollback_decision_inputs"]["application"]["candidate"] is False


def test_missing_provider_evidence_blocks() -> None:
    value = evidence()
    value["providers"] = [
        item for item in value["providers"] if item["id"] != "ecmwf_aifs"
    ]
    result = evaluate(value)
    assert result["state"] == "BLOCKED"
    assert "PUBLIC_PROVIDER_EVIDENCE_MISSING" in result["block_reasons"]


@pytest.mark.parametrize(
    "private_field",
    [
        {"home_lat": 1.0},
        {"credentials": "secret"},
        {"raw_logs": ["private"]},
        {"nested": {"database_path": "/private/weather.db"}},
        {"nested": {"value": "/home/andris/weather.db"}},
    ],
)
def test_private_evidence_is_rejected(private_field: dict[str, object]) -> None:
    value = evidence()
    value.update(private_field)
    with pytest.raises(ValueError):
        evaluate(value)


def test_weathernext_fabrication_blocks() -> None:
    value = evidence()
    wn = next(item for item in value["providers"] if item["id"] == "weathernext3")
    wn["values_fabricated"] = True
    result = evaluate(value)
    assert result["state"] == "BLOCKED"
    assert "WEATHERNEXT_VALUES_FABRICATED" in result["block_reasons"]
