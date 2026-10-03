from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .current_store import latest_current_observations
from .db import Database
from .leaderboard import SkillSample, common_sample_leaderboard
from .locations import BENCHMARK_LOCATION
from .models import parse_time
from .providers import PROVIDERS
from .providers.dwd_cdc_observations import CDC_STATION_ID
from .provider_health import PUBLIC_PROVIDER_HEALTH_POLICIES, classify_public_provider_health
from .provenance_api import blocked_trace_response, hourly_with_provenance, verification_value_trace
from .radar_warnings import fetch_dwd_alerts, fetch_dwd_radar_map_png, fetch_radar_point
from .runtime import database_schema_state, readiness_payload
from .truth_quality import database_truth_quality
from .value_provenance import ValueProvenanceError
from .verification import ErrorPair, lead_bucket, summarize
from .weather_conditions import annotate_daily_conditions


def _descriptor(provider) -> dict[str, object]:
    return {
        "id": provider.id,
        "model_provider": provider.model_provider,
        "model_name": provider.model_name,
        "role": provider.role,
        "transport": provider.transport,
        **({"station_id": provider.station_id} if provider.station_id else {}),
    }


def _daily_payload(database: Database, *, days: int, timezone_name: str, location_id: str = "home") -> list[dict[str, object]]:
    rows = database.latest_forecast_rows(
        hours=min(360, days * 24),
        variables=("temperature_2m", "precipitation_1h"),
        location_id=location_id,
    )
    tz = ZoneInfo(timezone_name)
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        if row["statistic"] not in {"deterministic", "mean"}:
            continue
        local_date = parse_time(str(row["valid_time_utc"])).astimezone(tz).date().isoformat()
        key = (str(row["provider"]), local_date)
        item = grouped.setdefault(
            key,
            {
                "provider": row["provider"],
                "model_name": row["model_name"],
                "date": local_date,
                "temperature_min_c": None,
                "temperature_max_c": None,
                "precipitation_total_mm": 0.0,
                "init_time_utc": row["init_time_utc"],
                "init_time_quality": row["init_time_quality"],
                "retrieved_at_utc": row["retrieved_at_utc"],
            },
        )
        if row["variable"] == "temperature_2m":
            value = float(row["value"])
            mn = item["temperature_min_c"]
            mx = item["temperature_max_c"]
            item["temperature_min_c"] = value if mn is None else min(float(mn), value)
            item["temperature_max_c"] = value if mx is None else max(float(mx), value)
        elif row["variable"] == "precipitation_1h" and row["accumulation_window_minutes"] == 60:
            item["precipitation_total_mm"] = float(item["precipitation_total_mm"]) + float(row["value"])
    return sorted(grouped.values(), key=lambda x: (str(x["date"]), str(x["provider"])))


def _temperature_common_samples(rows: list[dict[str, object]]) -> list[SkillSample]:
    """Choose one defensible run per provider/lead bucket/valid time before comparison."""

    selected: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        bucket = lead_bucket(float(row["lead_hours"]))
        key = (str(row["provider"]), bucket, str(row["valid_time_utc"]))
        rank = (str(row.get("init_time_utc") or ""), str(row.get("retrieved_at_utc") or ""))
        current = selected.get(key)
        if current is None:
            selected[key] = row
            continue
        current_rank = (
            str(current.get("init_time_utc") or ""), str(current.get("retrieved_at_utc") or ""),
        )
        if rank > current_rank:
            selected[key] = row

    return [
        SkillSample(
            sample_id=str(row["valid_time_utc"]),
            provider=str(row["provider"]),
            model_version=str(row["model_version"]) if row.get("model_version") is not None else None,
            lead_hours=float(row["lead_hours"]),
            forecast=float(row["forecast_value"]),
            observed=float(row["observed_value"]),
            mode="station_run_skill",
            variable="temperature_2m",
            p10=float(row["p10"]) if row.get("p10") is not None else None,
            p90=float(row["p90"]) if row.get("p90") is not None else None,
        )
        for row in selected.values()
    ]


def _public_location_label(location_id: str, settings: Settings) -> str:
    if location_id == "home":
        return settings.home_label
    if location_id == BENCHMARK_LOCATION.id:
        return BENCHMARK_LOCATION.label
    return BENCHMARK_LOCATION.label


def _safety_reference(settings: Settings) -> tuple[float, float, dict[str, object]]:
    if settings.home_configured:
        return (
            float(settings.home_lat),
            float(settings.home_lon),
            {
                "id": "home",
                "label": settings.home_label,
                "context": "configured_private_home",
                "coordinates_exposed": False,
            },
        )
    if settings.runtime_mode == "public-only":
        return (
            BENCHMARK_LOCATION.lat,
            BENCHMARK_LOCATION.lon,
            {
                "id": BENCHMARK_LOCATION.id,
                "label": BENCHMARK_LOCATION.label,
                "station_id": CDC_STATION_ID,
                "context": "public_reference",
                "coordinates_exposed": False,
            },
        )
    raise HTTPException(status_code=503, detail="home location is not configured")


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = database or Database(settings.database_url)

    # Development/test mode may create the schema automatically. The reviewed
    # RPi5 public runtime sets DATABASE_INIT_MODE=require-existing so container
    # startup cannot implicitly create the production schema. The legacy 10416
    # location remains the existing current-reference identity; issue #155 does
    # not create the new benchmark row on application startup.
    if settings.database_init_mode == "auto":
        database.initialize()

    schema = database_schema_state(database)
    # Production require-existing startup must stay DB-read-only. Location
    # materialization belongs to explicit schema/init or ingest write paths.
    if settings.database_init_mode == "auto" and schema["state"] == "ready":
        database.ensure_location(
            location_id=BENCHMARK_LOCATION.id,
            label=BENCHMARK_LOCATION.label,
            lat=BENCHMARK_LOCATION.lat,
            lon=BENCHMARK_LOCATION.lon,
            elevation_m=BENCHMARK_LOCATION.elevation_m,
            timezone=BENCHMARK_LOCATION.timezone,
        )
        if settings.home_configured:
            database.ensure_home_location(
                label=settings.home_label,
                lat=settings.home_lat,
                lon=settings.home_lon,
                timezone=settings.home_timezone,
            )  # type: ignore[arg-type]

    app = FastAPI(
        title="rozkalns_weather",
        version="0.4.0",
        description="Private local weather comparison and WeatherNext 3 verification API",
    )
    app.state.settings = settings
    app.state.database = database
    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    def require_database_ready() -> None:
        if database_schema_state(database)["state"] != "ready":
            raise HTTPException(status_code=503, detail="database schema is not initialized")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return FileResponse(
            static_dir / "sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/health")
    def health() -> dict[str, object]:
        readiness = readiness_payload(settings, database)
        return {
            "status": "ok",
            "runtime_mode": settings.runtime_mode,
            "database": readiness["database"]["state"],  # type: ignore[index]
            "home_configured": settings.home_configured,
            "weathernext_required": False,
        }

    @app.get("/ready")
    def ready() -> JSONResponse:
        payload = readiness_payload(settings, database)
        return JSONResponse(payload, status_code=200 if payload["ready"] else 503)

    @app.get("/api/readiness")
    def api_readiness() -> JSONResponse:
        payload = readiness_payload(settings, database)
        return JSONResponse(payload, status_code=200 if payload["ready"] else 503)

    @app.get("/api/providers")
    def providers() -> dict[str, object]:
        return {"providers": [_descriptor(provider) for provider in PROVIDERS]}

    @app.get("/api/health/providers")
    def provider_health() -> dict[str, object]:
        schema_state = database_schema_state(database)
        stored = database.provider_statuses() if schema_state["state"] == "ready" else {}
        evidence = database.provider_freshness_evidence() if schema_state["state"] == "ready" else {}
        now = datetime.now(timezone.utc)
        provider_states = []
        for provider in PROVIDERS:
            saved = stored.get(provider.id, {})
            state = saved.get("state", "adapter_ready_not_ingested")
            if provider.id == "weathernext3" and provider.id not in stored:
                state = "not_ingested"
            if provider.id in PUBLIC_PROVIDER_HEALTH_POLICIES:
                health = classify_public_provider_health(provider.id, saved, evidence.get(provider.id), now=now)
                state = health["ingest_state"]
            else:
                health = {
                    "tracked": False,
                    "ingest_state": state,
                    "freshness_state": "not_tracked",
                    "failure_domain": "none",
                    "reason_code": "NOT_IN_PUBLIC_RECURRING_SCOPE",
                    "last_attempt_at_utc": saved.get("last_attempt_at_utc"),
                    "last_success_at_utc": saved.get("last_success_at_utc"),
                    "last_init_time_utc": saved.get("last_init_time_utc"),
                    "last_retrieved_at_utc": None,
                    "latest_valid_time_utc": None,
                    "last_observed_at_utc": None,
                    "attempt_age_hours": None,
                    "success_age_hours": None,
                    "source_age_hours": None,
                    "detail": saved.get("detail"),
                }
            provider_states.append({"id": provider.id, "model_name": provider.model_name, "state": state, **health})
        home_payload = {
            "id": "home",
            "label": settings.home_label,
            "configured": settings.home_configured,
            "coordinates_exposed": False,
            "timezone": settings.home_timezone,
        }
        return {
            "runtime_mode": settings.runtime_mode,
            "health_contract": "provider-freshness-v1",
            "home": home_payload,
            "location": home_payload,
            "verification_reference": {
                "id": BENCHMARK_LOCATION.id,
                "label": BENCHMARK_LOCATION.label,
                "station_id": CDC_STATION_ID,
                "coordinates_exposed": False,
            },
            "database": schema_state,
            "providers": provider_states,
        }

    @app.get("/api/current")
    def current() -> dict[str, object]:
        require_database_ready()
        observations = latest_current_observations(database, location_id=BENCHMARK_LOCATION.id)
        return {
            "location": {
                "id": BENCHMARK_LOCATION.id,
                "label": BENCHMARK_LOCATION.label,
                "station_id": CDC_STATION_ID,
                "coordinates_exposed": False,
            },
            "truth_source": f"DWD CDC {CDC_STATION_ID}",
            "observations": observations,
            "state": "observed" if observations else "not_observed_yet",
            "note": "Station truth is not presented as a measurement at the private home point.",
        }

    @app.get("/api/hourly")
    def hourly(
        hours: int = Query(48, ge=1, le=360),
        variable: str = Query("temperature_2m"),
        location_id: Literal["home", "station_05480"] = Query("home"),
    ) -> dict[str, object]:
        require_database_ready()
        return {
            "hours": hours,
            "variable": variable,
            "location": {"id": location_id, "label": _public_location_label(location_id, settings), "coordinates_exposed": False},
            "series": hourly_with_provenance(database, hours=hours, variable=variable, location_id=location_id),
        }

    @app.get("/api/daily")
    def daily(
        days: int = Query(10, ge=1, le=15),
        location_id: Literal["home", "station_05480"] = Query("home"),
    ) -> dict[str, object]:
        require_database_ready()
        return {
            "days": days,
            "timezone": settings.home_timezone,
            "location": {"id": location_id, "label": _public_location_label(location_id, settings), "coordinates_exposed": False},
            "days_by_provider": annotate_daily_conditions(
                database,
                _daily_payload(
                    database,
                    days=days,
                    timezone_name=settings.home_timezone,
                    location_id=location_id,
                ),
                days=days,
                timezone_name=settings.home_timezone,
                location_id=location_id,
            ),
        }

    @app.get("/api/corpus/stats")
    def corpus_stats() -> dict[str, object]:
        require_database_ready()
        return database.corpus_stats()

    @app.get("/api/corpus/integrity")
    def corpus_integrity() -> dict[str, object]:
        require_database_ready()
        return database.corpus_integrity()

    @app.get("/api/verification/truth-quality")
    def verification_truth_quality(days: int = Query(90, ge=1, le=3650)) -> dict[str, object]:
        require_database_ready()
        return database_truth_quality(
            database,
            days=days,
            location_id=BENCHMARK_LOCATION.id,
            station_id=CDC_STATION_ID,
        )

    @app.get("/api/verification/summary")
    def verification_summary(
        days: int = Query(90, ge=1, le=3650),
        compact: bool = Query(False),
    ) -> dict[str, object]:
        require_database_ready()
        rows = database.temperature_verification_pairs(days=days, location_id=BENCHMARK_LOCATION.id)
        common_sample_slices = common_sample_leaderboard(
            _temperature_common_samples(rows),
            include_bootstrap=not compact,
        )
        if compact:
            visible_fields = (
                "provider",
                "model_version",
                "lead_bucket",
                "n",
                "missingness",
                "sample_sufficiency_state",
                "mae",
                "rmse",
                "bias",
                "p10_p90_coverage",
                "coverage_n",
            )
            return {
                "window_days": days,
                "variable": "temperature_2m",
                "comparison_mode": "station_run_skill",
                "comparison_location": {"id": BENCHMARK_LOCATION.id, "station_id": CDC_STATION_ID},
                "common_sample_slices": [
                    {key: row.get(key) for key in visible_fields}
                    for row in common_sample_slices
                ],
            }
        truth_quality = database_truth_quality(
            database,
            days=days,
            location_id=BENCHMARK_LOCATION.id,
            station_id=CDC_STATION_ID,
        )
        by_provider = defaultdict(list)
        by_bucket = defaultdict(lambda: defaultdict(list))
        by_version = defaultdict(lambda: defaultdict(list))
        for row in rows:
            pair = ErrorPair(
                provider=str(row["provider"]),
                model_version=row.get("model_version"),
                lead_hours=float(row["lead_hours"]),
                forecast=float(row["forecast_value"]),
                observed=float(row["observed_value"]),
                p10=float(row["p10"]) if row.get("p10") is not None else None,
                p90=float(row["p90"]) if row.get("p90") is not None else None,
            )
            by_provider[pair.provider].append(pair)
            by_bucket[pair.provider][lead_bucket(pair.lead_hours)].append(pair)
            by_version[pair.provider][pair.model_version or "unknown"].append(pair)
        payload = {
            provider: {
                "descriptive_only": True,
                "overall": summarize(pairs),
                "by_lead_bucket": {bucket: summarize(items) for bucket, items in by_bucket[provider].items()},
                "by_model_version": {version: summarize(items) for version, items in by_version[provider].items()},
            }
            for provider, pairs in by_provider.items()
        }
        return {
            "window_days": days,
            "variable": "temperature_2m",
            "comparison_mode": "station_run_skill",
            "sample_sufficiency_contract": "common-sample-sufficiency-v1",
            "comparison_location": {"id": BENCHMARK_LOCATION.id, "station_id": CDC_STATION_ID},
            "matching_tolerance_minutes": 0,
            "verification_ready": truth_quality["verification_ready"],
            "truth_quality": truth_quality,
            "common_sample_slices": common_sample_slices,
            "providers": payload,
            "note": "Only common station valid-times inside one variable/lead bucket and one complete provider model-version cohort are eligible for model-comparison surfaces. Provider aggregates remain descriptive only. Metrics are not clean benchmark evidence unless verification_ready is true. Home forecasts are comparison-only until home observations exist.",
        }

    @app.get("/api/provenance/verification", response_model=None)
    def provenance_verification(
        provider: str = Query(..., min_length=1),
        valid_time_utc: str = Query(..., min_length=1),
        variable: str = Query("temperature_2m", min_length=1),
        statistic: str = Query("deterministic", min_length=1),
        metric_name: str = Query("absolute_error", min_length=1),
    ) -> dict[str, object] | JSONResponse:
        require_database_ready()
        try:
            return verification_value_trace(
                database,
                provider=provider,
                valid_time_utc=valid_time_utc,
                variable=variable,
                statistic=statistic,
                metric_name=metric_name,
            )
        except ValueProvenanceError as exc:
            status_code = 404 if exc.reason_code in {"FORECAST_VALUE_NOT_FOUND", "TRUTH_VALUE_NOT_FOUND"} else 422
            return JSONResponse(blocked_trace_response(exc), status_code=status_code)

    @app.get("/api/warnings")
    def warnings() -> dict[str, object]:
        lat, lon, reference = _safety_reference(settings)
        return {**fetch_dwd_alerts(lat=lat, lon=lon), "reference_location": reference}

    @app.get("/api/radar/map")
    def radar_map(
        layer: Literal["base", "boundaries", "radar"] = Query(...),
        at: str | None = Query(None),
    ) -> Response:
        lat, lon, _reference = _safety_reference(settings)
        if layer == "radar" and not at:
            raise HTTPException(status_code=422, detail="radar timestamp is required")
        try:
            payload = fetch_dwd_radar_map_png(lat=lat, lon=lon, layer=layer, at=at)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="DWD radar map unavailable") from exc
        max_age = 86_400 if layer in {"base", "boundaries"} else 300
        return Response(
            content=payload,
            media_type="image/png",
            headers={
                "Cache-Control": f"private, max-age={max_age}",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/radar")
    def radar() -> dict[str, object]:
        lat, lon, reference = _safety_reference(settings)
        return {
            **fetch_radar_point(lat=lat, lon=lon, center_location_id=str(reference["id"])),
            "reference_location": reference,
        }

    return app


app = create_app()
