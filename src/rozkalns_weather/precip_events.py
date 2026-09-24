from __future__ import annotations

from dataclasses import dataclass
from typing import Final

PRECIP_EVENT_REGISTRY_VERSION: Final = "precip-event-registry-v1"
PRECIP_OCCURRENCE_1H_EVENT_ID: Final = "precipitation_1h_ge_0p1mm"


@dataclass(frozen=True, slots=True)
class PrecipEventDefinition:
    event_id: str
    amount_variable: str
    probability_variable: str
    threshold: float
    threshold_unit: str
    accumulation_window_minutes: int
    direction: str
    probability_sources: tuple[str, ...]
    registry_version: str = PRECIP_EVENT_REGISTRY_VERSION

    def __post_init__(self) -> None:
        if self.direction != "at_or_above":
            raise ValueError("unsupported precipitation event direction")
        if self.threshold < 0:
            raise ValueError("precipitation event threshold must be non-negative")
        if self.accumulation_window_minutes <= 0:
            raise ValueError("precipitation event accumulation window must be positive")
        if not self.probability_sources:
            raise ValueError("precipitation event probability sources must not be empty")

    def as_dict(self) -> dict[str, object]:
        return {
            "registry_version": self.registry_version,
            "event_id": self.event_id,
            "amount_variable": self.amount_variable,
            "probability_variable": self.probability_variable,
            "threshold": self.threshold,
            "threshold_unit": self.threshold_unit,
            "accumulation_window_minutes": self.accumulation_window_minutes,
            "direction": self.direction,
            "probability_sources": list(self.probability_sources),
            "deterministic_amount_probability_eligible": False,
            "summary_quantile_probability_eligible": False,
        }

    def validate_amount_identity(
        self,
        *,
        variable: str,
        unit: str,
        accumulation_window_minutes: int | None,
    ) -> None:
        if variable != self.amount_variable:
            raise ValueError(f"precip_event_variable_mismatch:{variable}")
        if unit != self.threshold_unit:
            raise ValueError(f"precip_event_unit_mismatch:{unit}")
        if accumulation_window_minutes != self.accumulation_window_minutes:
            raise ValueError(
                "precip_event_window_mismatch:"
                f"{accumulation_window_minutes}:{self.accumulation_window_minutes}"
            )

    def event_occurs(
        self,
        value: float,
        *,
        variable: str | None = None,
        unit: str | None = None,
        accumulation_window_minutes: int | None = None,
    ) -> bool:
        self.validate_amount_identity(
            variable=variable or self.amount_variable,
            unit=unit or self.threshold_unit,
            accumulation_window_minutes=(
                self.accumulation_window_minutes
                if accumulation_window_minutes is None
                else accumulation_window_minutes
            ),
        )
        return float(value) >= self.threshold

    def validate_probability_source(self, source: str) -> str:
        if source not in self.probability_sources:
            raise ValueError(
                "probability source must be explicit event probability or ensemble member fraction"
            )
        return source


DEFAULT_PRECIP_EVENT = PrecipEventDefinition(
    event_id=PRECIP_OCCURRENCE_1H_EVENT_ID,
    amount_variable="precipitation_1h",
    probability_variable="precipitation_probability_1h",
    threshold=0.1,
    threshold_unit="mm",
    accumulation_window_minutes=60,
    direction="at_or_above",
    probability_sources=(
        "explicit_event_probability",
        "ensemble_member_fraction",
    ),
)

PRECIP_EVENT_REGISTRY: Final = {
    DEFAULT_PRECIP_EVENT.event_id: DEFAULT_PRECIP_EVENT,
}


def event_definition(event_id: str = PRECIP_OCCURRENCE_1H_EVENT_ID) -> PrecipEventDefinition:
    try:
        return PRECIP_EVENT_REGISTRY[event_id]
    except KeyError as exc:
        raise ValueError(f"unsupported_precip_event_definition:{event_id}") from exc


def registry_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "registry_version": PRECIP_EVENT_REGISTRY_VERSION,
        "events": [
            PRECIP_EVENT_REGISTRY[event_id].as_dict()
            for event_id in sorted(PRECIP_EVENT_REGISTRY)
        ],
    }
