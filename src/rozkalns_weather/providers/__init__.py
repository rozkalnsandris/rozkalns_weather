from .base import ProviderDescriptor

PROVIDERS = (
    ProviderDescriptor(id="weathernext3", model_provider="Google DeepMind", model_name="WeatherNext 3", role="primary_research", transport="BigQuery"),
    ProviderDescriptor(id="dwd_mosmix_l", model_provider="DWD", model_name="MOSMIX-L", role="local_baseline", transport="DWD Open Data", station_id="10416"),
    ProviderDescriptor(id="dwd_observations", model_provider="DWD", model_name="Observations", role="verification_truth", transport="Bright Sky / DWD Open Data", station_id="10416"),
    ProviderDescriptor(id="icon_d2", model_provider="DWD", model_name="ICON-D2", role="deterministic_baseline", transport="Open-Meteo Single Runs"),
    ProviderDescriptor(id="ecmwf_ifs", model_provider="ECMWF", model_name="IFS HRES", role="deterministic_baseline", transport="Open-Meteo Single Runs"),
    ProviderDescriptor(id="ecmwf_aifs", model_provider="ECMWF", model_name="AIFS", role="deterministic_ai_baseline", transport="Open-Meteo Single Runs"),
    ProviderDescriptor(id="icon_d2_eps", model_provider="DWD", model_name="ICON-D2-EPS", role="ensemble_baseline", transport="Open-Meteo Ensemble API"),
    ProviderDescriptor(id="ecmwf_ifs_ens", model_provider="ECMWF", model_name="IFS ENS 0.25°", role="ensemble_baseline", transport="Open-Meteo Ensemble API"),
    ProviderDescriptor(id="ecmwf_aifs_ens", model_provider="ECMWF", model_name="AIFS ENS 0.25°", role="ensemble_ai_baseline", transport="Open-Meteo Ensemble API"),
    ProviderDescriptor(id="weathernext2_legacy", model_provider="Google DeepMind", model_name="WeatherNext 2", role="legacy_ai_context", transport="Open-Meteo Ensemble API"),
)

__all__ = ["PROVIDERS", "ProviderDescriptor"]
