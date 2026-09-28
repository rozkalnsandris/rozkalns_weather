from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import parse_time, utc_iso
from .providers.base import JsonFetcher, fetch_json

BRIGHTSKY_ALERTS_URL = "https://api.brightsky.dev/alerts"
BRIGHTSKY_RADAR_URL = "https://api.brightsky.dev/radar"
RADAR_RASTER_CONTRACT_REASON = "RADAR_RASTER_CONTRACT_PENDING"
RADAR_RASTER_REQUIRED_FIELDS = [
    "encoding",
    "dimensions",
    "projection",
    "precipitation_unit",
    "nodata",
]


def _safe_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return parse_time(str(value))
    except (ValueError, TypeError):
        return None


def warning_lifecycle(alert: dict[str, Any], *, now: datetime) -> str:
    effective = _safe_time(alert.get("effective") or alert.get("onset"))
    expires = _safe_time(alert.get("expires"))
    now = now.astimezone(timezone.utc)
    if expires and expires <= now:
        return "expired"
    if effective and effective > now:
        return "upcoming"
    return "active"


def normalize_alerts(payload: dict[str, Any], *, now: datetime) -> list[dict[str, Any]]:
    result = []
    for raw in payload.get("alerts", []):
        if not isinstance(raw, dict):
            continue
        result.append(
            {
                "id": raw.get("id") or raw.get("identifier"),
                "headline": raw.get("headline") or raw.get("event"),
                "severity": str(raw.get("severity") or "unknown").lower(),
                "urgency": str(raw.get("urgency") or "unknown").lower(),
                "certainty": str(raw.get("certainty") or "unknown").lower(),
                "effective": raw.get("effective"),
                "onset": raw.get("onset"),
                "expires": raw.get("expires"),
                "lifecycle": warning_lifecycle(raw, now=now),
                "description": raw.get("description"),
                "instruction": raw.get("instruction"),
            }
        )
    return result


def radar_frame_kind(timestamp: str | None, *, now: datetime) -> str:
    if not timestamp:
        return "radar_unknown_time"
    stamp = _safe_time(timestamp)
    if stamp is None:
        return "radar_unknown_time"
    return "radar_observed" if stamp <= now.astimezone(timezone.utc) else "radar_nowcast"


def _sanitized_radar_frame(raw: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Return only privacy-safe timeline metadata from an upstream radar frame.

    Bright Sky radar frames can contain encoded precipitation grids. Those grids,
    geometry, bbox and relative center information are intentionally not part of
    the public API contract until encoding/projection/unit/nodata semantics are
    normalized and reviewed for the UI renderer.
    """

    timestamp = raw.get("timestamp") or raw.get("time")
    frame: dict[str, Any] = {
        "timestamp": str(timestamp) if timestamp else None,
        "kind": radar_frame_kind(str(timestamp) if timestamp else None, now=now),
    }
    source = raw.get("source")
    if source:
        frame["source"] = str(source)
    return frame


def fetch_dwd_alerts(
    *,
    lat: float,
    lon: float,
    fetcher: JsonFetcher = fetch_json,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    alerts = normalize_alerts(fetcher(BRIGHTSKY_ALERTS_URL, {"lat": lat, "lon": lon}), now=now)
    return {
        "authority": "DWD",
        "transport": "Bright Sky",
        "official": True,
        "kind": "official_warning",
        "state": "alerts_present" if alerts else "no_active_alerts",
        "retrieved_at_utc": utc_iso(now),
        "source_attribution": "DWD warning data via Bright Sky",
        "alerts": alerts,
        "coordinates_exposed": False,
    }


def fetch_radar_point(
    *,
    lat: float,
    lon: float,
    center_location_id: str = "home",
    fetcher: JsonFetcher = fetch_json,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = fetcher(BRIGHTSKY_RADAR_URL, {"lat": lat, "lon": lon})
    raw_frames = payload.get("radar", [])
    frames: list[dict[str, Any]] = []
    if isinstance(raw_frames, list):
        for raw in raw_frames:
            if not isinstance(raw, dict):
                continue
            frames.append(_sanitized_radar_frame(raw, now=now))

    return {
        "source": "DWD radar via Bright Sky",
        "transport": "Bright Sky",
        "not_model_forecast": True,
        "state": "frames_present" if frames else "no_radar_frames",
        "retrieved_at_utc": utc_iso(now),
        "source_attribution": "DWD radar data via Bright Sky",
        "map_contract": {
            "center_location_id": center_location_id,
            "coordinates_exposed": False,
            "geometry_exposed": False,
            "raw_payload_exposed": False,
            "allowed_kinds": ["radar_observed", "radar_nowcast"],
            "model_forecast_is_separate": True,
            "rendering_contract": {
                "state": "metadata_only",
                "raster_rendering_available": False,
                "reason_code": RADAR_RASTER_CONTRACT_REASON,
                "required_fields": RADAR_RASTER_REQUIRED_FIELDS,
            },
        },
        "frames": frames,
    }
