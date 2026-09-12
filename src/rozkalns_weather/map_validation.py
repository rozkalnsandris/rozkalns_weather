from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, TextIO

CONTRACT_VERSION = "live-map-validation-v1"
RADAR_OBSERVED_STALE_AFTER_MINUTES = 20
RADAR_NOWCAST_MAX_HORIZON_MINUTES = 120

WARNING_PRESENTATION = {
    "authority": "DWD",
    "official": True,
    "kind": "official_warning",
    "title": "DWD official warnings",
    "panel_class": "warning",
    "model_warning_substitution": False,
}
RADAR_PRESENTATION = {
    "source": "DWD radar",
    "not_model_forecast": True,
    "allowed_kinds": ["radar_observed", "radar_nowcast"],
}


class MapValidationError(ValueError):
    """Invalid map validation evidence."""


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MapValidationError("timestamp must be a non-empty string")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MapValidationError("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise MapValidationError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _number(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise MapValidationError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MapValidationError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise MapValidationError(f"{name} must be finite")
    return number


def _location(evidence: dict[str, Any]) -> tuple[float, float]:
    location = evidence.get("location")
    if not isinstance(location, dict):
        raise MapValidationError("location is required")
    lat = _number(location.get("lat"), name="location.lat")
    lon = _number(location.get("lon"), name="location.lon")
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        raise MapValidationError("location is outside global coordinate bounds")
    return lat, lon


def _bounds(evidence: dict[str, Any]) -> tuple[float, float, float, float]:
    bounds = evidence.get("map_bounds")
    if not isinstance(bounds, dict):
        raise MapValidationError("map_bounds is required")
    south = _number(bounds.get("south"), name="map_bounds.south")
    west = _number(bounds.get("west"), name="map_bounds.west")
    north = _number(bounds.get("north"), name="map_bounds.north")
    east = _number(bounds.get("east"), name="map_bounds.east")
    if not (-90.0 <= south < north <= 90.0 and -180.0 <= west < east <= 180.0):
        raise MapValidationError("map_bounds are invalid")
    return south, west, north, east


def _point_on_segment(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> bool:
    x, y = point
    x1, y1 = a
    x2, y2 = b
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > 1e-10:
        return False
    return min(x1, x2) - 1e-10 <= x <= max(x1, x2) + 1e-10 and min(y1, y2) - 1e-10 <= y <= max(y1, y2) + 1e-10


def _point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, current in enumerate(ring):
        previous = ring[j]
        if _point_on_segment(point, previous, current):
            return True
        xi, yi = current
        xj, yj = previous
        if (yi > point[1]) != (yj > point[1]):
            crossing_x = (xj - xi) * (point[1] - yi) / (yj - yi) + xi
            if point[0] < crossing_x:
                inside = not inside
        j = i
    return inside


def _geojson_rings(geometry: Any) -> list[list[tuple[float, float]]]:
    if not isinstance(geometry, dict):
        raise MapValidationError("warning geometry must be an object")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    polygons: list[Any]
    if kind == "Polygon":
        polygons = [coordinates]
    elif kind == "MultiPolygon":
        polygons = coordinates if isinstance(coordinates, list) else []
    else:
        raise MapValidationError("warning geometry must be Polygon or MultiPolygon")
    rings: list[list[tuple[float, float]]] = []
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise MapValidationError("warning geometry polygon is empty")
        outer = polygon[0]
        if not isinstance(outer, list):
            raise MapValidationError("warning geometry ring is invalid")
        ring: list[tuple[float, float]] = []
        for pair in outer:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                raise MapValidationError("warning geometry coordinate is invalid")
            lon = _number(pair[0], name="geometry.lon")
            lat = _number(pair[1], name="geometry.lat")
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise MapValidationError("warning geometry coordinate is outside global bounds")
            ring.append((lon, lat))
        _validate_ring(ring)
        rings.append(ring)
    if not rings:
        raise MapValidationError("warning geometry has no polygon")
    return rings


def _cap_polygon_ring(polygon: Any) -> list[tuple[float, float]]:
    if not isinstance(polygon, str) or not polygon.strip():
        raise MapValidationError("CAP polygon is empty")
    ring: list[tuple[float, float]] = []
    for token in polygon.split():
        parts = token.split(",")
        if len(parts) != 2:
            raise MapValidationError("CAP polygon coordinate is invalid")
        lat = _number(parts[0], name="cap.lat")
        lon = _number(parts[1], name="cap.lon")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise MapValidationError("CAP polygon coordinate is outside global bounds")
        ring.append((lon, lat))
    _validate_ring(ring)
    return ring


def _validate_ring(ring: list[tuple[float, float]]) -> None:
    if len(ring) < 4:
        raise MapValidationError("warning polygon must contain at least four points")
    if ring[0] != ring[-1]:
        raise MapValidationError("warning polygon must be closed")


def _warning_rings(alert: dict[str, Any]) -> list[list[tuple[float, float]]]:
    if alert.get("geometry") is not None:
        return _geojson_rings(alert["geometry"])
    if alert.get("polygon") is not None:
        return [_cap_polygon_ring(alert["polygon"])]
    raise MapValidationError("warning geometry is required")


def _ring_bbox(ring: Iterable[tuple[float, float]]) -> tuple[float, float, float, float]:
    points = tuple(ring)
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return min(lats), min(lons), max(lats), max(lons)


def _bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _warning_lifecycle(alert: dict[str, Any], *, now: datetime) -> str:
    effective_raw = alert.get("effective") or alert.get("onset")
    effective = _parse_time(effective_raw) if effective_raw else None
    expires = _parse_time(alert.get("expires"))
    if effective is not None and expires <= effective:
        raise MapValidationError("warning expires must be after effective/onset")
    if expires <= now:
        return "expired"
    if effective is not None and effective > now:
        return "upcoming"
    return "active"


def _warning_revision_time(alert: dict[str, Any]) -> datetime:
    raw = alert.get("updated") or alert.get("sent")
    if raw is None:
        raise MapValidationError("warning revision time is required")
    return _parse_time(raw)


def _latest_warning_revisions(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, tuple[datetime, str, dict[str, Any]]] = {}
    for alert in alerts:
        identifier = alert.get("id") or alert.get("identifier")
        if not isinstance(identifier, str) or not identifier.strip():
            raise MapValidationError("warning identifier is required")
        revision = _warning_revision_time(alert)
        fingerprint = json.dumps(alert, sort_keys=True, separators=(",", ":"), default=str)
        current = latest.get(identifier)
        if current is None or revision > current[0]:
            latest[identifier] = (revision, fingerprint, alert)
        elif revision == current[0] and fingerprint != current[1]:
            raise MapValidationError("warning revision collision")
    return [item for _, _, item in sorted(latest.values(), key=lambda entry: (entry[0], entry[1]))]


def _validate_ui_contract(index_html: str) -> bool:
    required = (
        'class="panel warning"',
        "DWD official warnings",
        "DWD warning slānis ir autoritatīvs un atdalīts no modeļiem.",
        "Radar observed/nowcast nav model forecast.",
    )
    return all(token in index_html for token in required)


def _pack_result(*, blocked: set[str], warnings: set[str], warning_summary: dict[str, int], radar_summary: dict[str, int], ui_separation_ok: bool) -> dict[str, Any]:
    state = "BLOCKED" if blocked else "WARN" if warnings else "PASS"
    return {
        "contract_version": CONTRACT_VERSION,
        "state": state,
        "reason_codes": sorted(blocked | warnings),
        "blocking_reason_codes": sorted(blocked),
        "warning_reason_codes": sorted(warnings),
        "warning_summary": warning_summary,
        "radar_summary": radar_summary,
        "presentation": {
            "warnings": WARNING_PRESENTATION,
            "radar": RADAR_PRESENTATION,
            "ui_separation_ok": ui_separation_ok,
        },
        "privacy": {
            "coordinates_exposed": False,
            "geometry_exposed": False,
            "credentials_exposed": False,
            "raw_payload_exposed": False,
        },
        "network_access_performed": False,
        "runtime_mutation_performed": False,
        "live_authority_granted": False,
    }


def validate_map_evidence(evidence: dict[str, Any], *, now: datetime, index_html: str | None = None) -> dict[str, Any]:
    now = now.astimezone(timezone.utc)
    blocked: set[str] = set()
    warnings: set[str] = set()
    warning_summary = {"received": 0, "latest": 0, "active": 0, "upcoming": 0, "expired": 0, "applies_to_location": 0}
    radar_summary = {"frames": 0, "observed": 0, "nowcast": 0}

    try:
        lat, lon = _location(evidence)
    except MapValidationError:
        blocked.add("PRIVATE_COORDINATES_REQUIRED")
        lat = lon = 0.0

    try:
        bounds = _bounds(evidence)
    except MapValidationError:
        blocked.add("MAP_BOUNDS_INVALID")
        bounds = (-90.0, -180.0, 90.0, 180.0)

    if "PRIVATE_COORDINATES_REQUIRED" not in blocked and "MAP_BOUNDS_INVALID" not in blocked:
        if not (bounds[0] <= lat <= bounds[2] and bounds[1] <= lon <= bounds[3]):
            blocked.add("MAP_CENTER_OUTSIDE_BOUNDS")

    warning_evidence = evidence.get("warnings")
    alerts: list[dict[str, Any]] = []
    if not isinstance(warning_evidence, dict):
        blocked.add("DWD_WARNING_EVIDENCE_MISSING")
    else:
        if not (
            warning_evidence.get("authority") == "DWD"
            and warning_evidence.get("official") is True
            and warning_evidence.get("kind") == "official_warning"
        ):
            blocked.add("DWD_WARNING_AUTHORITY_CONTRACT_INVALID")
        raw_alerts = warning_evidence.get("alerts", [])
        if not isinstance(raw_alerts, list) or not all(isinstance(item, dict) for item in raw_alerts):
            blocked.add("WARNING_COLLECTION_INVALID")
        else:
            alerts = list(raw_alerts)
            warning_summary["received"] = len(alerts)

    latest_alerts: list[dict[str, Any]] = []
    if alerts:
        try:
            latest_alerts = _latest_warning_revisions(alerts)
        except MapValidationError as exc:
            blocked.add("WARNING_REVISION_COLLISION" if "collision" in str(exc) else "WARNING_REVISION_INVALID")
    warning_summary["latest"] = len(latest_alerts)

    for alert in latest_alerts:
        try:
            lifecycle = _warning_lifecycle(alert, now=now)
        except MapValidationError:
            blocked.add("WARNING_LIFECYCLE_INVALID")
            continue
        declared = alert.get("lifecycle")
        if declared is not None and declared != lifecycle:
            blocked.add("WARNING_LIFECYCLE_MISMATCH")
        warning_summary[lifecycle] += 1
        try:
            rings = _warning_rings(alert)
        except MapValidationError:
            blocked.add("WARNING_GEOMETRY_INVALID")
            continue
        applies = any(_point_in_ring((lon, lat), ring) for ring in rings) if "PRIVATE_COORDINATES_REQUIRED" not in blocked else False
        if applies:
            warning_summary["applies_to_location"] += 1
        if "MAP_BOUNDS_INVALID" not in blocked and not any(_bbox_intersects(_ring_bbox(ring), bounds) for ring in rings):
            warnings.add("WARNING_GEOMETRY_OUTSIDE_MAP")

    radar = evidence.get("radar")
    if radar is None:
        warnings.add("RADAR_EVIDENCE_MISSING")
    elif not isinstance(radar, dict):
        blocked.add("RADAR_EVIDENCE_INVALID")
    else:
        if radar.get("not_model_forecast") is not True:
            blocked.add("RADAR_MODEL_SEPARATION_INVALID")
        frames = radar.get("frames", [])
        if not isinstance(frames, list) or not all(isinstance(item, dict) for item in frames):
            blocked.add("RADAR_FRAMES_INVALID")
            frames = []
        radar_summary["frames"] = len(frames)
        observed_times: list[datetime] = []
        for frame in frames:
            kind = frame.get("kind")
            try:
                stamp = _parse_time(frame.get("timestamp") or frame.get("time"))
            except MapValidationError:
                blocked.add("RADAR_TIMESTAMP_INVALID")
                continue
            if kind == "radar_observed":
                radar_summary["observed"] += 1
                if stamp > now:
                    blocked.add("RADAR_OBSERVED_IN_FUTURE")
                else:
                    observed_times.append(stamp)
            elif kind == "radar_nowcast":
                radar_summary["nowcast"] += 1
                horizon_minutes = (stamp - now).total_seconds() / 60.0
                if horizon_minutes <= 0:
                    blocked.add("RADAR_NOWCAST_NOT_FUTURE")
                elif horizon_minutes > RADAR_NOWCAST_MAX_HORIZON_MINUTES:
                    blocked.add("RADAR_NOWCAST_HORIZON_EXCEEDED")
            else:
                blocked.add("RADAR_KIND_INVALID")
        if not observed_times:
            warnings.add("RADAR_OBSERVED_MISSING")
        else:
            age_minutes = (now - max(observed_times)).total_seconds() / 60.0
            if age_minutes > RADAR_OBSERVED_STALE_AFTER_MINUTES:
                warnings.add("RADAR_OBSERVED_STALE")
        if radar_summary["nowcast"] == 0:
            warnings.add("RADAR_NOWCAST_MISSING")

    if index_html is None:
        try:
            index_html = (Path(__file__).with_name("static") / "index.html").read_text(encoding="utf-8")
        except OSError:
            index_html = ""
    ui_separation_ok = _validate_ui_contract(index_html)
    if not ui_separation_ok:
        blocked.add("DWD_WARNING_UI_SEPARATION_INVALID")

    return _pack_result(
        blocked=blocked,
        warnings=warnings,
        warning_summary=warning_summary,
        radar_summary=radar_summary,
        ui_separation_ok=ui_separation_ok,
    )


def _invalid_payload() -> dict[str, Any]:
    return _pack_result(
        blocked={"MAP_VALIDATION_INPUT_INVALID"},
        warnings=set(),
        warning_summary={"received": 0, "latest": 0, "active": 0, "upcoming": 0, "expired": 0, "applies_to_location": 0},
        radar_summary={"frames": 0, "observed": 0, "nowcast": 0},
        ui_separation_ok=False,
    )


def main(argv: list[str] | None = None, input_stream: TextIO | None = None, output_stream: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rozkalns_weather.map_validation")
    parser.add_argument("--now", required=True, help="validation time as timezone-aware ISO-8601")
    args = parser.parse_args(argv)
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    try:
        now = _parse_time(args.now)
        evidence = json.load(input_stream)
        if not isinstance(evidence, dict):
            raise MapValidationError("map evidence must be a JSON object")
        payload = validate_map_evidence(evidence, now=now)
    except (MapValidationError, json.JSONDecodeError, TypeError, ValueError):
        payload = _invalid_payload()
        print(json.dumps(payload, sort_keys=True, indent=2), file=output_stream)
        return 2
    print(json.dumps(payload, sort_keys=True, indent=2), file=output_stream)
    return 3 if payload["state"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
