from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import isfinite
from typing import TYPE_CHECKING, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from .db import Database

CONDITION_CONTRACT_VERSION = "weather-condition-v1"
FALLBACK_CONTRACT_VERSION = "weather-condition-fallback-v1"
DAYLIGHT_FALLBACK_VERSION = "timezone-hour-fallback-v1"

SUPPORTED_WMO_CODES = frozenset(
    {
        0,
        1,
        2,
        3,
        45,
        48,
        51,
        53,
        55,
        56,
        57,
        61,
        63,
        65,
        66,
        67,
        71,
        73,
        75,
        77,
        80,
        81,
        82,
        85,
        86,
        95,
        96,
        97,
        99,
    }
)

STATISTIC_PRIORITY = {"deterministic": 0, "mean": 1, "p50": 2}
DRIZZLE_MIN_MM = 0.05
RAIN_MIN_MM = 0.2
HEAVY_RAIN_MIN_MM = 2.0
CONDITION_SEVERITY = {
    "unknown": 0,
    "clear": 10,
    "mostly_clear": 20,
    "partly_cloudy": 30,
    "overcast": 40,
    "fog": 50,
    "drizzle": 60,
    "rain": 70,
    "heavy_rain": 80,
    "snow": 90,
    "freezing_precipitation": 100,
    "thunderstorm": 110,
    "thunderstorm_hail": 120,
}

_WMO_CONDITIONS: dict[int, tuple[str, str]] = {
    0: ("clear", "Clear"),
    1: ("mostly_clear", "Mostly clear"),
    2: ("partly_cloudy", "Partly cloudy"),
    3: ("overcast", "Overcast"),
    45: ("fog", "Fog"),
    48: ("fog", "Rime fog"),
    51: ("drizzle", "Light drizzle"),
    53: ("drizzle", "Drizzle"),
    55: ("drizzle", "Dense drizzle"),
    56: ("freezing_precipitation", "Light freezing drizzle"),
    57: ("freezing_precipitation", "Dense freezing drizzle"),
    61: ("rain", "Light rain"),
    63: ("rain", "Rain"),
    65: ("heavy_rain", "Heavy rain"),
    66: ("freezing_precipitation", "Light freezing rain"),
    67: ("freezing_precipitation", "Heavy freezing rain"),
    71: ("snow", "Light snow"),
    73: ("snow", "Snow"),
    75: ("snow", "Heavy snow"),
    77: ("snow", "Snow grains"),
    80: ("rain", "Light rain showers"),
    81: ("rain", "Rain showers"),
    82: ("heavy_rain", "Heavy rain showers"),
    85: ("snow", "Light snow showers"),
    86: ("snow", "Heavy snow showers"),
    95: ("thunderstorm", "Thunderstorm"),
    96: ("thunderstorm_hail", "Thunderstorm with hail"),
    97: ("thunderstorm", "Heavy thunderstorm"),
    99: ("thunderstorm_hail", "Heavy thunderstorm with hail"),
}


def _number(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def condition_from_wmo(value: object | None) -> dict[str, object]:
    number = _number(value)
    if number is None or not number.is_integer():
        return {
            "condition": "unknown",
            "condition_label": "Unknown conditions",
            "weather_code": None if number is None else number,
            "condition_source": "invalid_weather_code",
        }
    code = int(number)
    mapped = _WMO_CONDITIONS.get(code)
    if mapped is None:
        return {
            "condition": "unknown",
            "condition_label": "Unknown conditions",
            "weather_code": code,
            "condition_source": "unsupported_weather_code",
        }
    condition, label = mapped
    return {
        "condition": condition,
        "condition_label": label,
        "weather_code": code,
        "condition_source": "wmo_weather_code",
    }


def fallback_condition(
    *,
    precipitation_mm: object | None,
    cloud_cover_percent: object | None,
) -> dict[str, object]:
    precipitation = _number(precipitation_mm)
    cloud_cover = _number(cloud_cover_percent)

    if precipitation is not None:
        if precipitation >= HEAVY_RAIN_MIN_MM:
            return {
                "condition": "heavy_rain",
                "condition_label": "Heavy rain",
                "weather_code": None,
                "condition_source": FALLBACK_CONTRACT_VERSION,
            }
        if precipitation >= RAIN_MIN_MM:
            return {
                "condition": "rain",
                "condition_label": "Rain",
                "weather_code": None,
                "condition_source": FALLBACK_CONTRACT_VERSION,
            }
        if precipitation >= DRIZZLE_MIN_MM:
            return {
                "condition": "drizzle",
                "condition_label": "Drizzle",
                "weather_code": None,
                "condition_source": FALLBACK_CONTRACT_VERSION,
            }

    if cloud_cover is not None and 0.0 <= cloud_cover <= 100.0:
        if cloud_cover < 20.0:
            condition, label = "clear", "Clear"
        elif cloud_cover < 45.0:
            condition, label = "mostly_clear", "Mostly clear"
        elif cloud_cover < 80.0:
            condition, label = "partly_cloudy", "Partly cloudy"
        else:
            condition, label = "overcast", "Overcast"
        return {
            "condition": condition,
            "condition_label": label,
            "weather_code": None,
            "condition_source": FALLBACK_CONTRACT_VERSION,
        }

    return {
        "condition": "unknown",
        "condition_label": "Unknown conditions",
        "weather_code": None,
        "condition_source": "insufficient_condition_evidence",
    }


def normalize_condition(
    *,
    weather_code: object | None,
    precipitation_mm: object | None,
    cloud_cover_percent: object | None,
) -> dict[str, object]:
    if weather_code is not None:
        return condition_from_wmo(weather_code)
    return fallback_condition(
        precipitation_mm=precipitation_mm,
        cloud_cover_percent=cloud_cover_percent,
    )


def daylight_state(
    *,
    is_day: object | None,
    valid_time_utc: str | None,
    timezone_name: str,
) -> dict[str, str]:
    if is_day is not None:
        number = _number(is_day)
        if number == 1.0:
            return {"daylight": "day", "daylight_source": "provider_is_day"}
        if number == 0.0:
            return {"daylight": "night", "daylight_source": "provider_is_day"}
        return {"daylight": "unknown", "daylight_source": "invalid_provider_is_day"}

    if valid_time_utc:
        try:
            stamp = datetime.fromisoformat(valid_time_utc.replace("Z", "+00:00"))
            if stamp.tzinfo is not None:
                hour = stamp.astimezone(ZoneInfo(timezone_name)).hour
                return {
                    "daylight": "day" if 7 <= hour < 19 else "night",
                    "daylight_source": DAYLIGHT_FALLBACK_VERSION,
                }
        except (ValueError, ZoneInfoNotFoundError):
            pass
    return {"daylight": "unknown", "daylight_source": "insufficient_daylight_evidence"}


def _preferred_rows(rows: Iterable[dict[str, object]]) -> dict[str, dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    for row in rows:
        rank = STATISTIC_PRIORITY.get(str(row.get("statistic") or ""))
        if rank is None:
            continue
        variable = str(row.get("variable") or "")
        current = selected.get(variable)
        if current is None:
            selected[variable] = row
            continue
        current_rank = STATISTIC_PRIORITY.get(str(current.get("statistic") or ""), 999)
        if rank < current_rank:
            selected[variable] = row
    return selected


def hourly_condition_rows(
    database: Database,
    *,
    hours: int,
    timezone_name: str,
    location_id: str,
) -> list[dict[str, object]]:
    raw_rows = database.latest_forecast_rows(
        hours=hours,
        variables=("weather_code", "is_day", "cloud_cover", "precipitation_1h"),
        location_id=location_id,
    )
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in raw_rows:
        grouped[(str(row["provider"]), str(row["valid_time_utc"]))].append(row)

    output: list[dict[str, object]] = []
    for (provider, valid_time), items in grouped.items():
        selected = _preferred_rows(items)
        anchor = (
            selected.get("weather_code")
            or selected.get("is_day")
            or selected.get("cloud_cover")
            or selected.get("precipitation_1h")
        )
        if anchor is None:
            continue
        weather_code_row = selected.get("weather_code")
        is_day_row = selected.get("is_day")
        cloud_row = selected.get("cloud_cover")
        precip_row = selected.get("precipitation_1h")
        condition = normalize_condition(
            weather_code=weather_code_row.get("value") if weather_code_row else None,
            precipitation_mm=precip_row.get("value") if precip_row else None,
            cloud_cover_percent=cloud_row.get("value") if cloud_row else None,
        )
        daylight = daylight_state(
            is_day=is_day_row.get("value") if is_day_row else None,
            valid_time_utc=valid_time,
            timezone_name=timezone_name,
        )
        output.append(
            {
                "contract": CONDITION_CONTRACT_VERSION,
                "provider": provider,
                "model_name": anchor["model_name"],
                "model_version": anchor.get("model_version"),
                "location_id": anchor["location_id"],
                "init_time_utc": anchor["init_time_utc"],
                "init_time_quality": anchor["init_time_quality"],
                "retrieved_at_utc": anchor["retrieved_at_utc"],
                "valid_time_utc": valid_time,
                "lead_hours": anchor["lead_hours"],
                **condition,
                **daylight,
                "provenance_alignment": "same_provider_latest_run_valid_time",
            }
        )
    return sorted(output, key=lambda item: (str(item["valid_time_utc"]), str(item["provider"])))


def _local_date(valid_time_utc: str, timezone_name: str) -> str | None:
    try:
        stamp = datetime.fromisoformat(valid_time_utc.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    except (ValueError, ZoneInfoNotFoundError):
        return None


def _daily_choice(rows: list[dict[str, object]]) -> dict[str, object] | None:
    if not rows:
        return None

    def key(row: dict[str, object]) -> tuple[int, int, int, int, str]:
        condition = str(row.get("condition") or "unknown")
        source = str(row.get("condition_source") or "")
        source_rank = 2 if source == "wmo_weather_code" else 1 if source == FALLBACK_CONTRACT_VERSION else 0
        daylight_rank = 1 if row.get("daylight") == "day" else 0 if row.get("daylight") == "night" else -1
        raw_code = row.get("weather_code")
        code_rank = int(raw_code) if isinstance(raw_code, int) else -1
        return (
            CONDITION_SEVERITY.get(condition, 0),
            source_rank,
            daylight_rank,
            code_rank,
            condition,
        )

    return max(rows, key=key)


def annotate_daily_conditions(
    database: Database,
    rows: list[dict[str, object]],
    *,
    days: int,
    timezone_name: str,
    location_id: str,
) -> list[dict[str, object]]:
    evidence = hourly_condition_rows(
        database,
        hours=min(360, days * 24),
        timezone_name=timezone_name,
        location_id=location_id,
    )
    by_provider_date: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for item in evidence:
        local_date = _local_date(str(item["valid_time_utc"]), timezone_name)
        if local_date:
            by_provider_date[(str(item["provider"]), local_date)].append(item)

    output: list[dict[str, object]] = []
    for row in rows:
        candidates = [
            item
            for item in by_provider_date.get((str(row["provider"]), str(row["date"])), [])
            if item.get("init_time_utc") == row.get("init_time_utc")
            and item.get("retrieved_at_utc") == row.get("retrieved_at_utc")
        ]
        choice = _daily_choice(candidates)
        augmented = dict(row)
        if choice is None:
            augmented.update(
                {
                    "condition_contract": CONDITION_CONTRACT_VERSION,
                    "condition": "unknown",
                    "condition_label": "Unknown conditions",
                    "condition_source": "insufficient_condition_evidence",
                    "weather_code": None,
                    "condition_daylight": "unknown",
                    "condition_daylight_source": "insufficient_daylight_evidence",
                    "condition_evidence_count": 0,
                }
            )
        else:
            augmented.update(
                {
                    "condition_contract": CONDITION_CONTRACT_VERSION,
                    "condition": choice["condition"],
                    "condition_label": choice["condition_label"],
                    "condition_source": f"daily_most_severe_v1:{choice['condition_source']}",
                    "weather_code": choice["weather_code"],
                    "condition_daylight": choice["daylight"],
                    "condition_daylight_source": choice["daylight_source"],
                    "condition_evidence_count": len(candidates),
                }
            )
        output.append(augmented)
    return output
