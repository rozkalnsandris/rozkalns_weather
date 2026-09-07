from .base import ProviderDescriptor

PROVIDERS = (
    ProviderDescriptor(
        id="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        role="primary_research",
        transport="BigQuery",
    ),
    ProviderDescriptor(
        id="dwd_mosmix_l",
        model_provider="DWD",
        model_name="MOSMIX-L",
        role="local_baseline",
        transport="DWD Open Data",
        station_id="10416",
    ),
    ProviderDescriptor(
        id="dwd_observations",
        model_provider="DWD",
        model_name="Observations",
        role="verification_truth",
        transport="Bright Sky / DWD Open Data",
        station_id="10416",
    ),
    ProviderDescriptor(
        id="icon_d2",
        model_provider="DWD",
        model_name="ICON-D2",
        role="short_range_baseline",
        transport="Open-Meteo",
    ),
    ProviderDescriptor(
        id="ecmwf_ifs",
        model_provider="ECMWF",
        model_name="IFS HRES",
        role="global_nwp_baseline",
        transport="Open-Meteo",
    ),
    ProviderDescriptor(
        id="ecmwf_aifs",
        model_provider="ECMWF",
        model_name="AIFS",
        role="ai_baseline",
        transport="Open-Meteo",
    ),
)

__all__ = ["PROVIDERS", "ProviderDescriptor"]
