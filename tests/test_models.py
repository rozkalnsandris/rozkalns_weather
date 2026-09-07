from datetime import datetime

import pytest

from rozkalns_weather.models import ForecastValue, parse_time, utc_iso


def test_time_helpers_store_utc() -> None:
    dt = parse_time("2026-09-07T08:00:00+02:00")
    assert utc_iso(dt) == "2026-09-07T06:00:00Z"


def test_forecast_value_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ForecastValue(
            valid_time_utc=datetime(2026, 9, 7, 8),
            lead_hours=1,
            variable="temperature_2m",
            value=20,
            unit="degC",
        )
