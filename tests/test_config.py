import pytest

from rozkalns_weather.config import Settings


def test_public_only_is_default() -> None:
    settings = Settings.from_env({})
    assert settings.runtime_mode == "public-only"
    assert settings.home_configured is False


def test_home_coordinates_are_atomic() -> None:
    with pytest.raises(ValueError, match="configured together"):
        Settings.from_env({"HOME_LAT": "51.5"})


def test_private_home_requires_coordinates() -> None:
    with pytest.raises(ValueError, match="requires HOME_LAT/HOME_LON"):
        Settings.from_env({"WEATHER_RUNTIME_MODE": "private-home"})


def test_private_home_accepts_runtime_only_coordinates() -> None:
    settings = Settings.from_env({
        "WEATHER_RUNTIME_MODE": "private-home",
        "HOME_LAT": "51.5",
        "HOME_LON": "7.6",
    })
    assert settings.home_configured is True


def test_public_only_rejects_private_home_coordinates() -> None:
    with pytest.raises(ValueError, match="must not include"):
        Settings.from_env({"HOME_LAT": "51.5", "HOME_LON": "7.6"})
