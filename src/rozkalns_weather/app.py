from __future__ import annotations

from fastapi import FastAPI

from .config import Settings
from .db import Database


PROVIDERS = [
    {
        "id": "weathernext3",
        "model_provider": "Google DeepMind",
        "model_name": "WeatherNext 3",
        "role": "primary_research",
        "transport": "BigQuery",
    },
    {
        "id": "dwd_mosmix_l",
        "model_provider": "DWD",
        "model_name": "MOSMIX-L",
        "role": "local_baseline",
        "station_id": "10416",
    },
    {
        "id": "dwd_observations",
        "model_provider": "DWD",
        "model_name": "Observations",
        "role": "verification_truth",
        "station_id": "10416",
    },
    {
        "id": "icon_d2",
        "model_provider": "DWD",
        "model_name": "ICON-D2",
        "role": "short_range_baseline",
    },
    {
        "id": "ecmwf_ifs",
        "model_provider": "ECMWF",
        "model_name": "IFS HRES",
        "role": "global_nwp_baseline",
    },
    {
        "id": "ecmwf_aifs",
        "model_provider": "ECMWF",
        "model_name": "AIFS",
        "role": "ai_baseline",
    },
]


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    database = database or Database(settings.database_url)
    database.initialize()

    if settings.home_configured:
        database.ensure_home_location(
            label=settings.home_label,
            lat=settings.home_lat,  # type: ignore[arg-type]
            lon=settings.home_lon,  # type: ignore[arg-type]
            timezone=settings.home_timezone,
        )

    app = FastAPI(
        title="rozkalns_weather",
        version="0.1.0",
        description="Private local weather comparison and WeatherNext 3 verification API",
    )
    app.state.settings = settings
    app.state.database = database

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "database": "ready"}

    @app.get("/api/providers")
    def providers() -> dict[str, object]:
        return {"providers": PROVIDERS}

    @app.get("/api/health/providers")
    def provider_health() -> dict[str, object]:
        provider_states = []
        for provider in PROVIDERS:
            state = "adapter_not_implemented"
            if provider["id"] == "weathernext3":
                state = (
                    "configured"
                    if settings.weathernext_configured
                    else "awaiting_access_or_config"
                )
            provider_states.append(
                {
                    "id": provider["id"],
                    "model_name": provider["model_name"],
                    "state": state,
                }
            )

        return {
            "location": {
                "id": "home",
                "label": settings.home_label,
                "configured": settings.home_configured,
                "coordinates_exposed": False,
                "timezone": settings.home_timezone,
            },
            "database": {
                "state": "ready",
                "tables": sorted(database.table_names()),
            },
            "providers": provider_states,
        }

    return app


app = create_app()
