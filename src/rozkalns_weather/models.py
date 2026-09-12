from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .physical_consistency import enforce_forecast_run_physical_consistency
from .semantics import SemanticIdentity, semantic_identity as build_semantic_identity


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def utc_iso(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return ensure_utc(parsed)


@dataclass(frozen=True, slots=True)
class ForecastValue:
    valid_time_utc: datetime
    lead_hours: float
    variable: str
    value: float
    unit: str
    statistic: str = "deterministic"
    native_value: float | None = None
    native_unit: str | None = None
    accumulation_window_minutes: int | None = None
    quality_status: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "valid_time_utc", ensure_utc(self.valid_time_utc))
        if self.lead_hours < 0:
            raise ValueError("lead_hours must be >= 0")
        build_semantic_identity(
            variable=self.variable,
            value=self.value,
            unit=self.unit,
            accumulation_window_minutes=self.accumulation_window_minutes,
            statistic=self.statistic,
        )

    @property
    def semantic_identity(self) -> SemanticIdentity:
        return build_semantic_identity(
            variable=self.variable,
            value=self.value,
            unit=self.unit,
            accumulation_window_minutes=self.accumulation_window_minutes,
            statistic=self.statistic,
        )


@dataclass(frozen=True, slots=True)
class ForecastRun:
    provider: str
    model_provider: str
    model_name: str
    init_time_utc: datetime
    retrieved_at_utc: datetime
    source_surface: str
    values: tuple[ForecastValue, ...]
    model_version: str | None = None
    transport_provider: str | None = None
    raw_payload_hash: str | None = None
    status: str = "ok"
    source_metadata: dict[str, Any] = field(default_factory=dict)
    init_time_quality: str = "provider_native"
    upstream_available_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "init_time_utc", ensure_utc(self.init_time_utc))
        object.__setattr__(self, "retrieved_at_utc", ensure_utc(self.retrieved_at_utc))
        if self.upstream_available_at_utc is not None:
            object.__setattr__(
                self,
                "upstream_available_at_utc",
                ensure_utc(self.upstream_available_at_utc),
            )

        report = enforce_forecast_run_physical_consistency(self)
        metadata = dict(self.source_metadata)
        metadata["physical_consistency"] = report.to_metadata()
        object.__setattr__(self, "source_metadata", metadata)


@dataclass(frozen=True, slots=True)
class Observation:
    source_provider: str
    observed_at_utc: datetime
    variable: str
    value: float
    unit: str
    station_id: str | None = None
    location_id: str | None = None
    quality_status: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at_utc", ensure_utc(self.observed_at_utc))
