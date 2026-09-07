from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ErrorPair:
    provider: str
    model_version: str | None
    lead_hours: float
    forecast: float
    observed: float
    p10: float | None = None
    p90: float | None = None


@dataclass(frozen=True, slots=True)
class ProbabilityPair:
    provider: str
    lead_hours: float
    probability: float
    observed_event: float
    model_version: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be in [0,1]")
        if self.observed_event not in {0.0, 1.0}:
            raise ValueError("observed_event must be 0 or 1")


LEAD_BUCKETS = ((0, 6, "0-6h"), (6, 12, "6-12h"), (12, 24, "12-24h"), (24, 48, "24-48h"), (48, 72, "2-3d"), (72, 120, "3-5d"), (120, 168, "5-7d"), (168, 240, "7-10d"), (240, 361, "10-15d"))


def lead_bucket(hours: float) -> str:
    for lower, upper, label in LEAD_BUCKETS:
        if lower <= hours < upper:
            return label
    return "out-of-range"


def sample_confidence(n: int) -> str:
    if n < 30:
        return "insufficient_sample"
    if n < 100:
        return "limited_sample"
    return "usable_sample"


def summarize(pairs: Iterable[ErrorPair]) -> dict[str, float | int | str | None]:
    items = list(pairs)
    if not items:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "p10_p90_coverage": None, "sample_confidence": sample_confidence(0)}
    errors = [item.forecast - item.observed for item in items]
    intervals = [item for item in items if item.p10 is not None and item.p90 is not None]
    coverage = mean(1.0 if item.p10 <= item.observed <= item.p90 else 0.0 for item in intervals) if intervals else None
    return {"n": len(items), "mae": mean(abs(error) for error in errors), "rmse": sqrt(mean(error * error for error in errors)), "bias": mean(errors), "p10_p90_coverage": coverage, "sample_confidence": sample_confidence(len(items))}


def brier_score(pairs: Iterable[ProbabilityPair]) -> dict[str, float | int | str | None]:
    items = list(pairs)
    if not items:
        return {"n": 0, "brier_score": None, "sample_confidence": sample_confidence(0)}
    score = mean((item.probability - item.observed_event) ** 2 for item in items)
    return {"n": len(items), "brier_score": score, "sample_confidence": sample_confidence(len(items))}


def reliability_bins(pairs: Iterable[ProbabilityPair], *, bins: int = 10) -> list[dict[str, float | int]]:
    if bins < 2:
        raise ValueError("bins must be >= 2")
    buckets: list[list[ProbabilityPair]] = [[] for _ in range(bins)]
    for item in pairs:
        index = min(bins - 1, int(item.probability * bins))
        buckets[index].append(item)
    result: list[dict[str, float | int]] = []
    for index, items in enumerate(buckets):
        lower = index / bins
        upper = (index + 1) / bins
        result.append({"bin_lower": lower, "bin_upper": upper, "n": len(items), "mean_probability": mean(x.probability for x in items) if items else (lower + upper) / 2, "observed_frequency": mean(x.observed_event for x in items) if items else 0.0})
    return result
