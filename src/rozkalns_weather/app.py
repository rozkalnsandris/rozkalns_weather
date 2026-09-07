from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .benchmark import common_sample_leaderboard, event_summary
from .config import Settings
from .db import Database
from .locations import DWD_10416
from .models import parse_time
from .probabilistic import crps_ensemble, event_probability, wis_from_members
from .providers import PROVIDERS
from .providers.weathernext import access_state
from .radar_warnings import fetch_dwd_alerts, fetch_radar_point
from .semantics import PRECIP_EVENT_VERSION
from .verification import ErrorPair, ProbabilityPair, brier_score, lead_bucket, reliability_bins, summarize


def _descriptor(provider) -> dict[str, object]:
    return {"id": provider.id, "model_provider": provider.model_provider, "model_name": provider.model_name, "role": provider.role, "transport": provider.transport, **({"station_id": provider.station_id} if provider.station_id else {})}


def _daily_payload(database: Database, *, days: int, timezone_name: str) -> list[dict[str, object]]:
    rows = database.latest_forecast_rows(hours=min(360, days * 24), variables=("temperature_2m", "precipitation_1h"), location_id="home")
    tz = ZoneInfo(timezone_name)
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        if row["statistic"] not in {"deterministic", "mean", "p50"}:
            continue
        local_date = parse_time(str(row["valid_time_utc"])).astimezone(tz).date().isoformat()
        key = (str(row["provider"]), local_date)
        item = grouped.setdefault(key, {"provider": row["provider"], "model_name": row["model_name"], "date": local_date, "temperature_min_c": None, "temperature_max_c": None, "precipitation_total_mm": 0.0, "init_time_utc": row["init_time_utc"], "init_time_quality": row["init_time_quality"], "retrieved_at_utc": row["retrieved_at_utc"]})
        if row["variable"] == "temperature_2m":
            value = float(row["value"])
            mn = item["temperature_min_c"]
            mx = item["temperature_max_c"]
            item["temperature_min_c"] = value if mn is None else min(float(mn), value)
            item["temperature_max_c"] = value if mx is None else max(float(mx), value)
        elif row["variable"] == "precipitation_1h" and row["accumulation_window_minutes"] == 60:
            item["precipitation_total_mm"] = float(item["precipitation_total_mm"]) + float(row["value"])
    return sorted(grouped.values(), key=lambda x: (str(x["date"]), str(x["provider"])))


def _ensemble_verification_payload(database: Database, *, days: int, precipitation_threshold_mm: float) -> dict[str, object]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    with database.connect() as connection:
        rows = [dict(row) for row in connection.execute(
            """SELECT r.id AS run_id,r.provider,r.model_version,r.init_time_quality,
                      v.valid_time_utc,v.lead_hours,v.variable,v.statistic,v.value,
                      o.value AS observed_value
               FROM forecast_runs r
               JOIN forecast_values v ON v.run_id=r.id
               JOIN observations o ON o.location_id=r.location_id
                 AND o.observed_at_utc=v.valid_time_utc
                 AND o.variable=v.variable
                 AND o.source_provider='DWD'
               WHERE r.location_id=? AND v.statistic LIKE 'member_%'
                 AND v.variable IN ('temperature_2m','precipitation_1h','wind_gust_10m')
                 AND v.valid_time_utc>=?
               ORDER BY r.provider,r.id,v.valid_time_utc,v.variable,v.statistic""",
            (DWD_10416.id, cutoff),
        ).fetchall()]
    grouped: dict[tuple[str, int, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["provider"]), int(row["run_id"]), str(row["valid_time_utc"]), str(row["variable"]))].append(row)
    scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    precipitation_pairs: dict[str, list[ProbabilityPair]] = defaultdict(list)
    samples: dict[str, int] = defaultdict(int)
    for (provider, _run_id, _valid, variable), members_rows in grouped.items():
        members = [float(row["value"]) for row in members_rows]
        observed = float(members_rows[0]["observed_value"])
        samples[provider] += 1
        scores[provider][f"crps_{variable}"].append(crps_ensemble(members, observed))
        if variable == "temperature_2m":
            wis = wis_from_members(members, observed)
            scores[provider]["wis_temperature_2m"].append(float(wis["wis"]))
            scores[provider]["coverage80_temperature_2m"].append(float(wis["coverage_80"]))
            scores[provider]["width80_temperature_2m"].append(float(wis["width_80"]))
        elif variable == "precipitation_1h":
            probability = event_probability(members, threshold=precipitation_threshold_mm)
            precipitation_pairs[provider].append(ProbabilityPair(provider=provider, lead_hours=float(members_rows[0]["lead_hours"]), probability=probability, observed_event=1.0 if observed >= precipitation_threshold_mm else 0.0, model_version=members_rows[0].get("model_version")))
    providers: dict[str, object] = {}
    for provider in sorted(set(scores) | set(precipitation_pairs)):
        metric_values = {name: (sum(values) / len(values) if values else None) for name, values in scores[provider].items()}
        probability = precipitation_pairs.get(provider, [])
        providers[provider] = {"n_grouped_samples": samples[provider], "metrics": metric_values, "precipitation_probability": {**brier_score(probability), "reliability_bins": reliability_bins(probability)} if probability else {"n": 0, "brier_score": None, "reliability_bins": []}}
    return {"window_days": days, "comparison_location": {"id": DWD_10416.id, "station_id": "10416"}, "member_input_only": True, "precipitation_threshold_mm_per_hour": precipitation_threshold_mm, "providers": providers, "note": "CRPS/WIS/Brier use stored ensemble member values only. Deterministic amounts and WeatherNext summary quantiles are never converted into event probabilities."}


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = database or Database(settings.database_url)
    database.initialize()
    database.ensure_location(location_id=DWD_10416.id, label=DWD_10416.label, lat=DWD_10416.lat, lon=DWD_10416.lon, elevation_m=DWD_10416.elevation_m, timezone=DWD_10416.timezone)
    if settings.home_configured:
        database.ensure_home_location(label=settings.home_label, lat=settings.home_lat, lon=settings.home_lon, timezone=settings.home_timezone)  # type: ignore[arg-type]
    app = FastAPI(title="rozkalns_weather", version="0.4.0", description="Private local weather comparison and WeatherNext 3 verification API")
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
            saved = stored.get(provider.id, {})
            state = saved.get("state", "adapter_ready_not_ingested")
            if provider.id == "weathernext3" and provider.id not in stored:
                state = access_state(configured=settings.weathernext_cloud_configured, now=now)
            provider_states.append({"id": provider.id, "model_name": provider.model_name, "role": provider.role, "state": state, "last_success_at_utc": saved.get("last_success_at_utc"), "last_attempt_at_utc": saved.get("last_attempt_at_utc"), "last_init_time_utc": saved.get("last_init_time_utc"), "detail": saved.get("detail")})
        home_payload = {"id": "home", "label": settings.home_label, "configured": settings.home_configured, "coordinates_exposed": False, "timezone": settings.home_timezone}
        return {"home": home_payload, "location": home_payload, "verification_reference": {"id": DWD_10416.id, "label": DWD_10416.label, "station_id": "10416", "coordinates_exposed": False}, "database": {"state": "ready", "tables": sorted(database.table_names())}, "providers": provider_states}

    @app.get("/api/current")
    def current() -> dict[str, object]:
        observations = database.latest_observations(location_id=DWD_10416.id)
        return {"location": {"id": DWD_10416.id, "label": DWD_10416.label, "station_id": "10416", "coordinates_exposed": False}, "truth_source": "DWD WMO 10416", "observations": observations, "state": "observed" if observations else "not_observed_yet", "note": "Station truth is not presented as a measurement at the private home point."}

    @app.get("/api/hourly")
    def hourly(hours: int = Query(48, ge=1, le=360), variable: str = Query("temperature_2m")) -> dict[str, object]:
        return {"hours": hours, "variable": variable, "location": {"id": "home", "label": settings.home_label, "coordinates_exposed": False}, "series": database.latest_hourly(hours=hours, variable=variable, location_id="home")}

    @app.get("/api/daily")
    def daily(days: int = Query(10, ge=1, le=15)) -> dict[str, object]:
        return {"days": days, "timezone": settings.home_timezone, "location": {"id": "home", "label": settings.home_label, "coordinates_exposed": False}, "days_by_provider": _daily_payload(database, days=days, timezone_name=settings.home_timezone)}

    @app.get("/api/corpus/stats")
    def corpus_stats() -> dict[str, object]:
        return database.corpus_stats()

    @app.get("/api/corpus/integrity")
    def corpus_integrity() -> dict[str, object]:
        return database.corpus_integrity()

    @app.get("/api/verification/summary")
    def verification_summary(days: int = Query(90, ge=1, le=3650)) -> dict[str, object]:
        rows = database.temperature_verification_pairs(days=days, location_id=DWD_10416.id)
        by_provider = defaultdict(list)
        by_bucket = defaultdict(lambda: defaultdict(list))
        by_version = defaultdict(lambda: defaultdict(list))
        for row in rows:
            pair = ErrorPair(provider=str(row["provider"]), model_version=row.get("model_version"), lead_hours=float(row["lead_hours"]), forecast=float(row["forecast_value"]), observed=float(row["observed_value"]), p10=float(row["p10"]) if row.get("p10") is not None else None, p90=float(row["p90"]) if row.get("p90") is not None else None)
            by_provider[pair.provider].append(pair)
            by_bucket[pair.provider][lead_bucket(pair.lead_hours)].append(pair)
            by_version[pair.provider][pair.model_version or "unknown"].append(pair)
        payload = {provider: {"overall": summarize(pairs), "by_lead_bucket": {bucket: summarize(items) for bucket, items in by_bucket[provider].items()}, "by_model_version": {version: summarize(items) for version, items in by_version[provider].items()}} for provider, pairs in by_provider.items()}
        return {"window_days": days, "variable": "temperature_2m", "comparison_mode": "station_run_skill", "comparison_location": {"id": DWD_10416.id, "station_id": "10416"}, "matching_tolerance_minutes": 0, "providers": payload, "note": "Only forecasts stored for the DWD 10416 reference location are verified against DWD 10416 observations. Home forecasts are comparison-only until home observations exist."}

    @app.get("/api/verification/leaderboard")
    def leaderboard(days: int = Query(90, ge=1, le=3650), mode: str = Query("run_to_run", pattern="^(run_to_run|user_available)$")) -> dict[str, object]:
        rows = database.temperature_verification_pairs(days=days, location_id=DWD_10416.id)
        result = common_sample_leaderboard(rows, mode=mode)
        return {"window_days": days, "comparison_location": {"id": DWD_10416.id, "station_id": "10416"}, **result, "legacy_ai_excluded_from_strict_leaderboard": ["weathernext2"]}

    @app.get("/api/verification/probabilistic")
    def probabilistic(days: int = Query(30, ge=1, le=3650)) -> dict[str, object]:
        return _ensemble_verification_payload(database, days=days, precipitation_threshold_mm=settings.precipitation_event_threshold_mm)

    @app.get("/api/verification/events")
    def events(days: int = Query(90, ge=1, le=3650)) -> dict[str, object]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
        with database.connect() as connection:
            rows = [dict(row) for row in connection.execute("""SELECT r.provider,v.variable,v.value AS forecast_value,o.value AS observed_value FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id JOIN observations o ON o.location_id=r.location_id AND o.observed_at_utc=v.valid_time_utc AND o.variable=v.variable AND o.source_provider='DWD' WHERE r.location_id=? AND v.statistic IN ('deterministic','mean') AND v.valid_time_utc>=? AND v.variable IN ('temperature_2m','precipitation_1h','wind_gust_10m')""", (DWD_10416.id, cutoff)).fetchall()]
        return {"window_days": days, "comparison_location": {"id": DWD_10416.id, "station_id": "10416"}, **event_summary(rows)}

    @app.get("/api/verification/precipitation")
    def precipitation_verification(days: int = Query(90, ge=1, le=3650)) -> dict[str, object]:
        threshold = settings.precipitation_event_threshold_mm
        rows = database.precipitation_verification_pairs(days=days, threshold_mm=threshold, location_id=DWD_10416.id)
        prob = defaultdict(list)
        amount = defaultdict(list)
        for row in rows["probability"]:
            prob[str(row["provider"])].append(ProbabilityPair(provider=str(row["provider"]), model_version=row.get("model_version"), lead_hours=float(row["lead_hours"]), probability=float(row["probability"]), observed_event=float(row["observed_event"])))
        for row in rows["amount"]:
            amount[str(row["provider"])].append(ErrorPair(provider=str(row["provider"]), model_version=row.get("model_version"), lead_hours=float(row["lead_hours"]), forecast=float(row["forecast_value"]), observed=float(row["observed_value"])))
        return {"window_days": days, "comparison_location": {"id": DWD_10416.id, "station_id": "10416"}, "event_version": PRECIP_EVENT_VERSION, "occurrence_threshold_mm_per_hour": threshold, "probability": {provider: {**brier_score(items), "reliability_bins": reliability_bins(items)} for provider, items in prob.items()}, "amount": {provider: summarize(items) for provider, items in amount.items()}, "note": "Probability and precipitation amount are verified separately; deterministic model transport never fabricates a probability."}

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
