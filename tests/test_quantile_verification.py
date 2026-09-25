import pytest

from rozkalns_weather.quantile_admissibility import evaluate_quantile_set
from rozkalns_weather.verification import summary_quantile_coverage


def _records(values: dict[str, float]) -> list[dict[str, object]]:
    identity = {
        "provider": "weathernext3",
        "model_name": "WeatherNext 3",
        "model_version": "3.0.0",
        "init_time_utc": "2026-09-12T00:00:00Z",
        "retrieved_at_utc": "2026-09-12T00:30:00Z",
        "valid_time_utc": "2026-09-12T12:00:00Z",
        "lead_hours": 12,
        "variable": "temperature_2m",
        "unit": "degC",
        "location_id": "station_05480",
        "source_surface": "weathernext_3_0_0_0p05deg",
        "resolution": "0.05deg",
    }
    return [dict(identity, statistic=statistic, value=value) for statistic, value in values.items()]


def test_weather_next_summary_quantile_coverage_requires_admissible_set() -> None:
    evidence = evaluate_quantile_set(
        _records({"p10": 16.0, "p25": 17.0, "p50": 18.0, "p75": 19.0, "p90": 20.0})
    )
    result = summary_quantile_coverage(evidence, observed=19.5)
    assert result == {
        "quantile_admissibility_contract": "forecast-quantile-admissibility-v1",
        "representation": "summary_quantiles",
        "lower_statistic": "p10",
        "upper_statistic": "p90",
        "lower": 16.0,
        "upper": 20.0,
        "observed": 19.5,
        "covered": 1.0,
        "crps_eligible": False,
        "brier_eligible": False,
        "reliability_eligible": False,
    }


def test_crossed_quantiles_cannot_reach_coverage_scoring() -> None:
    evidence = evaluate_quantile_set(
        _records({"p10": 16.0, "p25": 19.0, "p50": 18.0, "p75": 20.0, "p90": 21.0})
    )
    assert evidence["state"] == "BLOCKED"
    with pytest.raises(ValueError, match="quantile_set_not_admissible"):
        summary_quantile_coverage(evidence, observed=18.5)


def test_incomplete_quantiles_are_not_filled_for_coverage() -> None:
    evidence = evaluate_quantile_set(
        _records({"p10": 16.0, "p25": 17.0, "p50": 18.0, "p90": 20.0})
    )
    assert evidence["missing_statistics"] == ["p75"]
    assert evidence["fabricated_statistics"] == []
    with pytest.raises(ValueError, match="quantile_set_not_admissible"):
        summary_quantile_coverage(evidence, observed=18.5)
