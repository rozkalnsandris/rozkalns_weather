from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class EnsembleVerificationPair:
    provider: str
    lead_hours: float
    members: tuple[float, ...]
    observed: float
    model_version: str | None = None

    def __post_init__(self) -> None:
        if not self.members:
            raise ValueError("ensemble members must not be empty")
        if not all(isfinite(value) for value in self.members + (self.observed,)):
            raise ValueError("ensemble verification inputs must be finite")


def ensemble_crps(members: Sequence[float], observed: float) -> float:
    values = tuple(float(value) for value in members)
    if not values:
        raise ValueError("members must not be empty")
    first = mean(abs(value - observed) for value in values)
    pairwise = mean(abs(left - right) for left in values for right in values)
    return first - 0.5 * pairwise


def summarize_crps(pairs: Iterable[EnsembleVerificationPair]) -> dict[str, float | int | None]:
    items = list(pairs)
    if not items:
        return {"n": 0, "mean_crps": None}
    return {"n": len(items), "mean_crps": mean(ensemble_crps(item.members, item.observed) for item in items)}


def empirical_quantile(members: Sequence[float], probability: float) -> float:
    if not 0 <= probability <= 1:
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
    return values[lower] * (1 - fraction) + values[upper] * fraction


def interval_score(members: Sequence[float], observed: float, *, alpha: float = 0.2) -> dict[str, float]:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0,1)")
    lower = empirical_quantile(members, alpha / 2)
    upper = empirical_quantile(members, 1 - alpha / 2)
    width = upper - lower
    penalty = 0.0
    if observed < lower:
        penalty = (2 / alpha) * (lower - observed)
    elif observed > upper:
        penalty = (2 / alpha) * (observed - upper)
    return {
        "lower": lower,
        "upper": upper,
        "width": width,
        "covered": 1.0 if lower <= observed <= upper else 0.0,
        "interval_score": width + penalty,
    }


def weighted_interval_score(
    members: Sequence[float],
    observed: float,
    *,
    alphas: Sequence[float] = (0.1, 0.2, 0.4),
) -> float:
    if not alphas:
        raise ValueError("at least one alpha is required")
    median = empirical_quantile(members, 0.5)
    weighted = 0.5 * abs(observed - median)
    total_weight = 0.5
    for alpha in alphas:
        score = interval_score(members, observed, alpha=alpha)["interval_score"]
        weight = alpha / 2
        weighted += weight * score
        total_weight += weight
    return weighted / total_weight


def event_probability(members: Sequence[float], *, threshold: float = 0.1) -> float:
    values = tuple(float(value) for value in members)
    if not values:
        raise ValueError("members must not be empty")
    return mean(1.0 if value >= threshold else 0.0 for value in values)


def brier_from_members(
    member_sets: Iterable[Sequence[float]],
    observations: Iterable[float],
    *,
    threshold: float = 0.1,
) -> dict[str, float | int | None]:
    pairs = list(zip(member_sets, observations, strict=True))
    if not pairs:
        return {"n": 0, "brier_score": None, "threshold": threshold}
    errors = []
    for members, observed in pairs:
        probability = event_probability(members, threshold=threshold)
        event = 1.0 if float(observed) >= threshold else 0.0
        errors.append((probability - event) ** 2)
    return {"n": len(errors), "brier_score": mean(errors), "threshold": threshold}


def reliability_from_members(
    member_sets: Iterable[Sequence[float]],
    observations: Iterable[float],
    *,
    threshold: float = 0.1,
    bins: int = 10,
) -> list[dict[str, float | int]]:
    if bins < 2:
        raise ValueError("bins must be >= 2")
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for members, observed in zip(member_sets, observations, strict=True):
        probability = event_probability(members, threshold=threshold)
        event = 1.0 if float(observed) >= threshold else 0.0
        index = min(bins - 1, int(probability * bins))
        buckets[index].append((probability, event))
    output: list[dict[str, float | int]] = []
    for index, items in enumerate(buckets):
        lower = index / bins
        upper = (index + 1) / bins
        output.append(
            {
                "bin_lower": lower,
                "bin_upper": upper,
                "n": len(items),
                "mean_probability": mean(item[0] for item in items) if items else (lower + upper) / 2,
                "observed_frequency": mean(item[1] for item in items) if items else 0.0,
            }
        )
    return output
