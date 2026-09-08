from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from ..models import ForecastRun, ForecastValue, parse_time

STATS = ("mean", "p10", "p25", "p50", "p75", "p90")
SURFACE_FIELDS = {
    "temperature_2m": ("temperature_2m", "K", "degC", None),
    "dewpoint_temperature_2m": ("dew_point_2m", "K", "degC", None),
    "wind_speed_10m": ("wind_speed_10m", "m/s", "m/s", None),
    "mean_sea_level_pressure": ("pressure_msl", "Pa", "hPa", None),
    "total_cloud_cover": ("cloud_cover", "fraction", "%", None),
    "total_precipitation_1hr": ("precipitation_1h", "m", "mm", 60),
}
STATION_FIELDS = {
    "station_head_temperature_2m": ("temperature_2m", "K", "degC", None),
    "station_head_dewpoint_temperature_2m": ("dew_point_2m", "K", "degC", None),
}
TABLE_005 = "weathernext_3_0_0_0p05deg"
TABLE_01 = "weathernext_3_0_0_0p1deg"
EXPECTED_SCHEMA = {
    TABLE_005: {
        "init_time",
        "geography_polygon",
        "forecast.time",
        "forecast.hours",
        *{f"forecast.{field}_{stat}" for field in STATION_FIELDS for stat in STATS},
    },
    TABLE_01: {
        "init_time",
        "geography_polygon",
        "forecast.time",
        "forecast.hours",
        *{f"forecast.{field}_{stat}" for field in SURFACE_FIELDS for stat in STATS},
    },
}


@dataclass(frozen=True, slots=True)
class WeatherNextQuery:
    table: str
    sql: str
    resolution: str


@dataclass(frozen=True, slots=True)
class WeatherNextDiagnostic:
    state: str
    schema_errors: tuple[str, ...] = ()
    checked_init_time_utc: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "schema_errors": list(self.schema_errors),
            "checked_init_time_utc": self.checked_init_time_utc,
            "coordinates_exposed": False,
            "credentials_exposed": False,
        }


class WeatherNextDataLatency(RuntimeError):
    """Expected run is not visible yet; older disseminated runs may be tried."""


def run_class(init_time: datetime) -> str:
    return "synoptic_360h" if init_time.astimezone(timezone.utc).hour in {0, 6, 12, 18} else "interim_48h"


def forecast_horizon_hours(init_time: datetime) -> int:
    return 360 if run_class(init_time) == "synoptic_360h" else 48


def _table(project: str, dataset: str, suffix: str) -> str:
    for token in (project, dataset):
        if not token.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid BigQuery project/dataset identifier")
    return f"`{project}.{dataset}.{suffix}`"


def build_point_query(
    *, project: str, dataset: str, lat: float, lon: float, init_time: datetime,
    resolution: str, hours_limit: int | None = None,
) -> WeatherNextQuery:
    if resolution not in {"0p05", "0p1"}:
        raise ValueError("resolution must be 0p05 or 0p1")
    if hours_limit is not None and not 1 <= hours_limit <= 360:
        raise ValueError("hours_limit must be between 1 and 360")
    suffix = TABLE_005 if resolution == "0p05" else TABLE_01
    table = _table(project, dataset, suffix)
    fields = STATION_FIELDS if resolution == "0p05" else SURFACE_FIELDS
    selected = ["f.time AS forecast_time", "f.hours AS forecast_hour"]
    for field in fields:
        selected.extend(f"f.{field}_{stat} AS {field}_{stat}" for stat in STATS)
    init_literal = init_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")
    hours_clause = f"\n  AND f.hours <= {hours_limit}" if hours_limit is not None else ""
    sql = (
        f"SELECT\n  {', '.join(selected)}\n"
        f"FROM {table} AS t, t.forecast AS f\n"
        f"WHERE t.init_time = TIMESTAMP('{init_literal}')\n"
        f"  AND ST_COVERS(t.geography_polygon, ST_GEOGPOINT({lon:.8f}, {lat:.8f}))"
        f"{hours_clause}\nORDER BY f.time ASC"
    )
    return WeatherNextQuery(table=table, sql=sql, resolution=resolution)


def validate_query_contract(query: WeatherNextQuery) -> tuple[str, ...]:
    errors: list[str] = []
    normalized = query.sql.lower()
    if "t.init_time = timestamp(" not in normalized:
        errors.append("missing_init_time_partition_filter")
    if "select *" in normalized:
        errors.append("select_star_forbidden")
    if "st_covers" not in normalized and "st_intersects" not in normalized:
        errors.append("missing_spatial_predicate")
    if query.resolution == "0p05" and "station_head_temperature_2m_mean" not in query.sql:
        errors.append("station_head_fields_missing")
    if query.resolution == "0p1" and "total_precipitation_1hr_mean" not in query.sql:
        errors.append("surface_fields_missing")
    return tuple(errors)


def build_schema_probe_query(*, project: str, dataset: str) -> str:
    for token in (project, dataset):
        if not token.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid BigQuery project/dataset identifier")
    return (
        "SELECT table_name, column_name, field_path, data_type\n"
        f"FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`\n"
        f"WHERE table_name IN ('{TABLE_005}', '{TABLE_01}')\n"
        "ORDER BY table_name, field_path"
    )


def validate_schema_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    seen = {TABLE_005: set(), TABLE_01: set()}
    for row in rows:
        table = str(row.get("table_name") or "")
        path = str(row.get("field_path") or row.get("column_name") or "")
        if table in seen and path:
            seen[table].add(path)
    errors: list[str] = []
    for table, required in EXPECTED_SCHEMA.items():
        if not seen[table]:
            errors.append(f"missing_table:{table}")
            continue
        errors.extend(f"missing_field:{table}:{field}" for field in sorted(required - seen[table]))
    return tuple(errors)


def _convert(value: float, native_unit: str, unit: str) -> float:
    if native_unit == "K" and unit == "degC":
        return value - 273.15
    if native_unit == "Pa" and unit == "hPa":
        return value / 100.0
    if native_unit == "m" and unit == "mm":
        return value * 1000.0
    if native_unit == "fraction" and unit == "%":
        return value * 100.0
    return value


def expected_available_at(init_time: datetime, *, platform: str = "bigquery") -> datetime:
    init_time = init_time.astimezone(timezone.utc)
    if platform.lower() not in {"bigquery", "earth_engine"}:
        raise ValueError("only BigQuery/Earth Engine latency is modeled here")
    return init_time + (timedelta(hours=8, minutes=10) if init_time.hour in {0, 6, 12, 18} else timedelta(hours=7, minutes=25))


def available_init_candidates(
    now: datetime, *, limit: int = 4, synoptic_only: bool = False,
) -> tuple[datetime, ...]:
    if not 1 <= limit <= 24:
        raise ValueError("limit must be between 1 and 24")
    now = now.astimezone(timezone.utc)
    cursor = now.replace(minute=0, second=0, microsecond=0)
    candidates: list[datetime] = []
    for offset in range(72):
        candidate = cursor - timedelta(hours=offset)
        if synoptic_only and candidate.hour not in {0, 6, 12, 18}:
            continue
        if expected_available_at(candidate) <= now:
            candidates.append(candidate)
            if len(candidates) >= limit:
                return tuple(candidates)
    return tuple(candidates)


def latest_available_init(now: datetime, *, synoptic_only: bool = False) -> datetime:
    candidates = available_init_candidates(now, limit=1, synoptic_only=synoptic_only)
    if not candidates:
        raise RuntimeError("no WeatherNext init fits the expected dissemination window")
    return candidates[0]


def rows_to_run(
    rows: Iterable[Mapping[str, Any]], *, resolution: str,
    init_time: datetime, retrieved_at: datetime,
) -> ForecastRun:
    fields = STATION_FIELDS if resolution == "0p05" else SURFACE_FIELDS
    values: list[ForecastValue] = []
    for row in rows:
        valid_time = row.get("forecast_time")
        if isinstance(valid_time, str):
            valid = parse_time(valid_time)
        elif isinstance(valid_time, datetime):
            valid = valid_time.astimezone(timezone.utc)
        else:
            continue
        lead = float(row.get("forecast_hour") or (valid - init_time).total_seconds() / 3600.0)
        for field, (variable, native_unit, unit, accumulation) in fields.items():
            for stat in STATS:
                raw = row.get(f"{field}_{stat}")
                if raw is None:
                    continue
                native_value = float(raw)
                values.append(ForecastValue(
                    valid_time_utc=valid, lead_hours=lead, variable=variable,
                    statistic=stat, value=_convert(native_value, native_unit, unit),
                    unit=unit, native_value=native_value, native_unit=native_unit,
                    accumulation_window_minutes=accumulation,
                ))
    expected = expected_available_at(init_time)
    return ForecastRun(
        provider="weathernext3", model_provider="Google DeepMind", model_name="WeatherNext 3",
        model_version="3.0.0", init_time_utc=init_time, retrieved_at_utc=retrieved_at,
        source_surface=f"BigQuery WeatherNext 3 {resolution}", transport_provider="Google BigQuery",
        values=tuple(values),
        source_metadata={
            "resolution": resolution,
            "statistics": list(STATS),
            "run_class": run_class(init_time),
            "forecast_horizon_hours": forecast_horizon_hours(init_time),
            "expected_available_at_utc": expected.isoformat().replace("+00:00", "Z"),
            "upstream_available_at_observed": False,
        },
        init_time_quality="provider_native",
        upstream_available_at_utc=None,
    )


def access_state(*, configured: bool, now: datetime, init_time: datetime | None = None) -> str:
    if not configured:
        return "access_pending"
    if init_time is not None and now.astimezone(timezone.utc) < expected_available_at(init_time):
        return "data_latency"
    return "ready_for_query"


def classify_bigquery_error(exc: Exception) -> str:
    text = f"{type(exc).__name__} {exc}".lower()
    if any(token in text for token in ("forbidden", "permission", "access denied", "403")):
        return "permission_denied"
    if any(token in text for token in ("not found", "404", "no such field", "unrecognized name")):
        return "schema_changed"
    return "access_pending"


class WeatherNextBigQueryAdapter:
    provider_id = "weathernext3"

    def __init__(self, *, project: str, dataset: str, client: Any | None = None) -> None:
        self.project = project
        self.dataset = dataset
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import bigquery  # type: ignore
        except ImportError as exc:
            raise RuntimeError("WeatherNext live ingest requires the optional 'weathernext' dependency") from exc
        self._client = bigquery.Client(project=self.project)
        return self._client

    def schema_probe(self) -> list[dict[str, Any]]:
        client = self._client_or_create()
        return [dict(row) for row in client.query(build_schema_probe_query(project=self.project, dataset=self.dataset)).result()]

    def diagnose(self, *, lat: float, lon: float, now: datetime | None = None) -> WeatherNextDiagnostic:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        try:
            schema_rows = self.schema_probe()
        except Exception as exc:
            return WeatherNextDiagnostic(classify_bigquery_error(exc))
        schema_errors = validate_schema_rows(schema_rows)
        if schema_errors:
            return WeatherNextDiagnostic("schema_changed", schema_errors)
        init_time = latest_available_init(now)
        q05 = build_point_query(project=self.project, dataset=self.dataset, lat=lat, lon=lon, init_time=init_time, resolution="0p05", hours_limit=1)
        q01 = build_point_query(project=self.project, dataset=self.dataset, lat=lat, lon=lon, init_time=init_time, resolution="0p1", hours_limit=1)
        if validate_query_contract(q05) or validate_query_contract(q01):
            return WeatherNextDiagnostic("schema_changed", ("local_query_contract_invalid",))
        try:
            client = self._client_or_create()
            rows05 = list(client.query(q05.sql).result())
            rows01 = list(client.query(q01.sql).result())
        except Exception as exc:
            return WeatherNextDiagnostic(classify_bigquery_error(exc))
        return WeatherNextDiagnostic("ready" if rows05 and rows01 else "data_latency", checked_init_time_utc=init_time.isoformat().replace("+00:00", "Z"))

    def fetch(
        self, *, lat: float, lon: float, now: datetime | None = None,
        init_time: datetime | None = None,
    ) -> ForecastRun:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        init_time = init_time or latest_available_init(now)
        client = self._client_or_create()
        q05 = build_point_query(project=self.project, dataset=self.dataset, lat=lat, lon=lon, init_time=init_time, resolution="0p05")
        q01 = build_point_query(project=self.project, dataset=self.dataset, lat=lat, lon=lon, init_time=init_time, resolution="0p1")
        for query in (q05, q01):
            errors = validate_query_contract(query)
            if errors:
                raise ValueError("invalid WeatherNext query contract: " + ",".join(errors))
        rows05 = [dict(row) for row in client.query(q05.sql).result()]
        rows01 = [dict(row) for row in client.query(q01.sql).result()]
        if not rows05 or not rows01:
            raise WeatherNextDataLatency("WeatherNext data not yet available for selected init")
        run05 = rows_to_run(rows05, resolution="0p05", init_time=init_time, retrieved_at=now)
        run01 = rows_to_run(rows01, resolution="0p1", init_time=init_time, retrieved_at=now)
        surface_values = tuple(value for value in run01.values if value.variable not in {"temperature_2m", "dew_point_2m"})
        expected = expected_available_at(init_time)
        return ForecastRun(
            provider="weathernext3", model_provider="Google DeepMind", model_name="WeatherNext 3",
            model_version="3.0.0", init_time_utc=init_time, retrieved_at_utc=now,
            source_surface="BigQuery WeatherNext 3 0.05° station + 0.1° surface",
            transport_provider="Google BigQuery", values=tuple(run05.values) + surface_values,
            source_metadata={
                "tables": [q05.table, q01.table], "station_resolution": "0.05deg",
                "surface_resolution": "0.1deg", "statistics": list(STATS),
                "expected_available_at_utc": expected.isoformat().replace("+00:00", "Z"),
                "upstream_available_at_observed": False,
                "partition_filter": "init_time", "selected_columns_only": True,
                "run_class": run_class(init_time), "forecast_horizon_hours": forecast_horizon_hours(init_time),
            },
            init_time_quality="provider_native",
            upstream_available_at_utc=None,
        )

    def fetch_latest_with_fallback(
        self, *, lat: float, lon: float, now: datetime | None = None,
        max_candidates: int = 4,
    ) -> ForecastRun:
        """Try older target-disseminated hourly runs only for genuine data latency."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidates = available_init_candidates(now, limit=max_candidates)
        if not candidates:
            raise RuntimeError("no WeatherNext init fits the expected dissemination window")
        last_latency: WeatherNextDataLatency | None = None
        for candidate in candidates:
            try:
                return self.fetch(lat=lat, lon=lon, now=now, init_time=candidate)
            except WeatherNextDataLatency as exc:
                last_latency = exc
                continue
        assert last_latency is not None
        raise last_latency
