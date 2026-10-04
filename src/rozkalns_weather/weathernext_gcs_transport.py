from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Callable, Mapping

import httpx

from .locations import BENCHMARK_LOCATION
from .models import ForecastRun, ensure_utc
from .providers.weathernext import STATS
from .weathernext_gcs import (
    GCS_DISCOVERY_MAX_CANDIDATES,
    GCS_FIRST_PRIVATE_READ_HOURS,
    GCS_STATISTICS_BUCKET,
    GCS_STATISTICS_ROOT,
    REQUIRED_STATISTIC_VARIABLES,
    STATION_STATISTIC_VARIABLES,
    SURFACE_STATISTIC_VARIABLES,
    nearest_gcs_grid_indices,
    resolve_statistics_run_directory,
    statistics_point_records_to_run,
    statistics_run_discovery_prefix,
    statistics_run_prefix,
    validate_statistics_schema,
)

GCS_JSON_OBJECTS_ENDPOINT = (
    f"https://storage.googleapis.com/storage/v1/b/{GCS_STATISTICS_BUCKET}/o"
)
GCS_TRANSPORT_STACK = "GCS JSON list + obstore + zarr + xarray"
GCS_DISCOVERY_MAX_RESULTS = GCS_DISCOVERY_MAX_CANDIDATES + 1
GCS_REQUEST_TIMEOUT_SECONDS = 20.0


class WeatherNextGCSTransportError(RuntimeError):
    """A bounded WeatherNext GCS transport or selection contract failed closed."""


@dataclass(frozen=True, slots=True)
class GCSFirstAccessResult:
    evidence: Mapping[str, object]
    run: ForecastRun


def _credential_token(credential_provider: Callable[[], Mapping[str, Any]]) -> str:
    if not callable(credential_provider):
        raise WeatherNextGCSTransportError("explicit GCS credential provider is required")
    value = credential_provider()
    if type(value) is not dict:
        raise WeatherNextGCSTransportError("GCS credential provider returned invalid state")
    token = value.get("token")
    if type(token) is not str or not token.strip():
        raise WeatherNextGCSTransportError("GCS credential provider returned no token")
    return token


def discover_private_run_directory(
    *,
    init_time: datetime,
    credential_provider: Callable[[], Mapping[str, Any]],
    client: Any | None = None,
) -> str:
    """Resolve exactly one run directory with one tightly scoped GCS JSON list."""

    init_time = ensure_utc(init_time)
    discovery_prefix = statistics_run_discovery_prefix(init_time=init_time)
    token = _credential_token(credential_provider)
    owns_client = client is None
    http = client or httpx.Client(
        timeout=GCS_REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    try:
        response = http.get(
            GCS_JSON_OBJECTS_ENDPOINT,
            params={
                "prefix": discovery_prefix,
                "delimiter": "/",
                "maxResults": GCS_DISCOVERY_MAX_RESULTS,
                "projection": "noAcl",
                "fields": "nextPageToken,prefixes,items(name)",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            raise WeatherNextGCSTransportError("GCS run-directory discovery failed")
        try:
            payload = response.json()
        except Exception:
            raise WeatherNextGCSTransportError(
                "GCS run-directory discovery returned invalid JSON"
            ) from None
    finally:
        if owns_client:
            http.close()

    if type(payload) is not dict:
        raise WeatherNextGCSTransportError("GCS run-directory discovery payload is invalid")
    if payload.get("nextPageToken"):
        raise WeatherNextGCSTransportError("GCS run-directory discovery exceeded candidate bound")
    prefixes = payload.get("prefixes", [])
    items = payload.get("items", [])
    if type(prefixes) is not list or type(items) is not list:
        raise WeatherNextGCSTransportError("GCS run-directory discovery shape is invalid")
    if len(prefixes) + len(items) > GCS_DISCOVERY_MAX_CANDIDATES:
        raise WeatherNextGCSTransportError("GCS run-directory discovery exceeded candidate bound")
    if items:
        raise WeatherNextGCSTransportError("GCS run-directory discovery returned unexpected objects")

    root = f"{GCS_STATISTICS_ROOT}/"
    candidates: list[str] = []
    for raw in prefixes:
        if type(raw) is not str or not raw.startswith(root) or not raw.endswith("/"):
            raise WeatherNextGCSTransportError("GCS run-directory prefix escaped fixed root")
        token_value = raw[len(root) : -1]
        if not token_value or "/" in token_value:
            raise WeatherNextGCSTransportError("GCS run-directory prefix shape is invalid")
        candidates.append(token_value)

    try:
        return resolve_statistics_run_directory(
            init_time=init_time,
            candidates=candidates,
        )
    except ValueError as exc:
        raise WeatherNextGCSTransportError(str(exc)) from exc


def _default_store_factory(**kwargs: Any) -> Any:
    try:
        from obstore.store import GCSStore
    except ImportError as exc:
        raise WeatherNextGCSTransportError(
            "WeatherNext GCS access requires the optional 'weathernext-gcs' dependency"
        ) from exc
    return GCSStore(**kwargs)


def _default_dataset_opener(store: Any) -> Any:
    try:
        import xarray as xr
        import zarr
    except ImportError as exc:
        raise WeatherNextGCSTransportError(
            "WeatherNext GCS access requires the optional 'weathernext-gcs' dependency"
        ) from exc
    zstore = zarr.storage.ObjectStore(store)
    return xr.open_zarr(
        zstore,
        chunks=None,
        create_default_indexes=False,
        zarr_format=3,
    )


def open_private_statistics_dataset(
    *,
    init_time: datetime,
    run_directory: str,
    credential_provider: Callable[[], Mapping[str, Any]],
    store_factory: Callable[..., Any] | None = None,
    dataset_opener: Callable[[Any], Any] | None = None,
) -> Any:
    """Open only one exact statistics Zarr store without ambient auth or retries."""

    if not callable(credential_provider):
        raise WeatherNextGCSTransportError("explicit GCS credential provider is required")
    prefix = statistics_run_prefix(
        init_time=init_time,
        run_directory=run_directory,
    )
    factory = store_factory or _default_store_factory
    opener = dataset_opener or _default_dataset_opener
    store = factory(
        bucket=GCS_STATISTICS_BUCKET,
        prefix=prefix,
        credential_provider=credential_provider,
        retry_config={"max_retries": 0},
    )
    return opener(store)


def _values_list(value: Any) -> list[Any]:
    raw = getattr(value, "values", value)
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if isinstance(raw, tuple):
        raw = list(raw)
    return raw if isinstance(raw, list) else [raw]


def _as_utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        import numpy as np

        if isinstance(value, np.datetime64):
            if np.isnat(value):
                raise WeatherNextGCSTransportError("dataset init_time is NaT")
            seconds = int(value.astype("datetime64[s]").astype("int64"))
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except ImportError:
        pass
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise WeatherNextGCSTransportError("dataset init_time is not a supported UTC scalar")


def _lead_hour(value: Any) -> int:
    if isinstance(value, timedelta):
        hours = value.total_seconds() / 3600.0
    else:
        try:
            import numpy as np

            if isinstance(value, np.timedelta64):
                if np.isnat(value):
                    raise WeatherNextGCSTransportError("dataset lead_time contains NaT")
                hours = float(value / np.timedelta64(1, "h"))
            else:
                raise TypeError
        except ImportError:
            raise WeatherNextGCSTransportError(
                "dataset lead_time is not a supported duration"
            ) from None
        except TypeError:
            raise WeatherNextGCSTransportError(
                "dataset lead_time is not a supported duration"
            ) from None
    if not isfinite(hours) or int(hours) != hours:
        raise WeatherNextGCSTransportError("dataset lead_time must be an exact whole hour")
    return int(hours)


def _numeric_vector(value: Any, *, name: str) -> tuple[float, ...]:
    result = tuple(float(item) for item in _values_list(value))
    if not result or any(not isfinite(item) for item in result):
        raise WeatherNextGCSTransportError(f"{name} coordinate vector is invalid")
    return result


def _dataset_schema(dataset: Any) -> dict[str, tuple[str, ...]]:
    return {
        "coordinates": tuple(str(name) for name in dataset.coords),
        "dimensions": tuple(str(name) for name in dataset.sizes),
        "variables": tuple(str(name) for name in dataset.data_vars),
    }


def _lead_indices(dataset: Any, *, hours_limit: int) -> list[int]:
    raw = getattr(dataset["lead_time"], "values", dataset["lead_time"])
    try:
        observed = [_lead_hour(item) for item in raw]
    except TypeError:
        observed = [_lead_hour(raw)]
    result: list[int] = []
    for expected in range(1, hours_limit + 1):
        matches = [index for index, hour in enumerate(observed) if hour == expected]
        if len(matches) != 1:
            raise WeatherNextGCSTransportError(
                "dataset lead_time must contain each bounded hour exactly once"
            )
        result.append(matches[0])
    return result


def _point_records(
    dataset: Any,
    *,
    variables: tuple[str, ...],
    lead_indices: list[int],
    hours_limit: int,
    lat_name: str,
    lon_name: str,
    lat_index: int,
    lon_index: int,
) -> tuple[dict[str, Any], ...]:
    records = [{"lead_hour": hour} for hour in range(1, hours_limit + 1)]
    base_indexers: dict[str, Any] = {
        "lead_time": lead_indices,
        lat_name: lat_index,
        lon_name: lon_index,
    }
    if "init_time" in dataset.sizes:
        if int(dataset.sizes["init_time"]) != 1:
            raise WeatherNextGCSTransportError("dataset init_time dimension must be singleton")
        base_indexers["init_time"] = 0

    for variable in variables:
        selected = dataset[variable].isel(**base_indexers)
        values = _values_list(selected)
        if len(values) != hours_limit:
            raise WeatherNextGCSTransportError(
                "bounded point selection returned an unexpected value count"
            )
        for record, raw in zip(records, values):
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                raise WeatherNextGCSTransportError(
                    "bounded point selection returned a non-numeric value"
                ) from None
            if not isfinite(numeric):
                raise WeatherNextGCSTransportError(
                    "bounded point selection returned a non-finite value"
                )
            record[variable] = numeric
    return tuple(records)


def validate_gcs_provenance(run: ForecastRun) -> dict[str, object]:
    errors: list[str] = []
    if run.provider != "weathernext3":
        errors.append("provider")
    if run.model_provider != "Google DeepMind":
        errors.append("model_provider")
    if run.model_name != "WeatherNext 3":
        errors.append("model_name")
    if run.model_version != "3.0.0":
        errors.append("model_version")
    if run.transport_provider != "Google Cloud Storage/Zarr":
        errors.append("transport_provider")
    if not run.source_surface.startswith("GCS WeatherNext 3 statistics Zarr"):
        errors.append("source_surface")
    metadata = run.source_metadata
    if metadata.get("location_id") != BENCHMARK_LOCATION.id:
        errors.append("location_id")
    if metadata.get("bucket") != GCS_STATISTICS_BUCKET:
        errors.append("bucket")
    if tuple(metadata.get("statistics") or ()) != STATS:
        errors.append("statistics")
    if metadata.get("slice_before_materialization") is not True:
        errors.append("slice_before_materialization")
    if metadata.get("full_dataset_load_used") is not False:
        errors.append("full_dataset_load_used")
    if metadata.get("full_ensemble_fallback_used") is not False:
        errors.append("full_ensemble_fallback_used")
    if run.upstream_available_at_utc is not None:
        errors.append("unverified_upstream_available_at")
    if not run.values:
        errors.append("values")
    for value in run.values:
        if value.statistic not in STATS:
            errors.append("unexpected_statistic")
            break
        expected_lead = (
            value.valid_time_utc - run.init_time_utc
        ).total_seconds() / 3600.0
        if abs(value.lead_hours - expected_lead) > 1e-6:
            errors.append("lead_hours")
            break
    for value in run.values:
        if (
            value.variable == "precipitation_1h"
            and value.accumulation_window_minutes != 60
        ):
            errors.append("precipitation_accumulation")
            break
    return {
        "complete": not errors,
        "state": "complete" if not errors else "invalid",
        "errors": sorted(set(errors)),
    }


def read_private_first_access_gcs(
    *,
    init_time: datetime,
    retrieved_at: datetime,
    credential_provider: Callable[[], Mapping[str, Any]],
    client: Any | None = None,
    store_factory: Callable[..., Any] | None = None,
    dataset_opener: Callable[[Any], Any] | None = None,
) -> GCSFirstAccessResult:
    """Execute the exact source-defined private GCS read; no persistence is possible."""

    init_time = ensure_utc(init_time)
    retrieved_at = ensure_utc(retrieved_at)
    run_directory = discover_private_run_directory(
        init_time=init_time,
        credential_provider=credential_provider,
        client=client,
    )
    dataset = open_private_statistics_dataset(
        init_time=init_time,
        run_directory=run_directory,
        credential_provider=credential_provider,
        store_factory=store_factory,
        dataset_opener=dataset_opener,
    )
    close = getattr(dataset, "close", None)
    try:
        schema = _dataset_schema(dataset)
        errors = validate_statistics_schema(schema)
        if errors:
            raise WeatherNextGCSTransportError(
                "WeatherNext GCS statistics schema mismatch: " + ",".join(errors)
            )

        init_values = _values_list(dataset["init_time"])
        if len(init_values) != 1 or _as_utc_datetime(init_values[0]) != init_time:
            raise WeatherNextGCSTransportError(
                "WeatherNext GCS dataset init_time does not match requested init"
            )

        lead_indices = _lead_indices(
            dataset,
            hours_limit=GCS_FIRST_PRIVATE_READ_HOURS,
        )
        station_indices = nearest_gcs_grid_indices(
            latitudes=_numeric_vector(dataset["lat_0p05"], name="lat_0p05"),
            longitudes=_numeric_vector(dataset["lon_0p05"], name="lon_0p05"),
            lat=BENCHMARK_LOCATION.lat,
            lon=BENCHMARK_LOCATION.lon,
            resolution_degrees=0.05,
        )
        surface_indices = nearest_gcs_grid_indices(
            latitudes=_numeric_vector(dataset["lat_0p1"], name="lat_0p1"),
            longitudes=_numeric_vector(dataset["lon_0p1"], name="lon_0p1"),
            lat=BENCHMARK_LOCATION.lat,
            lon=BENCHMARK_LOCATION.lon,
            resolution_degrees=0.1,
        )
        station_records = _point_records(
            dataset,
            variables=STATION_STATISTIC_VARIABLES,
            lead_indices=lead_indices,
            hours_limit=GCS_FIRST_PRIVATE_READ_HOURS,
            lat_name="lat_0p05",
            lon_name="lon_0p05",
            lat_index=station_indices["lat_index"],
            lon_index=station_indices["lon_index"],
        )
        surface_records = _point_records(
            dataset,
            variables=SURFACE_STATISTIC_VARIABLES,
            lead_indices=lead_indices,
            hours_limit=GCS_FIRST_PRIVATE_READ_HOURS,
            lat_name="lat_0p1",
            lon_name="lon_0p1",
            lat_index=surface_indices["lat_index"],
            lon_index=surface_indices["lon_index"],
        )
    finally:
        if callable(close):
            close()

    run = statistics_point_records_to_run(
        station_records,
        surface_records,
        init_time=init_time,
        retrieved_at=retrieved_at,
        run_directory=run_directory,
        hours_limit=GCS_FIRST_PRIVATE_READ_HOURS,
    )
    provenance = validate_gcs_provenance(run)
    if not provenance["complete"]:
        raise WeatherNextGCSTransportError("WeatherNext GCS provenance validation failed")

    materialized = GCS_FIRST_PRIVATE_READ_HOURS * len(REQUIRED_STATISTIC_VARIABLES)
    evidence: dict[str, object] = {
        "schema_version": 1,
        "state": "gcs_canary_complete",
        "transport": GCS_TRANSPORT_STACK,
        "model_version": "3.0.0",
        "location_id": BENCHMARK_LOCATION.id,
        "selected_init_time_utc": init_time.isoformat().replace("+00:00", "Z"),
        "run_directory": run_directory,
        "lead_hour_start": 1,
        "lead_hour_end": GCS_FIRST_PRIVATE_READ_HOURS,
        "lead_count": GCS_FIRST_PRIVATE_READ_HOURS,
        "station_statistic_variable_count": len(STATION_STATISTIC_VARIABLES),
        "surface_statistic_variable_count": len(SURFACE_STATISTIC_VARIABLES),
        "materialized_scalar_count": materialized,
        "schema_valid": True,
        "provenance_complete": True,
        "automatic_retry_used": False,
        "full_dataset_load_used": False,
        "persistent_object_download_performed": False,
        "full_ensemble_fallback_used": False,
        "coordinates_exposed": False,
        "raw_values_exposed": False,
        "production_write_performed": False,
    }
    return GCSFirstAccessResult(evidence=evidence, run=run)
