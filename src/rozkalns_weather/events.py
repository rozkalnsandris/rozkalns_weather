from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(frozen=True, slots=True)
class EventPair:
    provider: str
    variable: str
    lead_hours: float
    forecast: float
    observed: float
    threshold: float
    direction: str = "at_or_above"
    model_version: str | None = None

    def __post_init__(self) -> None:
        if self.direction not in {"at_or_above", "at_or_below"}:
            raise ValueError("direction must be at_or_above or at_or_below")

    def forecast_event(self) -> bool:
        return self.forecast >= self.threshold if self.direction == "at_or_above" else self.forecast <= self.threshold

    def observed_event(self) -> bool:
        return self.observed >= self.threshold if self.direction == "at_or_above" else self.observed <= self.threshold


def summarize_events(pairs: Iterable[EventPair]) -> dict[str, float | int | str | None]:
    items = list(pairs)
    if not items:
        return {
            "n": 0,
            "hits": 0,
            "misses": 0,
            "false_alarms": 0,
            "correct_negatives": 0,
            "hit_rate": None,
            "false_alarm_ratio": None,
            "critical_success_index": None,
        }
    hits = misses = false_alarms = correct_negatives = 0
    for item in items:
        forecast = item.forecast_event()
        observed = item.observed_event()
        if forecast and observed:
            hits += 1
        elif not forecast and observed:
            misses += 1
        elif forecast and not observed:
            false_alarms += 1
        else:
            correct_negatives += 1
    hit_rate = hits / (hits + misses) if hits + misses else None
    false_alarm_ratio = false_alarms / (hits + false_alarms) if hits + false_alarms else None
    csi = hits / (hits + misses + false_alarms) if hits + misses + false_alarms else None
    return {
        "n": len(items),
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "correct_negatives": correct_negatives,
        "hit_rate": hit_rate,
        "false_alarm_ratio": false_alarm_ratio,
        "critical_success_index": csi,
    }


def matched_event_groups(pairs: Iterable[EventPair]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, float, str, str], list[EventPair]] = {}
    for item in pairs:
        key = (
            item.provider,
            item.model_version or "unknown",
            item.threshold,
            item.direction,
            item.variable,
        )
        grouped.setdefault(key, []).append(item)
    output = []
    for (provider, version, threshold, direction, variable), items in sorted(grouped.items()):
        output.append(
            {
                "provider": provider,
                "model_version": version,
                "variable": variable,
                "threshold": threshold,
                "direction": direction,
                "mean_lead_hours": mean(item.lead_hours for item in items),
                **summarize_events(items),
            }
        )
    return output
