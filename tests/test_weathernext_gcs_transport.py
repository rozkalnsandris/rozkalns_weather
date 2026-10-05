from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tomllib

import pytest

from rozkalns_weather.locations import BENCHMARK_LOCATION
from rozkalns_weather.weathernext_gcs import (
    GCS_STATISTICS_BUCKET,
    GCS_STATISTICS_ROOT,
    REQUIRED_STATISTIC_VARIABLES,
    STATION_STATISTIC_VARIABLES,
    SURFACE_STATISTIC_VARIABLES,
)
from rozkalns_weather.weathernext_gcs_transport import (
    GCS_DISCOVERY_MAX_RESULTS,
    GCS_JSON_OBJECTS_ENDPOINT,
    WeatherNextGCSTransportError,
    discover_private_run_directory,
    open_private_statistics_dataset,
    read_private_first_access_gcs,
)


INIT = datetime(2026, 10, 1, 23, tzinfo=timezone.utc)
RETRIEVED = datetime(2026, 10, 2, 7, 30, tzinfo=timezone.utc)
RUN_DIRECTORY = "20261001_23hr_07_preds"
ROOT = Path(__file__).resolve().parents[1]


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, *, params, headers):
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        return _Response(self.payload)


class _ScalarAxisValue:
    ndim = 0

    def __init__(self, value):
        self._value = value

    def __getitem__(self, key):
        if key != ():
            raise KeyError(key)
        return self._value

    def tolist(self):
        return int(self._value.timestamp() * 1_000_000_000)


class _LeadAxisValues:
    def __init__(self, values):
        self._values = list(values)

    def __iter__(self):
        return iter(self._values)

    def tolist(self):
        return [int(value.total_seconds() * 1_000_000_000) for value in self._values]


class _Array:
    def __init__(self, values):
        self.values = values
        self.indexers = []

    def isel(self, **indexers):
        self.indexers.append(dict(indexers))
        values = self.values
        lead = indexers.get("lead_time")
        if isinstance(lead, list):
            values = [values[index] for index in lead]
        return _Array(values)


class _Dataset:
    def __init__(self, *, missing_variable=None):
        lat05 = BENCHMARK_LOCATION.lat
        lon05 = BENCHMARK_LOCATION.lon % 360.0
        self.coords = {
            "init_time": None,
            "lead_time": None,
            "lat_0p05": None,
            "lon_0p05": None,
            "lat_0p1": None,
            "lon_0p1": None,
        }
        self.sizes = {
            "lead_time": 7,
            "lat_0p05": 3,
            "lon_0p05": 3,
            "lat_0p1": 3,
            "lon_0p1": 3,
        }
        self._arrays = {
            "init_time": _Array([INIT]),
            "lead_time": _Array([timedelta(hours=hour) for hour in range(7)]),
            "lat_0p05": _Array([lat05 - 0.05, lat05, lat05 + 0.05]),
            "lon_0p05": _Array([lon05 - 0.05, lon05, lon05 + 0.05]),
            "lat_0p1": _Array([lat05 - 0.1, lat05, lat05 + 0.1]),
            "lon_0p1": _Array([lon05 - 0.1, lon05, lon05 + 0.1]),
        }
        for name in sorted(REQUIRED_STATISTIC_VARIABLES):
            if name == missing_variable:
                continue
            if "precipitation" in name:
                base = 0.001
            elif "pressure" in name:
                base = 101325.0
            elif "cloud" in name:
                base = 0.5
            elif "wind" in name:
                base = 5.0
            else:
                base = 290.0
            self._arrays[name] = _Array([base + hour * 0.001 for hour in range(7)])
        self.data_vars = {
            name: None
            for name in self._arrays
            if name not in self.coords
        }
        self.closed = False

    def __getitem__(self, key):
        return self._arrays[key]

    def close(self):
        self.closed = True

    def load(self):
        raise AssertionError("full dataset load is forbidden")


def _credential_provider():
    return {"token": "fixture-only", "expires_at": None}


def test_discovery_uses_one_exact_partial_prefix_request_and_no_pagination() -> None:
    prefix = f"{GCS_STATISTICS_ROOT}/{RUN_DIRECTORY}/"
    client = _Client({"prefixes": [prefix], "items": []})

    resolved = discover_private_run_directory(
        init_time=INIT,
        credential_provider=_credential_provider,
        client=client,
    )

    assert resolved == RUN_DIRECTORY
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == GCS_JSON_OBJECTS_ENDPOINT
    assert call["params"] == {
        "prefix": f"{GCS_STATISTICS_ROOT}/20261001_23hr_",
        "delimiter": "/",
        "maxResults": GCS_DISCOVERY_MAX_RESULTS,
        "projection": "noAcl",
        "fields": "nextPageToken,prefixes,items(name)",
    }
    assert call["headers"]["Authorization"].startswith("Bearer ")
    assert "fixture-only" not in str(call["params"])

    with pytest.raises(WeatherNextGCSTransportError, match="exceeded candidate bound"):
        discover_private_run_directory(
            init_time=INIT,
            credential_provider=_credential_provider,
            client=_Client({"prefixes": [prefix], "items": [], "nextPageToken": "more"}),
        )


def test_private_dataset_open_requires_explicit_credentials_and_disables_retry() -> None:
    captured = {}

    def store_factory(**kwargs):
        captured.update(kwargs)
        return object()

    dataset = object()
    opened = open_private_statistics_dataset(
        init_time=INIT,
        run_directory=RUN_DIRECTORY,
        credential_provider=_credential_provider,
        store_factory=store_factory,
        dataset_opener=lambda store: dataset,
    )

    assert opened is dataset
    assert captured["bucket"] == GCS_STATISTICS_BUCKET
    assert captured["prefix"].endswith(f"/{RUN_DIRECTORY}/predictions.zarr")
    assert captured["credential_provider"] is _credential_provider
    assert captured["retry_config"] == {"max_retries": 0}

    with pytest.raises(WeatherNextGCSTransportError, match="credential provider"):
        open_private_statistics_dataset(
            init_time=INIT,
            run_directory=RUN_DIRECTORY,
            credential_provider=None,  # type: ignore[arg-type]
            store_factory=store_factory,
            dataset_opener=lambda store: dataset,
        )


def test_first_access_reads_only_bounded_point_statistics_and_emits_sanitized_evidence() -> None:
    prefix = f"{GCS_STATISTICS_ROOT}/{RUN_DIRECTORY}/"
    client = _Client({"prefixes": [prefix], "items": []})
    dataset = _Dataset()
    store_calls = []

    def store_factory(**kwargs):
        store_calls.append(dict(kwargs))
        return object()

    result = read_private_first_access_gcs(
        init_time=INIT,
        retrieved_at=RETRIEVED,
        credential_provider=_credential_provider,
        client=client,
        store_factory=store_factory,
        dataset_opener=lambda store: dataset,
    )

    evidence = dict(result.evidence)
    assert dataset.closed is True
    assert len(store_calls) == 1
    assert store_calls[0]["retry_config"] == {"max_retries": 0}
    assert evidence["state"] == "gcs_canary_complete"
    assert evidence["location_id"] == "station_05480"
    assert evidence["run_directory"] == RUN_DIRECTORY
    assert evidence["lead_count"] == 6
    assert evidence["station_statistic_variable_count"] == len(STATION_STATISTIC_VARIABLES)
    assert evidence["surface_statistic_variable_count"] == len(SURFACE_STATISTIC_VARIABLES)
    assert evidence["materialized_scalar_count"] == 288
    assert evidence["automatic_retry_used"] is False
    assert evidence["full_dataset_load_used"] is False
    assert evidence["persistent_object_download_performed"] is False
    assert evidence["full_ensemble_fallback_used"] is False
    assert evidence["coordinates_exposed"] is False
    assert evidence["raw_values_exposed"] is False
    assert evidence["production_write_performed"] is False
    assert result.run.transport_provider == "Google Cloud Storage/Zarr"
    assert result.run.source_metadata["location_id"] == "station_05480"
    assert result.run.upstream_available_at_utc is None
    rendered = str(evidence)
    assert "fixture-only" not in rendered
    assert str(BENCHMARK_LOCATION.lat) not in rendered
    assert str(BENCHMARK_LOCATION.lon) not in rendered


def test_init_axis_preserves_scalar_type_without_tolist_coercion() -> None:
    dataset = _Dataset()
    dataset._arrays["init_time"] = _Array(_ScalarAxisValue(INIT))

    prefix = f"{GCS_STATISTICS_ROOT}/{RUN_DIRECTORY}/"
    result = read_private_first_access_gcs(
        init_time=INIT,
        retrieved_at=RETRIEVED,
        credential_provider=_credential_provider,
        client=_Client({"prefixes": [prefix], "items": []}),
        store_factory=lambda **kwargs: object(),
        dataset_opener=lambda store: dataset,
    )

    assert result.evidence["selected_init_time_utc"] == "2026-10-01T23:00:00Z"
    assert dataset.closed is True


def test_lead_axis_preserves_iterable_scalar_types_without_tolist_coercion() -> None:
    dataset = _Dataset()
    dataset._arrays["lead_time"] = _Array(
        _LeadAxisValues([timedelta(hours=hour) for hour in range(7)])
    )

    prefix = f"{GCS_STATISTICS_ROOT}/{RUN_DIRECTORY}/"
    result = read_private_first_access_gcs(
        init_time=INIT,
        retrieved_at=RETRIEVED,
        credential_provider=_credential_provider,
        client=_Client({"prefixes": [prefix], "items": []}),
        store_factory=lambda **kwargs: object(),
        dataset_opener=lambda store: dataset,
    )

    assert result.evidence["lead_count"] == 6
    assert dataset.closed is True


def test_first_access_fails_closed_on_schema_drift_without_fallback() -> None:
    prefix = f"{GCS_STATISTICS_ROOT}/{RUN_DIRECTORY}/"
    client = _Client({"prefixes": [prefix], "items": []})
    dataset = _Dataset(missing_variable=STATION_STATISTIC_VARIABLES[0])

    with pytest.raises(WeatherNextGCSTransportError, match="schema mismatch"):
        read_private_first_access_gcs(
            init_time=INIT,
            retrieved_at=RETRIEVED,
            credential_provider=_credential_provider,
            client=client,
            store_factory=lambda **kwargs: object(),
            dataset_opener=lambda store: dataset,
        )
    assert dataset.closed is True


def test_gcs_optional_extra_declares_explicit_auth_runtime_without_public_runtime_drift() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    optional = project["project"]["optional-dependencies"]
    gcs = tuple(optional["weathernext-gcs"])
    assert gcs == (
        "dask[array]>=2026.8,<2027",
        "google-auth>=2.59.1,<3",
        "obstore>=0.11.1,<0.12",
        "requests>=2.34.2,<3",
        "xarray>=2026.9,<2027",
        "zarr>=3.4,<4",
    )
    assert tuple(project["project"]["dependencies"]) == (
        "fastapi>=0.116,<1",
        "httpx>=0.28,<1",
        "uvicorn>=0.35,<1",
    )
    assert "google-cloud-bigquery>=3.36,<4" not in gcs



def test_gcs_transport_source_stays_callback_only_and_does_not_load_credentials() -> None:
    source = (
        ROOT / "src/rozkalns_weather/weathernext_gcs_transport.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "google.auth",
        "from_service_account_file",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "google.auth.default",
        "load_credentials_from_file",
        "service_account.Credentials",
    )
    for token in forbidden:
        assert token not in source
    assert "explicit GCS credential provider is required" in source
    assert "credential_provider=credential_provider" in source
    assert "chunks={}" in source
    assert "chunks=None" not in source
