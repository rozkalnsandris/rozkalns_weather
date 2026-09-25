from __future__ import annotations

import json
from pathlib import Path

import pytest

from rozkalns_weather.ensemble_completeness import (
    CONTRACTS,
    CONTRACT_VERSION,
    canonical_member_id,
    evaluate_member_set,
    evaluate_run_stability,
    metric_eligible,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ensemble_member_completeness_cases.json"


def _ids(count: int) -> list[str]:
    return [f"member_{index:02d}" for index in range(count)]


def test_supported_contracts_bind_expected_control_and_member_identities() -> None:
    assert CONTRACT_VERSION == "ensemble-member-completeness-v1"
    assert CONTRACTS["icon_d2_eps"].expected_member_count == 20
    assert CONTRACTS["ecmwf_ifs_ens"].expected_member_count == 51
    assert CONTRACTS["ecmwf_aifs_ens"].expected_member_count == 51
    assert CONTRACTS["icon_d2_eps"].expected_member_ids[0] == "control"
    assert CONTRACTS["icon_d2_eps"].expected_member_ids[-1] == "member19"
    assert CONTRACTS["ecmwf_ifs_ens"].expected_member_ids[-1] == "member50"
    assert canonical_member_id("member_00") == "control"
    assert canonical_member_id("member01") == "member01"
    assert canonical_member_id("member_01") == "member01"


@pytest.mark.parametrize("case", json.loads(FIXTURE.read_text())["cases"], ids=lambda case: case["name"])
def test_fixture_driven_completeness_states(case: dict[str, object]) -> None:
    result = evaluate_member_set(
        provider_id=str(case["provider_id"]),
        member_ids=tuple(str(item) for item in case["member_ids"]),
        declared_member_count=int(case["declared_member_count"])
        if "declared_member_count" in case
        else None,
        model_versions=tuple(str(item) for item in case.get("model_versions", [])),
        retention_truncated=bool(case.get("retention_truncated", False)),
    )
    assert result["status"] == case["expected_status"]
    assert case["expected_reason"] in result["reason_codes"]
    eligible = result["status"] == "complete"
    assert all(value is eligible for value in result["metric_eligibility"].values())


def test_complete_set_preserves_provenance_and_is_metric_eligible() -> None:
    result = evaluate_member_set(
        provider_id="icon_d2_eps",
        member_ids=_ids(20),
        model_versions=("2026-09",),
        init_time_utc="2026-09-25T00:00:00Z",
        valid_time_utc="2026-09-25T12:00:00Z",
        lead_hours=12,
        variable="temperature_2m",
        source_surface="Open-Meteo Ensemble API",
        declared_member_count=20,
    )
    assert result["status"] == "complete"
    assert result["raw_member_ids"][0] == "member_00"
    assert result["canonical_member_ids"][0] == "control"
    assert result["model_versions"] == ["2026-09"]
    assert result["init_time_utc"] == "2026-09-25T00:00:00Z"
    assert result["valid_time_utc"] == "2026-09-25T12:00:00Z"
    assert result["lead_hours"] == 12
    assert result["variable"] == "temperature_2m"
    assert result["source_surface"] == "Open-Meteo Ensemble API"
    assert metric_eligible(result, "crps") is True
    assert metric_eligible(result, "brier") is True


def test_partial_and_unsupported_sets_never_become_probabilistic_metric_input() -> None:
    partial = evaluate_member_set(provider_id="icon_d2_eps", member_ids=("member_00", "member_01"))
    unsupported = evaluate_member_set(provider_id="unknown_ensemble", member_ids=("member_00",))
    for result in (partial, unsupported):
        assert metric_eligible(result, "crps") is False
        assert metric_eligible(result, "empirical_interval") is False
        assert metric_eligible(result, "member_fraction_probability") is False
        assert metric_eligible(result, "brier") is False
        assert metric_eligible(result, "reliability") is False


def test_unexpected_member_is_blocked_without_synthesizing_or_dropping_identity() -> None:
    raw = _ids(20) + ["member_20"]
    result = evaluate_member_set(provider_id="icon_d2_eps", member_ids=raw)
    assert result["status"] == "blocked"
    assert "UNEXPECTED_MEMBER_ID" in result["reason_codes"]
    assert "member20" in result["unexpected_member_ids"]
    assert "member_20" in result["raw_member_ids"]


def test_run_member_set_change_blocks_run_level_metric_eligibility() -> None:
    first = evaluate_member_set(provider_id="icon_d2_eps", member_ids=_ids(20))
    second = evaluate_member_set(provider_id="icon_d2_eps", member_ids=_ids(19))
    result = evaluate_run_stability((first, second))
    assert result["status"] == "blocked"
    assert result["reason_codes"] == ["MEMBER_SET_CHANGED"]
    assert result["distinct_member_sets"] == 2
    assert all(value is False for value in result["metric_eligibility"].values())


def test_unknown_metric_name_fails_closed() -> None:
    evidence = evaluate_member_set(provider_id="icon_d2_eps", member_ids=_ids(20))
    with pytest.raises(ValueError, match="unsupported ensemble metric"):
        metric_eligible(evidence, "ranking")
