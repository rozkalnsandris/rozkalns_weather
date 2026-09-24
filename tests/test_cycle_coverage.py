from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

from rozkalns_weather.corpus_reporting import public_corpus_report
from rozkalns_weather.cycle_coverage import (
    CYCLE_COVERAGE_REGISTRY_VERSION,
    CYCLE_HORIZON_REGISTRY,
    INIT_CYCLE_UNOBSERVABLE,
    comparison_lead_intersection,
    contract_for,
    cycle_class_coverage,
    evaluate_run_coverage,
    registry_payload,
)
from rozkalns_weather.db import Database

FIXTURES = Path(__file__).parent / "fixtures" / "cycle_coverage_cases.json"
CONTRACT = Path(__file__).parents[1] / "contracts" / "forecast-cycle-coverage-v1.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_machine_registry_matches_python_registry() -> None:
    assert json.loads(CONTRACT.read_text(encoding="utf-8")) == registry_payload()
    assert CYCLE_COVERAGE_REGISTRY_VERSION == "forecast-cycle-coverage-v1"


def test_supported_contracts_include_public_weather_and_ensemble_surfaces() -> None:
    assert {"icon_d2", "ecmwf_ifs", "ecmwf_aifs", "weathernext3"} <= set(CYCLE_HORIZON_REGISTRY)
    assert {"icon_d2_eps", "ecmwf_ifs_ens", "ecmwf_aifs_ens", "weathernext2_legacy"} <= set(CYCLE_HORIZON_REGISTRY)
    ifs = contract_for("ecmwf_ifs")
    assert ifs.horizon_for_cycle(0) == 240
    assert ifs.horizon_for_cycle(6) == 144
    wn = contract_for("weathernext3")
    assert wn.horizon_for_cycle(0) == 360
    assert wn.horizon_for_cycle(1) == 48


def test_open_meteo_ensemble_cycle_identity_is_not_fabricated() -> None:
    result = evaluate_run_coverage(
        "ecmwf_ifs_ens",
        init_time="2026-08-13T00:00:00Z",
        lead_hours=[0, 24, 48],
    )
    assert result["state"] == "UNOBSERVABLE"
    assert result["reason_codes"] == [INIT_CYCLE_UNOBSERVABLE]
    assert result["contract"]["expected_cycle_hours_utc"] == []


def test_run_coverage_fixture_cases() -> None:
    for case in _fixture()["run_cases"]:
        result = evaluate_run_coverage(
            case["provider_id"],
            init_time=case["init_time"],
            lead_hours=case["lead_hours"],
            model_version="fixture-v1",
            declared_horizon_hours=case.get("declared_horizon_hours"),
        )
        assert result["state"] == case["expected_state"], case["id"]
        assert result["reason_codes"] == case["expected_reasons"], case["id"]
        assert result["registry_version"] == CYCLE_COVERAGE_REGISTRY_VERSION
        assert result["model_version"] == "fixture-v1"


def test_missing_cycle_fixture() -> None:
    case = _fixture()["cycle_cases"][0]
    result = cycle_class_coverage(case["provider_id"], case["init_times"])
    assert result["state"] == case["expected_state"]
    assert result["missing_cycle_hours_utc"] == case["expected_missing_cycle_hours_utc"]
    assert result["reason_codes"] == ["MISSING_CYCLE_CLASS"]


def test_comparison_intersection_fixture_cases() -> None:
    for case in _fixture()["comparison_cases"]:
        result = comparison_lead_intersection(
            case["providers"],
            init_hour_utc=case["init_hour_utc"],
            requested_max_lead_hours=case["requested_max_lead_hours"],
        )
        assert result["state"] == case["expected_state"], case["id"]
        assert result["common_max_lead_hours"] == case["expected_common_max_lead_hours"]
        assert result["reason_codes"] == case["expected_reasons"]


def test_model_version_boundary_does_not_change_frozen_horizon() -> None:
    old = evaluate_run_coverage(
        "icon_d2",
        init_time=datetime(2026, 8, 13, tzinfo=timezone.utc),
        lead_hours=[0, 48],
        model_version="old-version",
    )
    new = evaluate_run_coverage(
        "icon_d2",
        init_time=datetime(2026, 8, 14, tzinfo=timezone.utc),
        lead_hours=[0, 48],
        model_version="new-version",
    )
    assert old["expected_horizon_hours"] == new["expected_horizon_hours"] == 48
    assert old["model_version"] != new["model_version"]
    assert old["registry_version"] == new["registry_version"]


def test_public_corpus_readiness_exposes_cycle_registry_without_writes(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'weather.db'}")
    database.initialize()
    report = public_corpus_report(database, start=date(2026, 4, 2), end=date(2026, 4, 2))
    assert report["cycle_horizon_registry_version"] == CYCLE_COVERAGE_REGISTRY_VERSION
    icon = next(item for item in report["models"] if item["provider"] == "icon_d2")
    assert icon["cycle_horizon_contract"]["registry_version"] == CYCLE_COVERAGE_REGISTRY_VERSION
    assert icon["cycle_horizon_contract"]["contract"]["horizon_by_cycle_hours"]["00"] == 48
    assert icon["cycle_horizon_contract"]["cycle_class_coverage"]["state"] == "BLOCKED"
    assert "ICON_D2_MISSING_CYCLE_CLASS" in report["block_reasons"]
    assert report["read_only"] is True
