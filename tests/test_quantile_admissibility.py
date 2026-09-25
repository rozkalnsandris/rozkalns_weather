import json
from pathlib import Path

import pytest

from rozkalns_weather.quantile_admissibility import (
    CONTRACT_VERSION,
    evaluate_quantile_set,
    interval_bounds,
)
from rozkalns_weather.semantics import statistic_family

FIXTURE = Path(__file__).parent / "fixtures" / "forecast_quantile_admissibility.json"


def _records(payload: dict[str, object], scenario: dict[str, object]) -> list[dict[str, object]]:
    base = dict(payload["base_identity"])
    values = dict(scenario["values"])
    records = [dict(base, statistic=statistic, value=value) for statistic, value in values.items()]

    override = scenario.get("override")
    if isinstance(override, dict):
        target = str(override["statistic"])
        for record in records:
            if record["statistic"] == target:
                record[str(override["field"])] = override["value"]
                break

    duplicate = scenario.get("duplicate")
    if isinstance(duplicate, dict):
        records.append(
            dict(base, statistic=str(duplicate["statistic"]), value=duplicate["value"])
        )
    return records


def test_fixture_scenarios_are_deterministic() -> None:
    payload = json.loads(FIXTURE.read_text())
    for scenario in payload["scenarios"]:
        evidence = evaluate_quantile_set(_records(payload, scenario))
        assert evidence["contract_version"] == CONTRACT_VERSION
        assert evidence["state"] == scenario["expected_state"], scenario["name"]
        for reason in scenario["expected_reasons"]:
            assert reason in evidence["reason_codes"], scenario["name"]


def test_valid_and_equal_quantiles_allow_interval_coverage_only() -> None:
    payload = json.loads(FIXTURE.read_text())
    for name in ("valid_quantiles", "equal_quantiles"):
        scenario = next(item for item in payload["scenarios"] if item["name"] == name)
        evidence = evaluate_quantile_set(_records(payload, scenario))
        assert evidence["state"] == "PASS"
        assert evidence["metric_eligibility"] == {
            "interval_coverage": True,
            "summary_interval": True,
            "crps": False,
            "brier": False,
            "reliability": False,
        }
        assert evidence["representation"] == "summary_quantiles"
        assert evidence["ensemble_members"] is False
        assert evidence["event_probability"] is False
        assert evidence["fabricated_statistics"] == []
        assert interval_bounds(evidence) == (
            float(scenario["values"]["p10"]),
            float(scenario["values"]["p90"]),
        )


def test_crossing_and_incomplete_sets_fail_closed_without_fabrication() -> None:
    payload = json.loads(FIXTURE.read_text())
    for name in ("crossing_pair", "incomplete_set", "duplicate_statistic"):
        scenario = next(item for item in payload["scenarios"] if item["name"] == name)
        evidence = evaluate_quantile_set(_records(payload, scenario))
        assert evidence["state"] == "BLOCKED"
        assert evidence["metric_eligibility"]["interval_coverage"] is False
        assert evidence["fabricated_statistics"] == []
        with pytest.raises(ValueError, match="quantile_set_not_admissible"):
            interval_bounds(evidence)


def test_identity_gate_requires_same_run_and_surface_provenance() -> None:
    payload = json.loads(FIXTURE.read_text())
    expected = {
        "mixed_provenance": "MIXED_MODEL_VERSION",
        "mixed_unit": "MIXED_UNIT",
        "mixed_source_surface": "MIXED_SOURCE_SURFACE",
        "mixed_resolution": "MIXED_RESOLUTION",
    }
    for name, reason in expected.items():
        scenario = next(item for item in payload["scenarios"] if item["name"] == name)
        evidence = evaluate_quantile_set(_records(payload, scenario))
        assert evidence["state"] == "BLOCKED"
        assert reason in evidence["reason_codes"]


def test_summary_quantiles_never_become_members_or_probabilities() -> None:
    for statistic in ("p10", "p25", "p50", "p75", "p90"):
        assert statistic_family(statistic) == "summary_quantile"
    assert statistic_family("member_01") == "ensemble_member"
    assert statistic_family("probability") == "event_probability"


def test_non_summary_statistics_are_rejected() -> None:
    payload = json.loads(FIXTURE.read_text())
    scenario = next(item for item in payload["scenarios"] if item["name"] == "valid_quantiles")
    records = _records(payload, scenario)
    records[-1]["statistic"] = "member_01"
    evidence = evaluate_quantile_set(records)
    assert evidence["state"] == "BLOCKED"
    assert "NON_SUMMARY_QUANTILE" in evidence["reason_codes"]
    assert "INCOMPLETE_QUANTILE_SET" in evidence["reason_codes"]
    assert "UNEXPECTED_QUANTILE_STATISTIC" in evidence["reason_codes"]
