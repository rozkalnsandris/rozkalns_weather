from __future__ import annotations

from typing import Any

from .providers.base import JsonFetcher, fetch_json

BRIGHTSKY_ALERTS_URL = "https://api.brightsky.dev/alerts"
BRIGHTSKY_RADAR_URL = "https://api.brightsky.dev/radar"


def fetch_dwd_alerts(*, lat: float, lon: float, fetcher: JsonFetcher = fetch_json) -> dict[str, Any]:
    payload = fetcher(BRIGHTSKY_ALERTS_URL, {"lat": lat, "lon": lon})
    return {"authority": "DWD", "transport": "Bright Sky", "official": True, "alerts": payload.get("alerts", [])}


def fetch_radar_point(*, lat: float, lon: float, fetcher: JsonFetcher = fetch_json) -> dict[str, Any]:
    payload = fetcher(BRIGHTSKY_RADAR_URL, {"lat": lat, "lon": lon})
    return {"source": "DWD radar via Bright Sky", "kind": "observed_or_radar_nowcast", "not_model_forecast": True, "radar": payload.get("radar", []), "geometry": payload.get("geometry")}
