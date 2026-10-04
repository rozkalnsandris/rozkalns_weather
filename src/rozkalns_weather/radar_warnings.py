from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any
from urllib.parse import urlencode

from .models import parse_time, utc_iso
from .providers.base import BytesFetcher, JsonFetcher, fetch_bytes, fetch_json

BRIGHTSKY_ALERTS_URL = "https://api.brightsky.dev/alerts"
BRIGHTSKY_RADAR_URL = "https://api.brightsky.dev/radar"
DWD_WMS_URL = "https://maps.dwd.de/geoserver/dwd/wms"
DWD_WMS_LAYERS = "dwd:bluemarble,dwd:Niederschlagsradar"
DWD_WMS_CRS = "EPSG:3857"
DWD_WMS_IMAGE_SIZE_PX = 640
DWD_WMS_MAX_IMAGE_BYTES = 2_000_000
DWD_WMS_MAX_VIEW_SPAN_DEGREES = 2.0
WEB_MERCATOR_RADIUS_M = 6_378_137.0
WEB_MERCATOR_MAX_LAT = 85.0
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RADAR_RENDER_DISTANCE_M = 20_000


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
    """Keep only the timeline fields needed by the browser."""

    timestamp = raw.get("timestamp") or raw.get("time")
    kind = radar_frame_kind(str(timestamp) if timestamp else None, now=now)
    frame: dict[str, Any] = {
        "timestamp": str(timestamp) if timestamp else None,
        "kind": kind,
    }
    source = raw.get("source")
    if source:
        frame["source"] = str(source)
    return frame



def normalize_dwd_wms_time(value: str) -> str:
    """Return the DWD WMS time form used by its advertised ISO8601 dimension."""

    stamp = parse_time(value).astimezone(timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _validate_radar_bounds(*, west: float, south: float, east: float, north: float) -> None:
    if west >= east or south >= north:
        raise ValueError("radar map bounds must have positive width and height")
    if east - west > DWD_WMS_MAX_VIEW_SPAN_DEGREES or north - south > DWD_WMS_MAX_VIEW_SPAN_DEGREES:
        raise ValueError("radar map view is too large")
    if south < -WEB_MERCATOR_MAX_LAT or north > WEB_MERCATOR_MAX_LAT:
        raise ValueError("radar map latitude is outside Web Mercator")


def _web_mercator_xy(*, lon: float, lat: float) -> tuple[float, float]:
    x = WEB_MERCATOR_RADIUS_M * math.radians(lon)
    y = WEB_MERCATOR_RADIUS_M * math.log(
        math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)
    )
    return x, y


def dwd_radar_map_url(
    *,
    at: str,
    west: float,
    south: float,
    east: float,
    north: float,
) -> str:
    """Build one fixed DWD WMS image for the requested public map viewport."""

    _validate_radar_bounds(west=west, south=south, east=east, north=north)
    left, bottom = _web_mercator_xy(lon=west, lat=south)
    right, top = _web_mercator_xy(lon=east, lat=north)
    params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": DWD_WMS_LAYERS,
        "styles": ",",
        "crs": DWD_WMS_CRS,
        "bbox": f"{left:.3f},{bottom:.3f},{right:.3f},{top:.3f}",
        "width": str(DWD_WMS_IMAGE_SIZE_PX),
        "height": str(DWD_WMS_IMAGE_SIZE_PX),
        "format": "image/png",
        "transparent": "FALSE",
        "time": normalize_dwd_wms_time(at),
    }
    return f"{DWD_WMS_URL}?{urlencode(params)}"


def fetch_dwd_radar_map_png(
    *,
    at: str,
    west: float,
    south: float,
    east: float,
    north: float,
    fetcher: BytesFetcher = fetch_bytes,
) -> bytes:
    url = dwd_radar_map_url(at=at, west=west, south=south, east=east, north=north)
    payload = fetcher(url)
    if not payload.startswith(PNG_SIGNATURE):
        raise ValueError("DWD WMS did not return a PNG image")
    if len(payload) > DWD_WMS_MAX_IMAGE_BYTES:
        raise ValueError("DWD WMS image is larger than the bounded map contract")
    return payload

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
        },
        "frames": frames,
    }
