from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import Database
from .providers import PROVIDERS
from .providers.weathernext import access_state
from .radar_warnings import fetch_dwd_alerts, fetch_radar_point
from .verification import ErrorPair, lead_bucket, summarize


def _descriptor(provider) -> dict[str, object]:
    return {
        "id": provider.id,
        "model_provider": provider.model_provider,
        "model_name": provider.model_name,
        "role": provider.role,
        "transport": provider.transport,
        **({"station_id": provider.station_id} if provider.station_id else {}),
    }


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = database or Database(settings.database_url)
    database.initialize()

    if settings.home_configured:
        database.ensure_home_location(label=settings.home_label, lat=settings.home_lat, lon=settings.home_lon, timezone=settings.home_timezone)  # type: ignore[arg-type]

    app = FastAPI(title="rozkalns_weather", version="0.2.0", description="Private local weather comparison and WeatherNext 3 verification API")
    app.state.settings = settings
    app.state.database = database

    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "database": "ready", "home_configured": settings.home_configured}

    @app.get("/api/providers")
    def providers() -> dict[str, object]:
        return {"providers": [_descriptor(provider) for provider in PROVIDERS]}

    @app.get("/api/health/providers")
    def provider_health() -> dict[str, object]:
        stored = database.provider_statuses()
        now = datetime.now(timezone.utc)
        provider_states = []
        for provider in PROVIDERS:
            state = stored.get(provider.id, {}).get("state", "adapter_ready_not_ingested")
            if provider.id == "weathernext3" and provider.id not in stored:
                state = access_state(configured=settings.weathernext_configured, now=now)
            provider_states.append({"id": provider.id, "model_name": provider.model_name, "state": state, "last_success_at_utc": stored.get(provider.id, {}).get("last_success_at_utc")})
        return {
            "location": {"id": "home", "label": settings.home_label, "configured": settings.home_configured, "coordinates_exposed": False, "timezone": settings.home_timezone},
            "database": {"state": "ready", "tables": sorted(database.table_names())},
            "providers": provider_states,
        }

    @app.get("/api/hourly")
    def hourly(hours: int = Query(48, ge=1, le=360), variable: str = Query("temperature_2m")) -> dict[str, object]:
        return {"hours": hours, "variable": variable, "location": {"id": "home", "label": settings.home_label, "coordinates_exposed": False}, "series": database.latest_hourly(hours=hours, variable=variable)}

    @app.get("/api/verification/summary")
    def verification_summary(days: int = Query(90, ge=1, le=3650)) -> dict[str, object]:
        rows = database.temperature_verification_pairs(days=days)
        by_provider: dict[str, list[ErrorPair]] = {}
        by_bucket: dict[str, dict[str, list[ErrorPair]]] = {}
        for row in rows:
            pair = ErrorPair(provider=str(row["provider"]), model_version=row.get("model_version"), lead_hours=float(row["lead_hours"]), forecast=float(row["forecast_value"]), observed=float(row["observed_value"]), p10=float(row["p10"]) if row.get("p10") is not None else None, p90=float(row["p90"]) if row.get("p90") is not None else None)
            by_provider.setdefault(pair.provider, []).append(pair)
            by_bucket.setdefault(pair.provider, {}).setdefault(lead_bucket(pair.lead_hours), []).append(pair)
        provider_payload: dict[str, object] = {}
        for provider, pairs in by_provider.items():
            versions: dict[str, list[ErrorPair]] = {}
            for pair in pairs:
                versions.setdefault(pair.model_version or "unknown", []).append(pair)
            provider_payload[provider] = {
                "overall": summarize(pairs),
                "by_lead_bucket": {bucket: summarize(items) for bucket, items in by_bucket.get(provider, {}).items()},
                "by_model_version": {version: summarize(items) for version, items in versions.items()},
            }
        return {"window_days": days, "variable": "temperature_2m", "matching_tolerance_minutes": 0, "providers": provider_payload}

    @app.get("/api/warnings")
    def warnings() -> dict[str, object]:
        if not settings.home_configured:
            raise HTTPException(status_code=503, detail="home location is not configured")
        return fetch_dwd_alerts(lat=settings.home_lat, lon=settings.home_lon)  # type: ignore[arg-type]

    @app.get("/api/radar")
    def radar() -> dict[str, object]:
        if not settings.home_configured:
            raise HTTPException(status_code=503, detail="home location is not configured")
        return fetch_radar_point(lat=settings.home_lat, lon=settings.home_lon)  # type: ignore[arg-type]

    return app


app = create_app()
