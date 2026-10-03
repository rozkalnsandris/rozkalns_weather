from .base import ProviderDescriptor

PROVIDERS = (
    ProviderDescriptor(
        id="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        role="optional_research",
        transport="Google Cloud Storage/Zarr",
    ),
    ProviderDescriptor(
        id="dwd_observations",
        model_provider="DWD",
        model_name="CDC 10-minute Current",
        role="current_truth",
        transport="DWD CDC",
        station_id="05480",
    ),
    ProviderDescriptor(
        id="icon_d2",
        model_provider="DWD",
        model_name="ICON-D2",
        role="forecast",
        transport="Open-Meteo Single Runs",
    ),
    ProviderDescriptor(
        id="ecmwf_ifs",
        model_provider="ECMWF",
        model_name="IFS HRES",
        role="forecast",
        transport="Open-Meteo Single Runs",
    ),
    ProviderDescriptor(
        id="ecmwf_aifs",
        model_provider="ECMWF",
        model_name="AIFS",
        role="forecast",
        transport="Open-Meteo Single Runs",
    ),
)

__all__ = ["PROVIDERS", "ProviderDescriptor"]
