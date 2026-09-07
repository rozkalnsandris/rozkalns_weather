import pytest

from rozkalns_weather.config import Settings


def test_home_can_be_unconfigured() -> None:
    settings = Settings.from_env({})
    assert settings.home_configured is False
    assert settings.home_label == "Dortmund-Wickede"
    assert settings.home_timezone == "Europe/Berlin"


def test_home_coordinates_are_loaded_together() -> None:
    settings = Settings.from_env({"HOME_LAT": "51.5", "HOME_LON": "7.6"})
    assert settings.home_configured is True
    assert settings.home_lat == 51.5
    assert settings.home_lon == 7.6


def test_partial_home_coordinates_are_rejected() -> None:
    with pytest.raises(ValueError, match="configured together"):
        Settings.from_env({"HOME_LAT": "51.5"})


def test_coordinate_ranges_are_validated() -> None:
    with pytest.raises(ValueError, match="HOME_LAT"):
        Settings.from_env({"HOME_LAT": "91", "HOME_LON": "7.6"})
