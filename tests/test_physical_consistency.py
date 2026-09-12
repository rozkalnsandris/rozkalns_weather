from datetime import datetime, timezone

import pytest

from rozkalns_weather.models import ForecastRun, ForecastValue
from rozkalns_weather.physical_consistency import (
    PhysicalConsistencyError,
    PhysicalIdentity,
    PhysicalSample,
    report_physical_consistency,
)


def _identity(
    *,
    statistic: str = "deterministic",
    lead_hours: float = 6.0,
    location_id: str = "station_10416",
) -> PhysicalIdentity:
    return PhysicalIdentity(
        provider="fixture",
        model_name="Fixture Model",
        model_version="v1",
        init_time_utc="2026-09-12T00:00:00Z",
        valid_time_utc="2026-09-12T06:00:00Z",
        lead_hours=lead_hours,
        statistic=statistic,
        location_id=location_id,
    )


def _sample(variable: str, value: float, **identity_kwargs) -> PhysicalSample:
    return PhysicalSample(
        identity=_identity(**identity_kwargs),
        variable=variable,
        value=value,
    )


def test_valid_physical_edges_are_pass() -> None:
    report = report_physical_consistency(
        [
            _sample("temperature_2m", 10.0),
            _sample("dew_point_2m", 10.0),
            _sample("wind_speed_10m", 5.0),
            _sample("wind_gust_10m", 5.0),
            _sample("relative_humidity_2m", 0.0),
            _sample("cloud_cover", 100.0),
            _sample("precipitation_probability_1h", 100.0),
            _sample("precipitation_1h", 0.0),
        ]
    )
    assert report.state == "PASS"
    assert report.reason_codes == ()


def test_cross_variable_blockers_have_stable_reason_codes() -> None:
    dew = report_physical_consistency(
        [_sample("temperature_2m", 10.0), _sample("dew_point_2m", 10.6)]
    )
    assert dew.state == "BLOCKED"
    assert dew.blocked_reason_codes == ("DEWPOINT_ABOVE_TEMPERATURE",)

    gust = report_physical_consistency(
        [_sample("wind_speed_10m", 5.0), _sample("wind_gust_10m", 4.4)]
    )
    assert gust.state == "BLOCKED"
    assert gust.blocked_reason_codes == ("GUST_BELOW_SUSTAINED_WIND",)


def test_tolerance_level_anomalies_are_suspect_not_repaired() -> None:
    report = report_physical_consistency(
        [
            _sample("temperature_2m", 10.0),
            _sample("dew_point_2m", 10.2),
            _sample("wind_speed_10m", 5.0),
            _sample("wind_gust_10m", 4.8),
        ]
    )
    assert report.state == "SUSPECT"
    assert set(report.reason_codes) == {
        "DEWPOINT_ABOVE_TEMPERATURE_TOLERANCE",
        "GUST_BELOW_SUSTAINED_WIND_TOLERANCE",
    }
    values = {
        name: value
        for finding in report.findings
        for name, value in finding.values
    }
    assert values["dew_point_2m"] == 10.2
    assert values["wind_gust_10m"] == 4.8


@pytest.mark.parametrize(
    ("variable", "value", "reason_code"),
    [
        ("relative_humidity_2m", 101.0, "BOUNDED_FIELD_OUT_OF_RANGE"),
        ("cloud_cover", -1.0, "BOUNDED_FIELD_OUT_OF_RANGE"),
        ("precipitation_probability_1h", 101.0, "BOUNDED_FIELD_OUT_OF_RANGE"),
        ("precipitation_1h", -0.2, "NEGATIVE_MAGNITUDE"),
        ("wind_speed_10m", -0.2, "NEGATIVE_MAGNITUDE"),
        ("wind_gust_10m", -0.2, "NEGATIVE_MAGNITUDE"),
    ],
)
def test_scalar_physical_blockers(variable: str, value: float, reason_code: str) -> None:
    report = report_physical_consistency([_sample(variable, value)])
    assert report.state == "BLOCKED"
    assert reason_code in report.blocked_reason_codes


def test_incompatible_comparison_identity_is_not_cross_compared() -> None:
    report = report_physical_consistency(
        [
            _sample("temperature_2m", 10.0, statistic="deterministic"),
            _sample("dew_point_2m", 12.0, statistic="mean"),
            _sample("wind_speed_10m", 5.0, lead_hours=6.0),
            _sample("wind_gust_10m", 4.0, lead_hours=12.0),
        ]
    )
    assert report.state == "PASS"


def _run(*values: ForecastValue, provider: str = "fixture") -> ForecastRun:
    return ForecastRun(
        provider=provider,
        model_provider="Fixture",
        model_name="Fixture Model",
        model_version="v1",
        init_time_utc=datetime(2026, 9, 12, 0, tzinfo=timezone.utc),
        retrieved_at_utc=datetime(2026, 9, 12, 1, tzinfo=timezone.utc),
        source_surface="fixture",
        source_metadata={"provider_marker": "unchanged"},
        values=tuple(values),
    )


def test_forecast_run_blocks_before_corpus_admission() -> None:
    valid = datetime(2026, 9, 12, 6, tzinfo=timezone.utc)
    with pytest.raises(PhysicalConsistencyError) as error:
        _run(
            ForecastValue(valid, 6, "temperature_2m", 10.0, "degC"),
            ForecastValue(valid, 6, "dew_point_2m", 11.0, "degC"),
        )
    assert error.value.reason_codes == ("DEWPOINT_ABOVE_TEMPERATURE",)

    unrelated = _run(
        ForecastValue(valid, 6, "temperature_2m", 9.0, "degC"),
        provider="unrelated_provider",
    )
    assert unrelated.source_metadata["physical_consistency"]["state"] == "PASS"


def test_suspect_run_preserves_provider_values_and_exposes_validation_metadata() -> None:
    valid = datetime(2026, 9, 12, 6, tzinfo=timezone.utc)
    run = _run(
        ForecastValue(valid, 6, "temperature_2m", 10.0, "degC", native_value=283.15, native_unit="K"),
        ForecastValue(valid, 6, "dew_point_2m", 10.2, "degC", native_value=283.35, native_unit="K"),
    )

    assert run.values[1].value == 10.2
    assert run.values[1].native_value == 283.35
    assert run.source_metadata["provider_marker"] == "unchanged"
    validation = run.source_metadata["physical_consistency"]
    assert validation["contract_version"] == "forecast-physical-v1"
    assert validation["state"] == "SUSPECT"
    assert validation["reason_codes"] == ["DEWPOINT_ABOVE_TEMPERATURE_TOLERANCE"]
