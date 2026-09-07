from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from random import Random
from statistics import mean
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class EnsembleSample:
    provider: str
    model_version: str | None
    lead_hours: float
    members: tuple[float, ...]
    observed: float

    def __post_init__(self) -> None:
        if not self.members:
            raise ValueError("ensemble sample requires at least one member")
        if not all(isfinite(value) for value in self.members):
            raise ValueError("ensemble members must be finite")


def crps_ensemble(members: Sequence[float], observed: float) -> float:
    """Finite-ensemble CRPS: E|X-y| - 0.5 E|X-X'|."""
    values = tuple(float(value) for value in members)
    if not values:
        raise ValueError("members must not be empty")
    first = mean(abs(value - observed) for value in values)
    second = sum(abs(a - b) for a in values for b in values) / (2.0 * len(values) ** 2)
    return first - second


def empirical_quantile(members: Sequence[float], probability: float) -> float:
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0,1]")
    values = sorted(float(value) for value in members)
    if not values:
        raise ValueError("members must not be empty")
    if len(values) == 1:
        return values[0]
    position = probability * (len(values) - 1)
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def central_interval(members: Sequence[float], *, coverage: float = 0.8) -> tuple[float, float]:
    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be between 0 and 1")
    alpha = (1.0 - coverage) / 2.0
    return empirical_quantile(members, alpha), empirical_quantile(members, 1.0 - alpha)


def interval_score(lower: float, upper: float, observed: float, *, alpha: float = 0.2) -> float:
    if lower > upper:
        raise ValueError("lower must not exceed upper")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1")
    penalty = 0.0
    if observed < lower:
        penalty = (2.0 / alpha) * (lower - observed)
    elif observed > upper:
        penalty = (2.0 / alpha) * (observed - upper)
    return (upper - lower) + penalty


def wis_from_members(members: Sequence[float], observed: float) -> dict[str, float]:
    p10 = empirical_quantile(members, 0.10)
    p25 = empirical_quantile(members, 0.25)
    p50 = empirical_quantile(members, 0.50)
    p75 = empirical_quantile(members, 0.75)
    p90 = empirical_quantile(members, 0.90)
    score80 = interval_score(p10, p90, observed, alpha=0.20)
    score50 = interval_score(p25, p75, observed, alpha=0.50)
    wis = (abs(p50 - observed) + 0.25 * score50 + 0.10 * score80) / 1.35
    return {
        "wis": wis,
        "p10": p10,
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "p90": p90,
        "coverage_50": 1.0 if p25 <= observed <= p75 else 0.0,
        "coverage_80": 1.0 if p10 <= observed <= p90 else 0.0,
        "width_50": p75 - p25,
        "width_80": p90 - p10,
    }


def event_probability(members: Sequence[float], *, threshold: float) -> float:
    values = tuple(float(value) for value in members)
    if not values:
        raise ValueError("members must not be empty")
    return sum(1 for value in values if value >= threshold) / len(values)


def bootstrap_mean_ci(
    values: Iterable[float], *, confidence: float = 0.95, min_samples: int = 30, resamples: int = 1000, seed: int = 7
) -> dict[str, float | int | str | None]:
    samples = [float(value) for value in values]
    if len(samples) < min_samples:
        return {"n": len(samples), "mean": mean(samples) if samples else None, "lower": None, "upper": None, "state": "insufficient_sample"}
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if resamples < 100:
        raise ValueError("resamples must be >= 100")
    random = Random(seed)
    boot = sorted(mean(random.choice(samples) for _ in samples) for _ in range(resamples))
    tail = (1.0 - confidence) / 2.0
    lower_index = max(0, min(resamples - 1, int(tail * resamples)))
    upper_index = max(0, min(resamples - 1, int((1.0 - tail) * resamples) - 1))
    return {"n": len(samples), "mean": mean(samples), "lower": boot[lower_index], "upper": boot[upper_index], "state": "ready"}
