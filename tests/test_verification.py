from rozkalns_weather.verification import ErrorPair, lead_bucket, summarize


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
