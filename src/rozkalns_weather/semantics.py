from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

SEMANTIC_CONTRACT_VERSION = "forecast-semantic-v1"
PRECIP_EVENT_VERSION = "precip-occurrence-v1"
DEFAULT_PRECIP_EVENT_THRESHOLD_MM = 0.1

POINT_STATISTICS = frozenset({"deterministic", "mean"})
SUMMARY_QUANTILES = frozenset({"p10", "p25", "p50", "p75", "p90"})

VARIABLES: dict[str, dict[str, Any]] = {
    "temperature_2m": {"unit": "degC", "kind": "instantaneous"},
    "dew_point_2m": {"unit": "degC", "kind": "instantaneous"},
    "relative_humidity_2m": {"unit": "%", "kind": "instantaneous"},
    "pressure_msl": {"unit": "hPa", "kind": "instantaneous"},
    "wind_speed_10m": {"unit": "m/s", "kind": "instantaneous"},
    "wind_gust_10m": {"unit": "m/s", "kind": "instantaneous"},
    "cloud_cover": {"unit": "%", "kind": "instantaneous"},
    "precipitation_1h": {"unit": "mm", "kind": "accumulation", "window_minutes": 60},
    "precipitation_probability_1h": {
        "unit": "%",
        "kind": "probability",
        "window_minutes": 60,
        "event_version": PRECIP_EVENT_VERSION,
    },
}

PROVIDER_NATIVE_MAPS = {
    "dwd_mosmix_l": {"TTT": "temperature_2m", "Td": "dew_point_2m", "FF": "wind_speed_10m", "FX1": "wind_gust_10m", "PPPP": "pressure_msl", "N": "cloud_cover", "RR1c": "precipitation_1h"},
    "open_meteo": {"temperature_2m": "temperature_2m", "dew_point_2m": "dew_point_2m", "wind_speed_10m": "wind_speed_10m", "wind_gusts_10m": "wind_gust_10m", "pressure_msl": "pressure_msl", "cloud_cover": "cloud_cover", "precipitation": "precipitation_1h", "precipitation_probability": "precipitation_probability_1h"},
    "weathernext3": {"station_head_temperature_2m": "temperature_2m", "station_head_dewpoint_temperature_2m": "dew_point_2m", "wind_speed_10m": "wind_speed_10m", "mean_sea_level_pressure": "pressure_msl", "total_cloud_cover": "cloud_cover", "total_precipitation_1hr": "precipitation_1h"},
}


class SemanticGateError(ValueError):
    """A forecast value or metric slice is semantically incompatible."""


@dataclass(frozen=True, slots=True)
class SemanticIdentity:
    variable: str
    unit: str
    kind: str
    accumulation_window_minutes: int | None
    statistic: str
    statistic_family: str
    event_version: str | None = None

    @property
    def comparison_key(self) -> tuple[str, str, str, int | None, str, str | None]:
        return (
            self.variable,
            self.unit,
            self.kind,
            self.accumulation_window_minutes,
            self.statistic_family,
            self.event_version,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "contract_version": SEMANTIC_CONTRACT_VERSION,
            "variable": self.variable,
            "unit": self.unit,
            "kind": self.kind,
            "accumulation_window_minutes": self.accumulation_window_minutes,
            "statistic": self.statistic,
            "statistic_family": self.statistic_family,
            "event_version": self.event_version,
        }

    def normalized_dict(self) -> dict[str, object]:
        data = self.as_dict()
        data.pop("statistic")
        return data


def statistic_family(statistic: str) -> str:
    normalized = statistic.strip()
    if normalized == "deterministic":
        return "deterministic"
    if normalized == "mean":
        return "summary_mean"
    if normalized in SUMMARY_QUANTILES:
        return "summary_quantile"
    if normalized == "probability":
        return "event_probability"
    if normalized == "control" or normalized.startswith("member_") or (
        normalized.startswith("member") and normalized[6:].isdigit()
    ):
        return "ensemble_member"
    return "unknown"


def _allowed_families(kind: str) -> frozenset[str]:
    if kind == "probability":
        return frozenset({"event_probability"})
    return frozenset({"deterministic", "summary_mean", "summary_quantile", "ensemble_member"})


def validate_semantics(
    *,
    variable: str,
    value: float,
    unit: str,
    accumulation_window_minutes: int | None,
    statistic: str = "deterministic",
) -> list[str]:
    definition = VARIABLES.get(variable)
    if definition is None:
        return [f"unknown_variable:{variable}"]

    errors: list[str] = []
    if unit != definition["unit"]:
        errors.append(f"invalid_unit:{variable}:{unit}")

    expected_window = definition.get("window_minutes")
    if accumulation_window_minutes != expected_window:
        errors.append(f"invalid_window:{variable}:{accumulation_window_minutes}")

    family = statistic_family(statistic)
    if family == "unknown":
        errors.append(f"unknown_statistic:{variable}:{statistic}")
    elif family not in _allowed_families(str(definition["kind"])):
        errors.append(f"invalid_statistic:{variable}:{statistic}")

    if definition["kind"] == "probability" and not 0.0 <= value <= 100.0:
        errors.append(f"invalid_probability:{variable}")
    return errors


def enforce_semantics(
    *,
    variable: str,
    value: float,
    unit: str,
    accumulation_window_minutes: int | None,
    statistic: str = "deterministic",
) -> None:
    errors = validate_semantics(
        variable=variable,
        value=value,
        unit=unit,
        accumulation_window_minutes=accumulation_window_minutes,
        statistic=statistic,
    )
    if errors:
        raise SemanticGateError(";".join(errors))


def semantic_identity(
    *,
    variable: str,
    value: float,
    unit: str,
    accumulation_window_minutes: int | None,
    statistic: str = "deterministic",
) -> SemanticIdentity:
    enforce_semantics(
        variable=variable,
        value=value,
        unit=unit,
        accumulation_window_minutes=accumulation_window_minutes,
        statistic=statistic,
    )
    definition = VARIABLES[variable]
    return SemanticIdentity(
        variable=variable,
        unit=unit,
        kind=str(definition["kind"]),
        accumulation_window_minutes=accumulation_window_minutes,
        statistic=statistic,
        statistic_family=statistic_family(statistic),
        event_version=str(definition["event_version"]) if definition.get("event_version") else None,
    )


def enforce_semantic_slice(identities: Iterable[SemanticIdentity]) -> SemanticIdentity:
    items = tuple(identities)
    if not items:
        raise SemanticGateError("empty_semantic_slice")
    first = items[0]
    for item in items[1:]:
        if item.comparison_key != first.comparison_key:
            raise SemanticGateError(
                "mixed_semantic_slice:"
                f"{first.variable}/{first.unit}/{first.statistic_family}:"
                f"{item.variable}/{item.unit}/{item.statistic_family}"
            )
    return first


def metric_eligibility(identity: SemanticIdentity, *, metric: str) -> tuple[bool, str]:
    if metric in {"mae", "rmse", "bias", "event_threshold"}:
        if identity.kind != "probability" and identity.statistic_family in {"deterministic", "summary_mean"}:
            return True, "point_forecast"
        return False, "point_metric_requires_deterministic_or_mean"

    if metric in {"crps", "interval_score", "wis"}:
        if identity.kind != "probability" and identity.statistic_family == "ensemble_member":
            return True, "genuine_ensemble_members"
        return False, "probabilistic_metric_requires_ensemble_members"

    if metric in {"brier", "reliability"}:
        if identity.kind == "probability" and identity.statistic_family == "event_probability":
            return True, "explicit_event_probability"
        if identity.variable == "precipitation_1h" and identity.statistic_family == "ensemble_member":
            return True, "ensemble_member_fraction"
        return False, "brier_requires_explicit_probability_or_ensemble_member_fraction"

    return False, f"unknown_metric:{metric}"


def enforce_metric_eligibility(identity: SemanticIdentity, *, metric: str) -> str:
    eligible, reason = metric_eligibility(identity, metric=metric)
    if not eligible:
        raise SemanticGateError(f"metric_ineligible:{metric}:{reason}")
    return reason
