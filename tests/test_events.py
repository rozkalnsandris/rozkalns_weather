from rozkalns_weather.events import EventPair, matched_event_groups, summarize_events


def test_event_summary_counts_hits_misses_and_false_alarms() -> None:
    pairs = [
        EventPair("icon", "precipitation_1h", 6, 0.2, 0.3, 0.1),
        EventPair("icon", "precipitation_1h", 6, 0.0, 0.2, 0.1),
        EventPair("icon", "precipitation_1h", 6, 0.2, 0.0, 0.1),
        EventPair("icon", "precipitation_1h", 6, 0.0, 0.0, 0.1),
    ]
    summary = summarize_events(pairs)
    assert summary["hits"] == 1
    assert summary["misses"] == 1
    assert summary["false_alarms"] == 1
    assert summary["correct_negatives"] == 1
    assert summary["hit_rate"] == 0.5
    assert summary["false_alarm_ratio"] == 0.5
    assert summary["critical_success_index"] == 1 / 3


def test_temperature_cold_extreme_supports_at_or_below() -> None:
    pair = EventPair("ifs", "temperature_2m", 24, -3.0, -4.0, -2.0, direction="at_or_below")
    assert pair.forecast_event() is True
    assert pair.observed_event() is True


def test_groups_preserve_variable_threshold_and_model_version() -> None:
    rows = matched_event_groups(
        [
            EventPair("icon", "wind_gust_10m", 12, 15.0, 16.0, 14.0, model_version="v1"),
            EventPair("icon", "wind_gust_10m", 18, 13.0, 16.0, 14.0, model_version="v1"),
        ]
    )
    assert len(rows) == 1
    assert rows[0]["variable"] == "wind_gust_10m"
    assert rows[0]["threshold"] == 14.0
    assert rows[0]["model_version"] == "v1"
    assert rows[0]["mean_lead_hours"] == 15.0
