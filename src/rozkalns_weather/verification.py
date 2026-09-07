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


LEAD_BUCKETS = ((0, 6, "0-6h"), (6, 12, "6-12h"), (12, 24, "12-24h"), (24, 48, "24-48h"), (48, 72, "2-3d"), (72, 120, "3-5d"), (120, 168, "5-7d"), (168, 240, "7-10d"), (240, 361, "10-15d"))


def lead_bucket(hours: float) -> str:
    for lower, upper, label in LEAD_BUCKETS:
        if lower <= hours < upper:
            return label
    return "out-of-range"


def summarize(pairs: Iterable[ErrorPair]) -> dict[str, float | int | None]:
    items = list(pairs)
    if not items:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "p10_p90_coverage": None}
    errors = [item.forecast - item.observed for item in items]
    intervals = [item for item in items if item.p10 is not None and item.p90 is not None]
    coverage = None
    if intervals:
        coverage = mean(1.0 if item.p10 <= item.observed <= item.p90 else 0.0 for item in intervals)
    return {"n": len(items), "mae": mean(abs(error) for error in errors), "rmse": sqrt(mean(error * error for error in errors)), "bias": mean(errors), "p10_p90_coverage": coverage}
