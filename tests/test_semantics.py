from rozkalns_weather.semantics import PROVIDER_NATIVE_MAPS, VARIABLES


def test_shared_semantics_align_core_providers() -> None:
    assert VARIABLES["precipitation_1h"]["window_minutes"] == 60
    assert PROVIDER_NATIVE_MAPS["dwd_mosmix_l"]["TTT"] == "temperature_2m"
    assert PROVIDER_NATIVE_MAPS["weathernext3"]["station_head_temperature_2m"] == "temperature_2m"
    assert PROVIDER_NATIVE_MAPS["open_meteo"]["temperature_2m"] == "temperature_2m"
