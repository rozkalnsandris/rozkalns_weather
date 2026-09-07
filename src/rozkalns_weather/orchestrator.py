from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Callable, TypeVar

from .config import Settings
from .db import Database
from .locations import DWD_10416
from .models import ForecastRun, Observation
from .providers.base import bytes_fetcher, json_fetcher
from .providers.dwd_mosmix import DwdMosmixAdapter
from .providers.dwd_observations import DwdObservationAdapter
from .providers.open_meteo import ECMWF_AIFS, ECMWF_IFS, ICON_D2, OpenMeteoSingleRunAdapter
from .providers.weathernext import WeatherNextBigQueryAdapter, latest_available_init

T = TypeVar("T")

class IngestAlreadyRunning(RuntimeError):
    pass

class FileRunLock:
    def __init__(self, path: Path, *, stale_after_seconds: int = 3600) -> None:
        self.path = path
        self.stale_after_seconds = stale_after_seconds
        self._held = False

    def __enter__(self) -> "FileRunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError:
                age = 0
            if age > self.stale_after_seconds:
                self.path.unlink(missing_ok=True)
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            else:
                raise IngestAlreadyRunning("ingest cycle already running") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "created_at": datetime.now(timezone.utc).isoformat()}, handle)
        self._held = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False

@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    provider: str
    state: str
    attempts: int
    detail: str | None = None
    init_time_utc: str | None = None
    locations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {"provider": self.provider, "state": self.state, "attempts": self.attempts, "detail": self.detail, "init_time_utc": self.init_time_utc, "locations": list(self.locations)}

def retry_read_only(action: Callable[[], T], *, attempts: int, sleeper: Callable[[float], None] = time.sleep) -> tuple[T, int]:
    if attempts < 1 or attempts > 5:
        raise ValueError("attempts must be between 1 and 5")
    last: Exception | None = None
    for index in range(1, attempts + 1):
        try:
            return action(), index
        except Exception as exc:
            last = exc
            if index < attempts:
                sleeper(min(2.0, 0.25 * index))
    assert last is not None
    raise last

class IngestOrchestrator:
    def __init__(self, settings: Settings, database: Database, *, timeout_seconds: float | None = None, retry_attempts: int | None = None, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.settings = settings
        self.database = database
        self.timeout_seconds = timeout_seconds or settings.ingest_timeout_seconds
        self.retry_attempts = retry_attempts or settings.ingest_retries
        self.sleeper = sleeper

    def _ensure_locations(self) -> None:
        self.database.ensure_location(location_id=DWD_10416.id, label=DWD_10416.label, lat=DWD_10416.lat, lon=DWD_10416.lon, elevation_m=DWD_10416.elevation_m, timezone=DWD_10416.timezone)
        if self.settings.home_configured:
            assert self.settings.home_lat is not None and self.settings.home_lon is not None
            self.database.ensure_home_location(label=self.settings.home_label, lat=self.settings.home_lat, lon=self.settings.home_lon, timezone=self.settings.home_timezone)

    def _record_one_forecast(self, provider: str, action: Callable[[], ForecastRun], now: datetime, *, location_id: str) -> tuple[ForecastRun | None, int, str | None]:
        try:
            run, attempts = retry_read_only(action, attempts=self.retry_attempts, sleeper=self.sleeper)
            self.database.insert_forecast_run(run, location_id=location_id)
            return run, attempts, None
        except Exception as exc:
            return None, self.retry_attempts, type(exc).__name__

    def _record_forecast_locations(self, provider: str, actions: list[tuple[str, Callable[[], ForecastRun]]], now: datetime) -> ProviderOutcome:
        successes: list[tuple[str, ForecastRun, int]] = []
        failures: list[str] = []
        attempts = 0
        for location_id, action in actions:
            run, used, error = self._record_one_forecast(provider, action, now, location_id=location_id)
            attempts = max(attempts, used)
            if run is not None:
                successes.append((location_id, run, used))
            else:
                failures.append(f"{location_id}:{error}")
        if successes:
            state = "ok" if not failures else "partial"
            init_time = max(item[1].init_time_utc for item in successes)
            detail = ";".join(failures) if failures else None
            self.database.set_provider_status(provider, state=state, now=now, model_name=successes[0][1].model_name, init_time=init_time, detail=detail)
            return ProviderOutcome(provider, state, attempts, detail=detail, init_time_utc=init_time.isoformat().replace("+00:00", "Z"), locations=tuple(item[0] for item in successes))
        detail = ";".join(failures) or "no_locations_collected"
        self.database.set_provider_status(provider, state="error", now=now, detail=detail)
        return ProviderOutcome(provider, "error", attempts, detail=detail)

    def _record_observations(self, provider: str, action: Callable[[], list[Observation]], now: datetime) -> ProviderOutcome:
        try:
            observations, attempts = retry_read_only(action, attempts=self.retry_attempts, sleeper=self.sleeper)
            self.database.insert_observations(observations)
            self.database.set_provider_status(provider, state="ok", now=now, model_name="DWD Observations")
            return ProviderOutcome(provider, "ok", attempts, locations=(DWD_10416.id,))
        except Exception as exc:
            detail = type(exc).__name__
            self.database.set_provider_status(provider, state="error", now=now, detail=detail)
            return ProviderOutcome(provider, "error", self.retry_attempts, detail=detail)

    def _collect_open_meteo_model(self, model, now: datetime) -> ProviderOutcome:
        adapter = OpenMeteoSingleRunAdapter(model, fetcher=json_fetcher(self.timeout_seconds))
        try:
            metadata, meta_attempts = retry_read_only(lambda: adapter.latest_metadata(now=now), attempts=self.retry_attempts, sleeper=self.sleeper)
        except Exception as exc:
            detail = f"metadata:{type(exc).__name__}"
            self.database.set_provider_status(model.provider_id, state="error", now=now, detail=detail)
            return ProviderOutcome(model.provider_id, "error", self.retry_attempts, detail=detail)
        actions: list[tuple[str, Callable[[], ForecastRun]]] = [(DWD_10416.id, lambda a=adapter, m=metadata: a.fetch(lat=DWD_10416.lat, lon=DWD_10416.lon, init_time=m.init_time_utc, availability_time=m.availability_time_utc, retrieved_at=now))]
        if self.settings.home_configured:
            assert self.settings.home_lat is not None and self.settings.home_lon is not None
            actions.append(("home", lambda a=adapter, m=metadata: a.fetch(lat=self.settings.home_lat, lon=self.settings.home_lon, init_time=m.init_time_utc, availability_time=m.availability_time_utc, retrieved_at=now)))
        outcome = self._record_forecast_locations(model.provider_id, actions, now)
        return ProviderOutcome(outcome.provider, outcome.state, max(outcome.attempts, meta_attempts), detail=outcome.detail, init_time_utc=outcome.init_time_utc, locations=outcome.locations)

    def collect_public(self, *, now: datetime | None = None) -> dict[str, dict[str, object]]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        results: dict[str, ProviderOutcome] = {}
        with FileRunLock(self.database.lock_path):
            self._ensure_locations()
            results["dwd_mosmix_l"] = self._record_forecast_locations("dwd_mosmix_l", [(DWD_10416.id, lambda: DwdMosmixAdapter(fetcher=bytes_fetcher(self.timeout_seconds)).fetch(retrieved_at=now))], now)
            results["dwd_observations"] = self._record_observations("dwd_observations", lambda: DwdObservationAdapter(fetcher=json_fetcher(self.timeout_seconds)).fetch(now=now), now)
            for model in (ICON_D2, ECMWF_IFS, ECMWF_AIFS):
                results[model.provider_id] = self._collect_open_meteo_model(model, now)
        return {key: value.as_dict() for key, value in results.items()}

    def collect_weathernext(self, *, now: datetime | None = None, adapter: WeatherNextBigQueryAdapter | None = None) -> dict[str, object]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self._ensure_locations()
        if not self.settings.weathernext_cloud_configured:
            self.database.set_provider_status("weathernext3", state="access_pending", now=now, detail="google_project_or_linked_dataset_pending", model_name="WeatherNext 3")
            return ProviderOutcome("weathernext3", "access_pending", 0, detail="google_project_or_linked_dataset_pending").as_dict()
        assert self.settings.google_cloud_project and self.settings.weathernext_bigquery_dataset
        adapter = adapter or WeatherNextBigQueryAdapter(project=self.settings.google_cloud_project, dataset=self.settings.weathernext_bigquery_dataset)
        init_time = latest_available_init(now)
        actions: list[tuple[str, Callable[[], ForecastRun]]] = [(DWD_10416.id, lambda: adapter.fetch(lat=DWD_10416.lat, lon=DWD_10416.lon, now=now, init_time=init_time))]
        if self.settings.home_configured:
            assert self.settings.home_lat is not None and self.settings.home_lon is not None
            actions.append(("home", lambda: adapter.fetch(lat=self.settings.home_lat, lon=self.settings.home_lon, now=now, init_time=init_time)))
        return self._record_forecast_locations("weathernext3", actions, now).as_dict()
