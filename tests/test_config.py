import pytest

from rozkalns_weather.config import Settings


def test_home_point_is_optional_but_atomic() -> None:
    assert Settings.from_env({}).home_configured is False
    with pytest.raises(ValueError, match="configured together"):
        Settings.from_env({"HOME_LAT": "51.5"})


def test_weather_next_requires_home_and_cloud_config() -> None:
    settings = Settings.from_env({"GOOGLE_CLOUD_PROJECT": "demo", "WEATHERNEXT_BIGQUERY_DATASET": "weather"})
    assert settings.weathernext_configured is False
    configured = Settings.from_env({"HOME_LAT":"51.5","HOME_LON":"7.6","GOOGLE_CLOUD_PROJECT":"demo","WEATHERNEXT_BIGQUERY_DATASET":"weather"})
    assert configured.weathernext_configured is True
