from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Final, Iterable

CYCLE_COVERAGE_REGISTRY_VERSION: Final = "forecast-cycle-coverage-v1"

UNEXPECTED_CYCLE_CLASS: Final = "UNEXPECTED_CYCLE_CLASS"
EARLY_TRUNCATION: Final = "EARLY_TRUNCATION"
UNEXPECTED_EXTRA_LEAD: Final = "UNEXPECTED_EXTRA_LEAD"
DUPLICATE_LEAD: Final = "DUPLICATE_LEAD"
HORIZON_CONTRACT_CHANGE: Final = "HORIZON_CONTRACT_CHANGE"
INVALID_LEAD: Final = "INVALID_LEAD"
NEGATIVE_LEAD: Final = "NEGATIVE_LEAD"
MISSING_CYCLE_CLASS: Final = "MISSING_CYCLE_CLASS"
INIT_CYCLE_UNOBSERVABLE: Final = "INIT_CYCLE_UNOBSERVABLE"
UNSUPPORTED_LONG_LEAD_COMPARISON: Final = "UNSUPPORTED_LONG_LEAD_COMPARISON"
UNSUPPORTED_CYCLE_COMPARISON: Final = "UNSUPPORTED_CYCLE_COMPARISON"


@dataclass(frozen=True, slots=True)
class CycleHorizonContract:
    provider_id: str
    model_role: str
    expected_cycle_hours_utc: tuple[int, ...]
    horizon_by_cycle_hours: tuple[tuple[int, int], ...]
    exact_init_cycle_observable: bool = True
    request_horizon_days_range: tuple[int, int] | None = None
    unobservable_reason: str | None = None

    def __post_init__(self) -> None:
        if len(set(self.expected_cycle_hours_utc)) != len(self.expected_cycle_hours_utc):
            raise ValueError("cycle hours must be unique")
        if any(hour < 0 or hour > 23 for hour in self.expected_cycle_hours_utc):
            raise ValueError("cycle hours must be in 0..23 UTC")
        horizon_map = dict(self.horizon_by_cycle_hours)
        if self.exact_init_cycle_observable:
            if set(horizon_map) != set(self.expected_cycle_hours_utc):
                raise ValueError("exact-init contracts require one horizon per cycle")
            if any(hours <= 0 for hours in horizon_map.values()):
                raise ValueError("forecast horizons must be positive")
        elif self.expected_cycle_hours_utc or horizon_map:
            raise ValueError("unobservable cycle contracts must not fabricate cycle hours")
        if self.request_horizon_days_range is not None:
            lower, upper = self.request_horizon_days_range
            if lower <= 0 or upper < lower:
                raise ValueError("request horizon day range is invalid")

    def horizon_for_cycle(self, hour: int) -> int:
        if not self.exact_init_cycle_observable:
            raise ValueError(INIT_CYCLE_UNOBSERVABLE)
        try:
            return dict(self.horizon_by_cycle_hours)[hour]
        except KeyError as exc:
            raise ValueError(UNEXPECTED_CYCLE_CLASS) from exc

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider_id": self.provider_id,
            "model_role": self.model_role,
            "exact_init_cycle_observable": self.exact_init_cycle_observable,
            "expected_cycle_hours_utc": list(self.expected_cycle_hours_utc),
            "horizon_by_cycle_hours": {
                f"{hour:02d}": horizon for hour, horizon in self.horizon_by_cycle_hours
            },
            "model_version_boundary_policy": "registry-version-and-source-model-version",
        }
        if self.request_horizon_days_range is not None:
            payload["request_horizon_days_range"] = list(self.request_horizon_days_range)
        if self.unobservable_reason is not None:
            payload["unobservable_reason"] = self.unobservable_reason
        return payload


def _deterministic(
    provider_id: str,
    role: str,
    horizons: dict[int, int],
) -> CycleHorizonContract:
    return CycleHorizonContract(
        provider_id=provider_id,
        model_role=role,
        expected_cycle_hours_utc=tuple(sorted(horizons)),
        horizon_by_cycle_hours=tuple(sorted(horizons.items())),
    )


def _unobservable_ensemble(provider_id: str, role: str = "ensemble") -> CycleHorizonContract:
    return CycleHorizonContract(
        provider_id=provider_id,
        model_role=role,
        expected_cycle_hours_utc=(),
        horizon_by_cycle_hours=(),
        exact_init_cycle_observable=False,
        request_horizon_days_range=(1, 16),
        unobservable_reason="OPEN_METEO_ENSEMBLE_INIT_CYCLE_UNEXPOSED",
    )


_WEATHERNEXT_HORIZONS = {
    hour: (360 if hour in {0, 6, 12, 18} else 48)
    for hour in range(24)
}

CYCLE_HORIZON_REGISTRY: Final = {
    "icon_d2": _deterministic("icon_d2", "deterministic", {0: 48, 6: 48, 12: 48, 18: 48}),
    "ecmwf_ifs": _deterministic("ecmwf_ifs", "deterministic", {0: 240, 6: 144, 12: 240, 18: 144}),
    "ecmwf_aifs": _deterministic("ecmwf_aifs", "deterministic", {0: 360, 6: 360, 12: 360, 18: 360}),
    "weathernext3": _deterministic("weathernext3", "probabilistic_summary", _WEATHERNEXT_HORIZONS),
    "icon_d2_eps": _unobservable_ensemble("icon_d2_eps"),
    "ecmwf_ifs_ens": _unobservable_ensemble("ecmwf_ifs_ens"),
    "ecmwf_aifs_ens": _unobservable_ensemble("ecmwf_aifs_ens"),
    "weathernext2_legacy": _unobservable_ensemble("weathernext2_legacy", "legacy_ai_context_ensemble"),
}


def contract_for(provider_id: str) -> CycleHorizonContract:
    try:
        return CYCLE_HORIZON_REGISTRY[provider_id]
    except KeyError as exc:
        raise ValueError(f"unsupported_cycle_coverage_provider:{provider_id}") from exc


def registry_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "registry_version": CYCLE_COVERAGE_REGISTRY_VERSION,
        "contracts": [contract.as_dict() for contract in CYCLE_HORIZON_REGISTRY.values()],
    }


def _parse_init(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("init time must be timezone-aware")
        return value.astimezone(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("init time must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def evaluate_run_coverage(
    provider_id: str,
    *,
    init_time: datetime | str,
    lead_hours: Iterable[float],
    model_version: str | None = None,
    declared_horizon_hours: int | None = None,
    tolerance_hours: float = 1e-6,
) -> dict[str, object]:
    contract = contract_for(provider_id)
    init = _parse_init(init_time)
    if not contract.exact_init_cycle_observable:
        return {
            "state": "UNOBSERVABLE",
            "reason_codes": [INIT_CYCLE_UNOBSERVABLE],
            "registry_version": CYCLE_COVERAGE_REGISTRY_VERSION,
            "provider_id": provider_id,
            "model_version": model_version,
            "init_time_utc": init.isoformat().replace("+00:00", "Z"),
            "contract": contract.as_dict(),
        }

    reasons: list[str] = []
    if init.hour not in contract.expected_cycle_hours_utc:
        reasons.append(UNEXPECTED_CYCLE_CLASS)
        expected_horizon: int | None = None
    else:
        expected_horizon = contract.horizon_for_cycle(init.hour)

    leads: list[float] = []
    invalid = False
    for raw in lead_hours:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            invalid = True
            continue
        if not isfinite(value):
            invalid = True
            continue
        leads.append(value)
    if invalid:
        reasons.append(INVALID_LEAD)
    if any(value < 0 for value in leads):
        reasons.append(NEGATIVE_LEAD)
    counts = Counter(leads)
    if any(count > 1 for count in counts.values()):
        reasons.append(DUPLICATE_LEAD)

    if expected_horizon is not None:
        if declared_horizon_hours is not None and declared_horizon_hours != expected_horizon:
            reasons.append(HORIZON_CONTRACT_CHANGE)
        nonnegative = [value for value in leads if value >= 0]
        if not nonnegative or max(nonnegative) < expected_horizon - tolerance_hours:
            reasons.append(EARLY_TRUNCATION)
        if nonnegative and max(nonnegative) > expected_horizon + tolerance_hours:
            reasons.append(UNEXPECTED_EXTRA_LEAD)

    reasons = list(dict.fromkeys(reasons))
    return {
        "state": "BLOCKED" if reasons else "PASS",
        "reason_codes": reasons,
        "registry_version": CYCLE_COVERAGE_REGISTRY_VERSION,
        "provider_id": provider_id,
        "model_version": model_version,
        "init_time_utc": init.isoformat().replace("+00:00", "Z"),
        "cycle_hour_utc": init.hour,
        "expected_horizon_hours": expected_horizon,
        "declared_horizon_hours": declared_horizon_hours,
        "observed_max_lead_hours": max(leads) if leads else None,
        "observed_unique_lead_count": len(counts),
        "contract": contract.as_dict(),
    }


def cycle_class_coverage(
    provider_id: str,
    init_times: Iterable[datetime | str],
) -> dict[str, object]:
    contract = contract_for(provider_id)
    if not contract.exact_init_cycle_observable:
        return {
            "state": "UNOBSERVABLE",
            "reason_codes": [INIT_CYCLE_UNOBSERVABLE],
            "registry_version": CYCLE_COVERAGE_REGISTRY_VERSION,
            "provider_id": provider_id,
            "expected_cycle_hours_utc": [],
            "present_cycle_hours_utc": [],
            "missing_cycle_hours_utc": [],
        }
    present = sorted({_parse_init(value).hour for value in init_times})
    missing = sorted(set(contract.expected_cycle_hours_utc) - set(present))
    return {
        "state": "BLOCKED" if missing else "PASS",
        "reason_codes": [MISSING_CYCLE_CLASS] if missing else [],
        "registry_version": CYCLE_COVERAGE_REGISTRY_VERSION,
        "provider_id": provider_id,
        "expected_cycle_hours_utc": list(contract.expected_cycle_hours_utc),
        "present_cycle_hours_utc": present,
        "missing_cycle_hours_utc": missing,
    }


def comparison_lead_intersection(
    provider_ids: Iterable[str],
    *,
    init_hour_utc: int,
    requested_max_lead_hours: float | None = None,
) -> dict[str, object]:
    providers = tuple(provider_ids)
    if not providers:
        raise ValueError("at least one provider is required")
    if init_hour_utc < 0 or init_hour_utc > 23:
        raise ValueError("init hour must be in 0..23 UTC")
    horizons: dict[str, int] = {}
    reasons: list[str] = []
    for provider_id in providers:
        contract = contract_for(provider_id)
        if not contract.exact_init_cycle_observable:
            reasons.append(INIT_CYCLE_UNOBSERVABLE)
            continue
        if init_hour_utc not in contract.expected_cycle_hours_utc:
            reasons.append(UNSUPPORTED_CYCLE_COMPARISON)
            continue
        horizons[provider_id] = contract.horizon_for_cycle(init_hour_utc)
    common_horizon = min(horizons.values()) if len(horizons) == len(providers) else None
    if requested_max_lead_hours is not None:
        if requested_max_lead_hours < 0:
            raise ValueError("requested max lead must be non-negative")
        if common_horizon is not None and requested_max_lead_hours > common_horizon:
            reasons.append(UNSUPPORTED_LONG_LEAD_COMPARISON)
    reasons = list(dict.fromkeys(reasons))
    return {
        "state": "BLOCKED" if reasons else "PASS",
        "reason_codes": reasons,
        "registry_version": CYCLE_COVERAGE_REGISTRY_VERSION,
        "providers": list(providers),
        "init_hour_utc": init_hour_utc,
        "provider_horizon_hours": horizons,
        "common_max_lead_hours": common_horizon,
        "requested_max_lead_hours": requested_max_lead_hours,
    }
