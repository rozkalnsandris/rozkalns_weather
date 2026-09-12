from datetime import datetime, timezone

import pytest

from rozkalns_weather.models import ForecastValue
from rozkalns_weather.semantics import (
    PROVIDER_NATIVE_MAPS,
    VARIABLES,
    SEMANTIC_CONTRACT_VERSION,
    SemanticGateError,
    enforce_metric_eligibility,
    enforce_semantic_slice,
    semantic_identity,
)


def test_shared_semantics_align_core_providers() -> None:
    assert VARIABLES["precipitation_1h"]["window_minutes"] == 60
    assert PROVIDER_NATIVE_MAPS["dwd_mosmix_l"]["TTT"] == "temperature_2m"
    assert PROVIDER_NATIVE_MAPS["weathernext3"]["station_head_temperature_2m"] == "temperature_2m"
    assert PROVIDER_NATIVE_MAPS["open_meteo"]["temperature_2m"] == "temperature_2m"


def test_forecast_value_rejects_unit_window_and_statistic_drift() -> None:
    base = {
        "valid_time_utc": datetime(2026, 9, 12, 12, tzinfo=timezone.utc),
        "lead_hours": 6,
        "value": 1.0,
    }
    with pytest.raises(SemanticGateError, match="invalid_unit"):
        ForecastValue(**base, variable="temperature_2m", unit="K")
    with pytest.raises(SemanticGateError, match="invalid_window"):
        ForecastValue(
            **base,
            variable="precipitation_1h",
            unit="mm",
            accumulation_window_minutes=180,
        )
    with pytest.raises(SemanticGateError, match="invalid_statistic"):
        ForecastValue(
            **base,
            variable="temperature_2m",
            unit="degC",
            statistic="probability",
        )


def test_normalized_semantic_identity_preserves_native_provenance_separately() -> None:
    value = ForecastValue(
        valid_time_utc=datetime(2026, 9, 12, 12, tzinfo=timezone.utc),
        lead_hours=6,
        variable="temperature_2m",
        statistic="mean",
        value=20.0,
        unit="degC",
        native_value=293.15,
        native_unit="K",
    )
    assert value.native_unit == "K"
    assert value.native_value == 293.15
    assert value.semantic_identity.normalized_dict() == {
        "contract_version": SEMANTIC_CONTRACT_VERSION,
        "variable": "temperature_2m",
        "unit": "degC",
        "kind": "instantaneous",
        "accumulation_window_minutes": None,
        "statistic_family": "summary_mean",
        "event_version": None,
    }


def test_semantic_slice_rejects_mixed_variables() -> None:
    temperature = semantic_identity(
        variable="temperature_2m",
        statistic="deterministic",
        value=20.0,
        unit="degC",
        accumulation_window_minutes=None,
    )
    wind = semantic_identity(
        variable="wind_speed_10m",
        statistic="deterministic",
        value=4.0,
        unit="m/s",
        accumulation_window_minutes=None,
    )
    with pytest.raises(SemanticGateError, match="mixed_semantic_slice"):
        enforce_semantic_slice((temperature, wind))


def test_metric_eligibility_distinguishes_members_quantiles_and_amounts() -> None:
    member = semantic_identity(
        variable="precipitation_1h",
        statistic="member_00",
        value=0.2,
        unit="mm",
        accumulation_window_minutes=60,
    )
    assert enforce_metric_eligibility(member, metric="crps") == "genuine_ensemble_members"
    assert enforce_metric_eligibility(member, metric="brier") == "ensemble_member_fraction"

    weather_next_quantile = semantic_identity(
        variable="temperature_2m",
        statistic="p10",
        value=18.0,
        unit="degC",
        accumulation_window_minutes=None,
    )
    with pytest.raises(SemanticGateError, match="metric_ineligible:crps"):
        enforce_metric_eligibility(weather_next_quantile, metric="crps")

    deterministic_amount = semantic_identity(
        variable="precipitation_1h",
        statistic="deterministic",
        value=0.2,
        unit="mm",
        accumulation_window_minutes=60,
    )
    with pytest.raises(SemanticGateError, match="metric_ineligible:brier"):
        enforce_metric_eligibility(deterministic_amount, metric="brier")
