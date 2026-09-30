from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .models import parse_time, utc_iso
from .providers.base import JsonFetcher, fetch_json

BRIGHTSKY_ALERTS_URL = "https://api.brightsky.dev/alerts"
BRIGHTSKY_RADAR_URL = "https://api.brightsky.dev/radar"
RADAR_RENDER_DISTANCE_M = 20_000
RADAR_GRID_CELL_M = 1_000
RADAR_PRECIPITATION_SCALE_MM_PER_5_MIN = 0.01
RADAR_PROJECTION_ID = "DWD_RADOLAN_DE1200"
RADAR_RASTER_INVALID_REASON = "RADAR_RASTER_VALIDATION_FAILED"
RADAR_RASTER_EMPTY_REASON = "RADAR_NO_RENDERABLE_FRAMES"


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


def _plain_radar_grid(value: Any) -> list[list[int]] | None:
    if not isinstance(value, list) or not value:
        return None
    rows: list[list[int]] = []
    width: int | None = None
    for raw_row in value:
        if not isinstance(raw_row, list) or not raw_row:
            return None
        if width is None:
            width = len(raw_row)
        elif len(raw_row) != width:
            return None
        row: list[int] = []
        for raw_cell in raw_row:
            if isinstance(raw_cell, bool) or not isinstance(raw_cell, int):
                return None
            if raw_cell < 0 or raw_cell > 32767:
                return None
            row.append(raw_cell)
        rows.append(row)
    return rows


def _sanitized_radar_frame(raw: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Normalize one Bright Sky frame without exposing geometry or coordinates."""

    timestamp = raw.get("timestamp") or raw.get("time")
    kind = radar_frame_kind(str(timestamp) if timestamp else None, now=now)
    frame: dict[str, Any] = {
        "timestamp": str(timestamp) if timestamp else None,
        "kind": kind,
    }
    source = raw.get("source")
    if source:
        frame["source"] = str(source)

    grid = _plain_radar_grid(raw.get("precipitation_5"))
    if grid is not None and kind in {"radar_observed", "radar_nowcast"}:
        frame["raster"] = {
            "width": len(grid[0]),
            "height": len(grid),
            "values": grid,
        }
    return frame


def _radar_rendering_contract(frames: list[dict[str, Any]]) -> dict[str, Any]:
    raster_frames = [frame for frame in frames if isinstance(frame.get("raster"), dict)]
    if not raster_frames:
        return {
            "state": "unavailable",
            "raster_rendering_available": False,
            "reason_code": RADAR_RASTER_EMPTY_REASON,
        }

    dimensions = {
        (int(frame["raster"]["width"]), int(frame["raster"]["height"]))
        for frame in raster_frames
    }
    if len(dimensions) != 1:
        for frame in frames:
            frame.pop("raster", None)
        return {
            "state": "unavailable",
            "raster_rendering_available": False,
            "reason_code": RADAR_RASTER_INVALID_REASON,
        }

    width, height = dimensions.pop()
    return {
        "state": "raster_ready",
        "raster_rendering_available": True,
        "encoding": "plain_integer_grid",
        "dimensions": {"width": width, "height": height},
        "projection": {
            "id": RADAR_PROJECTION_ID,
            "kind": "polar_stereographic",
            "pixel_size_m": RADAR_GRID_CELL_M,
            "web_mercator_overlay_safe": False,
        },
        "precipitation_unit": {
            "field": "precipitation_5",
            "unit": "mm_per_5_min",
            "scale": RADAR_PRECIPITATION_SCALE_MM_PER_5_MIN,
        },
        "nodata": {
            "sentinel": None,
            "zero_may_include_uncovered_grid_edge": True,
        },
        "crop_radius_m": RADAR_RENDER_DISTANCE_M,
        "center_marker": "privacy_safe_crop_center",
        "raster_frame_count": len(raster_frames),
        "timeline_frame_count": len(frames),
    }


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
    payload = fetcher(
        BRIGHTSKY_RADAR_URL,
        {
            "lat": lat,
            "lon": lon,
            "distance": RADAR_RENDER_DISTANCE_M,
            "format": "plain",
            "date": utc_iso(now - timedelta(hours=1)),
            "last_date": utc_iso(now + timedelta(hours=2)),
            "tz": "UTC",
        },
    )
    raw_frames = payload.get("radar", [])
    frames: list[dict[str, Any]] = []
    if isinstance(raw_frames, list):
        for raw in raw_frames:
            if not isinstance(raw, dict):
                continue
            frame = _sanitized_radar_frame(raw, now=now)
            if frame["kind"] in {"radar_observed", "radar_nowcast"}:
                frames.append(frame)

    rendering_contract = _radar_rendering_contract(frames)
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
            "rendering_contract": rendering_contract,
        },
        "frames": frames,
    }
