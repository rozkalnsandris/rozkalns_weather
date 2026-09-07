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


@dataclass(frozen=True, slots=True)
class WeatherNextQuery:
    table: str
    sql: str
    resolution: str


def _table(project: str, dataset: str, suffix: str) -> str:
    for token in (project, dataset):
        if not token.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid BigQuery project/dataset identifier")
    return f"`{project}.{dataset}.{suffix}`"


def build_point_query(
    *, project: str, dataset: str, lat: float, lon: float, init_time: datetime, resolution: str
) -> WeatherNextQuery:
    if resolution not in {"0p05", "0p1"}:
        raise ValueError("resolution must be 0p05 or 0p1")
    suffix = "weathernext_3_0_0_0p05deg" if resolution == "0p05" else "weathernext_3_0_0_0p1deg"
    table = _table(project, dataset, suffix)
    fields = STATION_FIELDS if resolution == "0p05" else SURFACE_FIELDS
    selected = ["f.time AS forecast_time", "f.hours AS forecast_hour"]
    for field in fields:
        selected.extend(f"f.{field}_{stat} AS {field}_{stat}" for stat in STATS)
    init_literal = init_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")
    sql = f"""
SELECT
  {', '.join(selected)}
FROM {table} AS t, t.forecast AS f
WHERE t.init_time = TIMESTAMP('{init_literal}')
  AND ST_COVERS(t.geography_polygon, ST_GEOGPOINT({lon:.8f}, {lat:.8f}))
ORDER BY f.time ASC
""".strip()
    return WeatherNextQuery(table=table, sql=sql, resolution=resolution)


def build_schema_probe_query(*, project: str, dataset: str) -> str:
    for token in (project, dataset):
        if not token.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid BigQuery project/dataset identifier")
    return f"""
SELECT table_name, column_name, field_path, data_type
FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
WHERE table_name IN ('weathernext_3_0_0_0p05deg', 'weathernext_3_0_0_0p1deg')
ORDER BY table_name, field_path
""".strip()


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


def rows_to_run(
    rows: Iterable[Mapping[str, Any]],
    *,
    resolution: str,
    init_time: datetime,
    retrieved_at: datetime,
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
                values.append(
                    ForecastValue(
                        valid_time_utc=valid,
                        lead_hours=lead,
                        variable=variable,
                        statistic=stat,
                        value=_convert(native_value, native_unit, unit),
                        unit=unit,
                        native_value=native_value,
                        native_unit=native_unit,
                        accumulation_window_minutes=accumulation,
                    )
                )
    return ForecastRun(
        provider="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        model_version="3.0.0",
        init_time_utc=init_time,
        retrieved_at_utc=retrieved_at,
        source_surface=f"BigQuery WeatherNext 3 {resolution}",
        transport_provider="Google BigQuery",
        values=tuple(values),
        source_metadata={"resolution": resolution, "statistics": list(STATS)},
    )


def expected_available_at(init_time: datetime, *, platform: str = "bigquery") -> datetime:
    init_time = init_time.astimezone(timezone.utc)
    if platform.lower() not in {"bigquery", "earth_engine"}:
        raise ValueError("only BigQuery/Earth Engine latency is modeled here")
    if init_time.hour in {0, 6, 12, 18}:
        return init_time + timedelta(hours=8, minutes=10)
    return init_time + timedelta(hours=7, minutes=25)


def access_state(*, configured: bool, now: datetime, init_time: datetime | None = None) -> str:
    if not configured:
        return "access_pending"
    if init_time is not None and now.astimezone(timezone.utc) < expected_available_at(init_time):
        return "within_expected_dissemination_latency"
    return "configured"


def latest_available_init(now: datetime, *, synoptic_only: bool = True) -> datetime:
    """Latest init whose documented BigQuery target dissemination window has passed."""
    cursor = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for offset in range(0, 48):
        candidate = cursor - timedelta(hours=offset)
        if synoptic_only and candidate.hour not in {0, 6, 12, 18}:
            continue
        if expected_available_at(candidate) <= now.astimezone(timezone.utc):
            return candidate
    raise RuntimeError("no WeatherNext init fits the expected dissemination window")


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
            raise RuntimeError(
                "WeatherNext live ingest requires the optional 'weathernext' dependency"
            ) from exc
        self._client = bigquery.Client(project=self.project)
        return self._client

    def schema_probe(self) -> list[dict[str, Any]]:
        client = self._client_or_create()
        sql = build_schema_probe_query(project=self.project, dataset=self.dataset)
        return [dict(row) for row in client.query(sql).result()]

    def fetch(
        self,
        *,
        lat: float,
        lon: float,
        now: datetime | None = None,
        init_time: datetime | None = None,
    ) -> ForecastRun:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        init_time = init_time or latest_available_init(now, synoptic_only=True)
        client = self._client_or_create()

        q05 = build_point_query(project=self.project, dataset=self.dataset, lat=lat, lon=lon, init_time=init_time, resolution="0p05")
        q01 = build_point_query(project=self.project, dataset=self.dataset, lat=lat, lon=lon, init_time=init_time, resolution="0p1")
        rows05 = [dict(row) for row in client.query(q05.sql).result()]
        rows01 = [dict(row) for row in client.query(q01.sql).result()]
        run05 = rows_to_run(rows05, resolution="0p05", init_time=init_time, retrieved_at=now)
        run01 = rows_to_run(rows01, resolution="0p1", init_time=init_time, retrieved_at=now)

        surface_values = tuple(value for value in run01.values if value.variable not in {"temperature_2m", "dew_point_2m"})
        return ForecastRun(
            provider="weathernext3",
            model_provider="Google DeepMind",
            model_name="WeatherNext 3",
            model_version="3.0.0",
            init_time_utc=init_time,
            retrieved_at_utc=now,
            source_surface="BigQuery WeatherNext 3 0.05° station + 0.1° surface",
            transport_provider="Google BigQuery",
            values=tuple(run05.values) + surface_values,
            source_metadata={
                "tables": [q05.table, q01.table],
                "station_resolution": "0.05deg",
                "surface_resolution": "0.1deg",
                "statistics": list(STATS),
                "expected_available_at_utc": expected_available_at(init_time).isoformat(),
            },
        )
