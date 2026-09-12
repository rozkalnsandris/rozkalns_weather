from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
from statistics import mean
from typing import Iterable

from .semantics import PRECIP_EVENT_VERSION


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
    probability_source: str = "explicit_event_probability"
    event_version: str = PRECIP_EVENT_VERSION

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be in [0,1]")
        if self.observed_event not in {0.0, 1.0}:
            raise ValueError("observed_event must be 0 or 1")
        if self.probability_source not in {
            "explicit_event_probability",
            "ensemble_member_fraction",
        }:
            raise ValueError(
                "probability source must be explicit event probability or ensemble member fraction"
            )
        if self.event_version != PRECIP_EVENT_VERSION:
            raise ValueError("probability event definition is unsupported")


LEAD_BUCKETS = (
    (0, 6, "0-6h"),
    (6, 12, "6-12h"),
    (12, 24, "12-24h"),
    (24, 48, "24-48h"),
    (48, 72, "2-3d"),
    (72, 120, "3-5d"),
    (120, 168, "5-7d"),
    (168, 240, "7-10d"),
    (240, 361, "10-15d"),
)


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


def sample_evidence(n: int, *, expected_n: int | None = None) -> dict[str, object]:
    """Common sample-size metadata attached to every verification metric family."""

    sufficiency = sample_confidence(n)
    if expected_n is None:
        missingness: dict[str, object] = {
            "state": "not_assessed",
            "expected_n": None,
            "available_n": n,
            "missing_n": None,
            "missing_fraction": None,
        }
    else:
        if expected_n < n:
            raise ValueError("expected_n cannot be smaller than available n")
        missing_n = expected_n - n
        missingness = {
            "state": "assessed",
            "expected_n": expected_n,
            "available_n": n,
            "missing_n": missing_n,
            "missing_fraction": (missing_n / expected_n) if expected_n else 0.0,
        }
    return {
        "n": n,
        "sample_confidence": sufficiency,
        "sample_sufficiency_state": sufficiency,
        "missingness": missingness,
    }


def summarize(
    pairs: Iterable[ErrorPair], *, expected_n: int | None = None
) -> dict[str, object]:
    items = list(pairs)
    evidence = sample_evidence(len(items), expected_n=expected_n)
    if not items:
        return {
            **evidence,
            "mae": None,
            "rmse": None,
            "bias": None,
            "p10_p90_coverage": None,
            "coverage_n": 0,
        }
    errors = [item.forecast - item.observed for item in items]
    intervals = [item for item in items if item.p10 is not None and item.p90 is not None]
    coverage = (
        mean(1.0 if float(item.p10) <= item.observed <= float(item.p90) else 0.0 for item in intervals)
        if intervals
        else None
    )
    return {
        **evidence,
        "mae": mean(abs(error) for error in errors),
        "rmse": sqrt(mean(error * error for error in errors)),
        "bias": mean(errors),
        "p10_p90_coverage": coverage,
        "coverage_n": len(intervals),
    }


def brier_score(
    pairs: Iterable[ProbabilityPair], *, expected_n: int | None = None
) -> dict[str, object]:
    items = list(pairs)
    evidence = sample_evidence(len(items), expected_n=expected_n)
    if not items:
        return {
            **evidence,
            "brier_score": None,
        }
    score = mean((item.probability - item.observed_event) ** 2 for item in items)
    return {
        **evidence,
        "brier_score": score,
    }


def reliability_bins(
    pairs: Iterable[ProbabilityPair], *, bins: int = 10
) -> list[dict[str, float | int]]:
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
        result.append(
            {
                "bin_lower": lower,
                "bin_upper": upper,
                "n": len(items),
                "mean_probability": mean(x.probability for x in items)
                if items
                else (lower + upper) / 2,
                "observed_frequency": mean(x.observed_event for x in items)
                if items
                else 0.0,
            }
        )
    return result


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("availability timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def user_available_at(
    *,
    upstream_available_at_utc: datetime | None,
    retrieved_at_utc: datetime,
) -> datetime:
    """Earliest instant this stored forecast could have been shown by this dashboard."""
    retrieved = _as_utc(retrieved_at_utc)
    if upstream_available_at_utc is None:
        return retrieved
    upstream = _as_utc(upstream_available_at_utc)
    return max(upstream, retrieved)


def forecast_was_available(
    *,
    upstream_available_at_utc: datetime | None,
    retrieved_at_utc: datetime,
    decision_time_utc: datetime,
) -> bool:
    """Operational/user-available skill gate; run skill intentionally ignores this."""
    return user_available_at(
        upstream_available_at_utc=upstream_available_at_utc,
        retrieved_at_utc=retrieved_at_utc,
    ) <= _as_utc(decision_time_utc)
