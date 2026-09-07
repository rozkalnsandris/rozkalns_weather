from datetime import datetime, timezone

import pytest

from rozkalns_weather.verification import (
    ErrorPair,
    ProbabilityPair,
    brier_score,
    forecast_was_available,
    lead_bucket,
    reliability_bins,
    summarize,
)


def test_metrics_and_weather_next_interval_coverage() -> None:
    pairs = [
        ErrorPair("weathernext3", "3.0.0", 12, 20, 19, 18, 21),
        ErrorPair("weathernext3", "3.0.0", 24, 18, 20, 17, 19),
    ]
    result = summarize(pairs)
    assert result["n"] == 2
    assert result["mae"] == 1.5
    assert result["bias"] == -0.5
    assert result["p10_p90_coverage"] == 0.5
    assert lead_bucket(12) == "12-24h"


def test_user_available_skill_requires_upstream_and_local_retrieval() -> None:
    upstream = datetime(2026, 9, 7, 14, 10, tzinfo=timezone.utc)
    retrieved = datetime(2026, 9, 7, 14, 15, tzinfo=timezone.utc)
    assert not forecast_was_available(
        upstream_available_at_utc=upstream,
        retrieved_at_utc=retrieved,
        decision_time_utc=datetime(2026, 9, 7, 14, 12, tzinfo=timezone.utc),
    )
    assert forecast_was_available(
        upstream_available_at_utc=upstream,
        retrieved_at_utc=retrieved,
        decision_time_utc=datetime(2026, 9, 7, 14, 15, tzinfo=timezone.utc),
    )


def test_probability_metrics_never_accept_percent_or_amount_as_probability() -> None:
    pairs = [
        ProbabilityPair("dwd_icon_eps", 12, 0.8, 1.0),
        ProbabilityPair("dwd_icon_eps", 12, 0.2, 0.0),
    ]
    result = brier_score(pairs)
    assert result["n"] == 2
    assert result["brier_score"] == pytest.approx(0.04)
    bins = reliability_bins(pairs, bins=5)
    assert sum(int(item["n"]) for item in bins) == 2
    with pytest.raises(ValueError, match="probability"):
        ProbabilityPair("invalid", 12, 80.0, 1.0)
