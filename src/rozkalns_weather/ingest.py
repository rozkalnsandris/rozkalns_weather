from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .config import Settings
from .db import Database
from .providers.dwd_mosmix import DwdMosmixAdapter
from .providers.dwd_observations import DwdObservationAdapter
from .providers.open_meteo import ECMWF_AIFS, ECMWF_IFS, ICON_D2, OpenMeteoAdapter


def ingest_public_baselines(settings: Settings, database: Database) -> dict[str, str]:
    results: dict[str, str] = {}
    now = datetime.now(timezone.utc)

    def run(provider: str, action: Callable[[], None]) -> None:
        try:
            action()
            database.set_provider_status(provider, state="ok", now=now)
            results[provider] = "ok"
        except Exception as exc:
            database.set_provider_status(provider, state="error", now=now, detail=type(exc).__name__)
            results[provider] = "error"

    run("dwd_mosmix_l", lambda: database.insert_forecast_run(DwdMosmixAdapter().fetch(retrieved_at=now)))
    run("dwd_observations", lambda: database.insert_observations(DwdObservationAdapter().fetch(now=now)))

    if not settings.home_configured:
        for provider in ("icon_d2", "ecmwf_ifs", "ecmwf_aifs"):
            database.set_provider_status(provider, state="home_location_not_configured", now=now)
            results[provider] = "home_location_not_configured"
        return results

    assert settings.home_lat is not None and settings.home_lon is not None
    for model in (ICON_D2, ECMWF_IFS, ECMWF_AIFS):
        run(model.provider_id, lambda m=model: database.insert_forecast_run(OpenMeteoAdapter(m).fetch(lat=settings.home_lat, lon=settings.home_lon, retrieved_at=now)))
    return results
