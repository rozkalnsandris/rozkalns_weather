from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation
from rozkalns_weather.precip_events import (
    DEFAULT_PRECIP_EVENT,
    PRECIP_EVENT_REGISTRY_VERSION,
    registry_payload,
)
from rozkalns_weather.probabilistic import event_probability
from rozkalns_weather.reporting import monthly_weather_next_report
from rozkalns_weather.verification import ProbabilityPair, brier_score, reliability_bins

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = Path(__file__).parent / "fixtures" / "precip_event_registry_cases.json"
GOLDEN_PATH = Path(__file__).parent / "fixtures" / "verification_golden_corpus.json"
CONTRACT_PATH = ROOT / "contracts" / "precip-event-registry-v1.json"


def _cases() -> dict[str, object]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_machine_readable_contract_matches_runtime_registry() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract == registry_payload()
    assert contract["registry_version"] == PRECIP_EVENT_REGISTRY_VERSION
    assert contract["events"][0] == DEFAULT_PRECIP_EVENT.as_dict()


def test_threshold_boundary_and_amount_semantics_are_frozen() -> None:
    cases = _cases()
    assert cases["event_id"] == DEFAULT_PRECIP_EVENT.event_id
    for case in cases["boundary_cases"]:
        assert DEFAULT_PRECIP_EVENT.event_occurs(
            case["value"],
            variable="precipitation_1h",
            unit="mm",
            accumulation_window_minutes=60,
        ) is case["expected"]

    for case in cases["mismatch_cases"]:
        with pytest.raises(ValueError, match=case["error"]):
            DEFAULT_PRECIP_EVENT.event_occurs(
                0.2,
                variable="precipitation_1h",
                unit=case["unit"],
                accumulation_window_minutes=case["window_minutes"],
            )


def test_probability_eligibility_rejects_implicit_conversions() -> None:
    for case in _cases()["probability_source_cases"]:
        if case["eligible"]:
            assert DEFAULT_PRECIP_EVENT.validate_probability_source(case["source"]) == case["source"]
        else:
            with pytest.raises(ValueError, match="probability source"):
                DEFAULT_PRECIP_EVENT.validate_probability_source(case["source"])

    with pytest.raises(ValueError, match="probability source"):
        ProbabilityPair(
            "invalid",
            6,
            0.5,
            1.0,
            probability_source="deterministic_amount",
        )
    with pytest.raises(ValueError, match="probability source"):
        ProbabilityPair(
            "invalid",
            6,
            0.5,
            1.0,
            probability_source="summary_quantile",
        )


def test_genuine_ensemble_fraction_uses_registered_event_threshold() -> None:
    members = (0.0, 0.05, 0.1, 0.2)
    assert event_probability(members, threshold=DEFAULT_PRECIP_EVENT.threshold) == 0.5


def test_golden_probability_metrics_expose_event_definition_identity() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["explicit_precip_probability"]
    pairs = [
        ProbabilityPair(
            provider=golden["provider"],
            lead_hours=18,
            probability=item["probability"],
            observed_event=item["observed_event"],
        )
        for item in golden["pairs"]
    ]
    result = brier_score(pairs, expected_n=golden["expected_n"])
    assert result["brier_score"] == pytest.approx(golden["expected_brier"])
    assert result["event_definition"] == DEFAULT_PRECIP_EVENT.as_dict()
    assert sum(int(row["n"]) for row in reliability_bins(pairs, bins=5)) == len(pairs)


def test_monthly_report_binds_member_fraction_metrics_to_registry(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'precip-registry-report.db'}")
    database.initialize()
    database.ensure_location(
        location_id=DWD_10416.id,
        label=DWD_10416.label,
        lat=DWD_10416.lat,
        lon=DWD_10416.lon,
        elevation_m=DWD_10416.elevation_m,
        timezone=DWD_10416.timezone,
    )

    valid = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    database.insert_observations(
        [
            Observation(
                source_provider="DWD",
                station_id="10416",
                location_id=DWD_10416.id,
                observed_at_utc=valid,
                variable="precipitation_1h",
                value=0.2,
                unit="mm",
            )
        ]
    )
    database.insert_forecast_run(
        ForecastRun(
            provider="icon_d2",
            model_provider="DWD",
            model_name="ICON-D2",
            init_time_utc=valid - timedelta(hours=6),
            retrieved_at_utc=valid - timedelta(hours=5),
            source_surface="fixture",
            values=(
                ForecastValue(
                    valid_time_utc=valid,
                    lead_hours=6,
                    variable="precipitation_1h",
                    statistic="deterministic",
                    value=0.3,
                    unit="mm",
                    accumulation_window_minutes=60,
                ),
            ),
        ),
        location_id=DWD_10416.id,
    )
    database.insert_forecast_run(
        ForecastRun(
            provider="icon_d2_eps",
            model_provider="DWD",
            model_name="ICON-D2-EPS",
            init_time_utc=valid - timedelta(hours=12),
            retrieved_at_utc=valid - timedelta(hours=11),
            source_surface="fixture ensemble members",
            values=(
                ForecastValue(
                    valid_time_utc=valid,
                    lead_hours=12,
                    variable="precipitation_1h",
                    statistic="member_00",
                    value=0.0,
                    unit="mm",
                    accumulation_window_minutes=60,
                ),
                ForecastValue(
                    valid_time_utc=valid,
                    lead_hours=12,
                    variable="precipitation_1h",
                    statistic="member_01",
                    value=0.2,
                    unit="mm",
                    accumulation_window_minutes=60,
                ),
            ),
        ),
        location_id=DWD_10416.id,
    )

    report = monthly_weather_next_report(database, month="2026-09")
    expected = DEFAULT_PRECIP_EVENT.as_dict()
    assert report["precipitation_event_registry_version"] == PRECIP_EVENT_REGISTRY_VERSION
    assert report["precipitation_event_definition"] == expected
    assert report["ensemble_calibration"]["icon_d2_eps"]["precipitation_probability"]["event_definition"] == expected
