from __future__ import annotations

from collections import defaultdict
from typing import Literal

from fastapi import HTTPException, Query
from fastapi.responses import JSONResponse

from .app_core import (
    _daily_payload,
    _public_location_label,
    _safety_reference,
    _temperature_common_samples,
    app as _core_app,
    create_app as _core_create_app,
)
from .config import Settings
from .db import Database
from .leaderboard import common_sample_leaderboard
from .locations import BENCHMARK_LOCATION
from .providers.dwd_cdc_observations import CDC_STATION_ID
from .provenance_api import hourly_with_provenance
from .query_bounds import (
    CONTRACT as QUERY_BOUNDS_CONTRACT,
    DEFAULT_PAGE_SIZE,
    MAX_DAILY_DAYS,
    MAX_HOURLY_HOURS,
    MAX_HOURLY_SOURCE_ROWS,
    MAX_VERIFICATION_DAYS,
    MAX_VERIFICATION_SAMPLES,
    QueryGuardError,
    blocked_query_response,
    bounded_integer,
    enforce_sample_count,
    ensure_response_size,
    paginate_rows,
    parse_selection,
    query_identity,
    snapshot_identity,
)
from .radar_warnings import fetch_dwd_alerts, fetch_radar_point
from .runtime import database_schema_state
from .semantics import PRECIP_EVENT_VERSION
from .truth_quality import database_truth_quality
from .verification import ErrorPair, ProbabilityPair, brier_score, lead_bucket, reliability_bins, summarize

_GUARDED_PATHS = {
    "/api/hourly",
    "/api/daily",
    "/api/verification/truth-quality",
    "/api/verification/summary",
    "/api/verification/precipitation",
    "/api/warnings",
    "/api/radar",
}


def _filter_rows(
    rows: list[dict[str, object]],
    *,
    providers: tuple[str, ...],
    model_versions: tuple[str, ...],
) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if (not providers or str(row.get("provider") or "") in providers)
        and (not model_versions or str(row.get("model_version") or "") in model_versions)
    ]


def _blocked(exc: QueryGuardError) -> JSONResponse:
    return JSONResponse(blocked_query_response(exc), status_code=exc.status_code)


def _bounded_complete_metadata(
    *,
    endpoint: str,
    query: dict[str, object],
    sample_count: int,
) -> dict[str, object]:
    return {
        "contract": QUERY_BOUNDS_CONTRACT,
        "query_identity_sha256": query_identity({"endpoint": endpoint, **query}),
        "sample_count": sample_count,
        "complete": True,
        "silent_truncation": False,
    }


def _install_query_guards(app):
    if getattr(app.state, "query_bounds_installed", False):
        return app
    app.state.query_bounds_installed = True
    settings: Settings = app.state.settings
    database: Database = app.state.database

    app.router.routes = [
        route for route in app.router.routes if getattr(route, "path", None) not in _GUARDED_PATHS
    ]

    def require_database_ready() -> None:
        if database_schema_state(database)["state"] != "ready":
            raise HTTPException(status_code=503, detail="database schema is not initialized")

    @app.get("/api/hourly", response_model=None)
    def hourly(
        hours: int = Query(48),
        variable: str = Query("temperature_2m"),
        location_id: Literal["home", "station_05480", "station_10416"] = Query("home"),
        providers: str | None = Query(None),
        model_versions: str | None = Query(None),
        page_size: int | None = Query(None),
        cursor: str | None = Query(None),
    ) -> dict[str, object] | JSONResponse:
        require_database_ready()
        try:
            bounded_integer("hours", hours, minimum=1, maximum=MAX_HOURLY_HOURS)
            provider_selection = parse_selection(providers, kind="provider")
            model_selection = parse_selection(model_versions, kind="model")
            rows = hourly_with_provenance(
                database,
                hours=hours,
                variable=variable,
                location_id=location_id,
            )
            rows = _filter_rows(rows, providers=provider_selection, model_versions=model_selection)
            enforce_sample_count(
                len(rows),
                maximum=MAX_HOURLY_SOURCE_ROWS,
                reason_code="HOURLY_SOURCE_ROWS_TOO_LARGE",
            )
            effective_page_size = page_size
            if cursor is not None and effective_page_size is None:
                effective_page_size = DEFAULT_PAGE_SIZE
            query_core = {
                "hours": hours,
                "variable": variable,
                "location_id": location_id,
                "providers": list(provider_selection),
                "model_versions": list(model_selection),
                "page_size": effective_page_size,
            }
            query_sha = query_identity({"endpoint": "/api/hourly", **query_core})
            snapshot_sha = snapshot_identity(rows)
            if effective_page_size is None:
                series = rows
                query_meta: dict[str, object] = {
                    "contract": QUERY_BOUNDS_CONTRACT,
                    "query_identity_sha256": query_sha,
                    "snapshot_identity_sha256": snapshot_sha,
                    "total_rows": len(rows),
                    "offset": 0,
                    "page_size": None,
                    "returned_rows": len(rows),
                    "complete": True,
                    "next_cursor": None,
                    "silent_truncation": False,
                }
            else:
                series, query_meta = paginate_rows(
                    rows,
                    page_size=effective_page_size,
                    query_identity_sha256=query_sha,
                    snapshot_identity_sha256=snapshot_sha,
                    cursor=cursor,
                )
                query_meta["silent_truncation"] = False
            payload = {
                "hours": hours,
                "variable": variable,
                "location": {
                    "id": location_id,
                    "label": _public_location_label(location_id, settings),
                    "coordinates_exposed": False,
                },
                "series": series,
                "query": query_meta,
            }
            ensure_response_size(payload)
            return payload
        except QueryGuardError as exc:
            return _blocked(exc)

    @app.get("/api/daily", response_model=None)
    def daily(
        days: int = Query(10),
        location_id: Literal["home", "station_05480", "station_10416"] = Query("home"),
    ) -> dict[str, object] | JSONResponse:
        require_database_ready()
        try:
            bounded_integer("days", days, minimum=1, maximum=MAX_DAILY_DAYS)
            payload = {
                "days": days,
                "timezone": settings.home_timezone,
                "location": {
                    "id": location_id,
                    "label": _public_location_label(location_id, settings),
                    "coordinates_exposed": False,
                },
                "days_by_provider": _daily_payload(
                    database,
                    days=days,
                    timezone_name=settings.home_timezone,
                    location_id=location_id,
                ),
            }
            payload["query"] = _bounded_complete_metadata(
                endpoint="/api/daily",
                query={"days": days, "location_id": location_id},
                sample_count=len(payload["days_by_provider"]),
            )
            ensure_response_size(payload)
            return payload
        except QueryGuardError as exc:
            return _blocked(exc)

    @app.get("/api/verification/truth-quality", response_model=None)
    def verification_truth_quality(days: int = Query(90)) -> dict[str, object] | JSONResponse:
        require_database_ready()
        try:
            bounded_integer("days", days, minimum=1, maximum=MAX_VERIFICATION_DAYS)
            payload = database_truth_quality(
                database,
                days=days,
                location_id=BENCHMARK_LOCATION.id,
                station_id=CDC_STATION_ID,
            )
            ensure_response_size(payload)
            return payload
        except QueryGuardError as exc:
            return _blocked(exc)

    @app.get("/api/verification/summary", response_model=None)
    def verification_summary(
        days: int = Query(90),
        providers: str | None = Query(None),
        model_versions: str | None = Query(None),
    ) -> dict[str, object] | JSONResponse:
        require_database_ready()
        try:
            bounded_integer("days", days, minimum=1, maximum=MAX_VERIFICATION_DAYS)
            provider_selection = parse_selection(providers, kind="provider")
            model_selection = parse_selection(model_versions, kind="model")
            truth_quality = database_truth_quality(
                database,
                days=days,
                location_id=BENCHMARK_LOCATION.id,
                station_id=CDC_STATION_ID,
            )
            rows = database.temperature_verification_pairs(days=days, location_id=BENCHMARK_LOCATION.id)
            rows = _filter_rows(rows, providers=provider_selection, model_versions=model_selection)
            enforce_sample_count(len(rows), maximum=MAX_VERIFICATION_SAMPLES)
            common_sample_slices = common_sample_leaderboard(_temperature_common_samples(rows))
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
            provider_payload = {
                provider: {
                    "descriptive_only": True,
                    "overall": summarize(pairs),
                    "by_lead_bucket": {
                        bucket: summarize(items) for bucket, items in by_bucket[provider].items()
                    },
                    "by_model_version": {
                        version: summarize(items) for version, items in by_version[provider].items()
                    },
                }
                for provider, pairs in by_provider.items()
            }
            payload = {
                "window_days": days,
                "variable": "temperature_2m",
                "comparison_mode": "station_run_skill",
                "sample_sufficiency_contract": "common-sample-sufficiency-v1",
                "comparison_location": {"id": BENCHMARK_LOCATION.id, "station_id": CDC_STATION_ID},
                "matching_tolerance_minutes": 0,
                "verification_ready": truth_quality["verification_ready"],
                "truth_quality": truth_quality,
                "common_sample_slices": common_sample_slices,
                "providers": provider_payload,
                "query": _bounded_complete_metadata(
                    endpoint="/api/verification/summary",
                    query={
                        "days": days,
                        "providers": list(provider_selection),
                        "model_versions": list(model_selection),
                        "variable": "temperature_2m",
                    },
                    sample_count=len(rows),
                ),
                "note": "Only common station valid-times inside one variable/lead bucket and one complete provider model-version cohort are eligible for model-comparison surfaces. Provider aggregates remain descriptive only. Metrics are not clean benchmark evidence unless verification_ready is true. Home forecasts are comparison-only until home observations exist.",
            }
            ensure_response_size(payload)
            return payload
        except QueryGuardError as exc:
            return _blocked(exc)

    @app.get("/api/verification/precipitation", response_model=None)
    def precipitation_verification(
        days: int = Query(90),
        providers: str | None = Query(None),
        model_versions: str | None = Query(None),
    ) -> dict[str, object] | JSONResponse:
        require_database_ready()
        try:
            bounded_integer("days", days, minimum=1, maximum=MAX_VERIFICATION_DAYS)
            provider_selection = parse_selection(providers, kind="provider")
            model_selection = parse_selection(model_versions, kind="model")
            truth_quality = database_truth_quality(
                database,
                days=days,
                location_id=BENCHMARK_LOCATION.id,
                station_id=CDC_STATION_ID,
            )
            threshold = settings.precipitation_event_threshold_mm
            rows = database.precipitation_verification_pairs(
                days=days,
                threshold_mm=threshold,
                location_id=BENCHMARK_LOCATION.id,
            )
            probability_rows = _filter_rows(
                rows["probability"],
                providers=provider_selection,
                model_versions=model_selection,
            )
            amount_rows = _filter_rows(
                rows["amount"],
                providers=provider_selection,
                model_versions=model_selection,
            )
            enforce_sample_count(
                len(probability_rows) + len(amount_rows),
                maximum=MAX_VERIFICATION_SAMPLES,
            )
            prob = defaultdict(list)
            amount = defaultdict(list)
            for row in probability_rows:
                prob[str(row["provider"])].append(
                    ProbabilityPair(
                        provider=str(row["provider"]),
                        model_version=row.get("model_version"),
                        lead_hours=float(row["lead_hours"]),
                        probability=float(row["probability"]),
                        observed_event=float(row["observed_event"]),
                    )
                )
            for row in amount_rows:
                amount[str(row["provider"])].append(
                    ErrorPair(
                        provider=str(row["provider"]),
                        model_version=row.get("model_version"),
                        lead_hours=float(row["lead_hours"]),
                        forecast=float(row["forecast_value"]),
                        observed=float(row["observed_value"]),
                    )
                )
            payload = {
                "window_days": days,
                "comparison_location": {"id": BENCHMARK_LOCATION.id, "station_id": CDC_STATION_ID},
                "event_version": PRECIP_EVENT_VERSION,
                "occurrence_threshold_mm_per_hour": threshold,
                "sample_sufficiency_contract": "common-sample-sufficiency-v1",
                "verification_ready": truth_quality["verification_ready"],
                "truth_quality": truth_quality,
                "probability": {
                    provider: {**brier_score(items), "reliability_bins": reliability_bins(items)}
                    for provider, items in prob.items()
                },
                "amount": {provider: summarize(items) for provider, items in amount.items()},
                "query": {
                    **_bounded_complete_metadata(
                        endpoint="/api/verification/precipitation",
                        query={
                            "days": days,
                            "providers": list(provider_selection),
                            "model_versions": list(model_selection),
                        },
                        sample_count=len(probability_rows) + len(amount_rows),
                    ),
                    "probability_sample_count": len(probability_rows),
                    "amount_sample_count": len(amount_rows),
                },
                "note": "Probability and precipitation amount are verified separately; each metric exposes n and sample sufficiency. Missingness remains not_assessed unless a strict common-sample denominator is available. Metrics are not clean benchmark evidence unless verification_ready is true, and deterministic model transport never fabricates a probability.",
            }
            ensure_response_size(payload)
            return payload
        except QueryGuardError as exc:
            return _blocked(exc)

    @app.get("/api/warnings")
    def warnings() -> dict[str, object]:
        lat, lon, reference = _safety_reference(settings)
        return {**fetch_dwd_alerts(lat=lat, lon=lon), "reference_location": reference}

    @app.get("/api/radar")
    def radar() -> dict[str, object]:
        lat, lon, reference = _safety_reference(settings)
        return {
            **fetch_radar_point(lat=lat, lon=lon, center_location_id=str(reference["id"])),
            "reference_location": reference,
        }

    return app


def create_app(settings: Settings | None = None, database: Database | None = None):
    return _install_query_guards(_core_create_app(settings=settings, database=database))


app = _install_query_guards(_core_app)
