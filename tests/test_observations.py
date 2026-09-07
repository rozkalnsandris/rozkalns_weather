from rozkalns_weather.providers.dwd_observations import parse_brightsky_observations


def test_brightsky_observations_keep_wmo_provenance() -> None:
    payload = {
        "sources": [{"id": 7, "wmo_station_id": "10416", "dwd_station_id": "01234", "station_name": "Dortmund"}],
        "weather": [{"timestamp": "2026-09-07T08:00:00+00:00", "source_id": 7, "temperature": 19.5, "pressure_msl": 1012.3}],
    }
    items = parse_brightsky_observations(payload)
    temp = next(x for x in items if x.variable == "temperature_2m")
    assert temp.station_id == "10416"
    assert temp.value == 19.5
    assert temp.source_metadata["transport"] == "Bright Sky"
