#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SINGLE_RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = (
    "temperature_2m",
    "dew_point_2m",
    "precipitation",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_gusts_10m",
)
MODELS = {
    "icon_d2": {"api_model": "icon_d2", "forecast_days": 2},
    "ecmwf_ifs": {"api_model": "ecmwf_ifs", "forecast_days": 10},
    "ecmwf_aifs": {"api_model": "ecmwf_aifs025_single", "forecast_days": 15},
}
GAPS = (
    ("icon_d2", "2026-08-15T18:00:00Z", "exact_run_required_variables_1h"),
    ("icon_d2", "2026-08-19T00:00:00Z", "exact_run_required_variables_1h"),
    ("icon_d2", "2026-08-22T06:00:00Z", "exact_run_required_variables_1h"),
    ("icon_d2", "2026-08-25T12:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_ifs", "2026-08-13T06:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_ifs", "2026-08-16T18:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_ifs", "2026-08-20T06:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_ifs", "2026-08-23T12:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_ifs", "2026-08-26T12:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_aifs", "2026-08-13T18:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_aifs", "2026-08-17T06:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_aifs", "2026-08-21T00:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_aifs", "2026-08-24T06:00:00Z", "exact_run_required_variables_1h"),
    ("ecmwf_aifs", "2026-08-13T06:00:00Z", "full_horizon_boundary"),
)


def _once(params: dict[str, object], timeout: float) -> tuple[int, str | None, object, bool]:
    url = f"{SINGLE_RUNS_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "rozkalns-weather-exact-run-gap-proof/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            content_type = response.headers.get("Content-Type")
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = int(exc.code)
        content_type = exc.headers.get("Content-Type") if exc.headers else None
        body = exc.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError) as exc:
        detail = getattr(exc, "reason", exc)
        return 0, None, {"transport_error": str(detail)}, True
    try:
        payload: object = json.loads(body)
    except json.JSONDecodeError:
        payload = {"non_json_body": body[:240]}
    return status, content_type, payload, False


def _request(params: dict[str, object], timeout: float = 20.0) -> tuple[int, str | None, object, int]:
    attempts = 0
    while True:
        attempts += 1
        status, content_type, payload, transport_error = _once(params, timeout)
        if not transport_error or attempts >= 3:
            return status, content_type, payload, attempts
        time.sleep(float(attempts))


def _api_reason(status: int, payload: object) -> str | None:
    if status != 200:
        return f"HTTP_{status}"
    if not isinstance(payload, dict):
        return "NON_OBJECT_JSON"
    if payload.get("error") is True:
        return str(payload.get("reason") or "API_ERROR")
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list) or not hourly["time"]:
        return "MISSING_HOURLY_TIME"
    return None


def main() -> int:
    benchmark = json.loads(Path("deploy/dwd-cdc-05480-benchmark.json").read_text())
    station = benchmark["station"]
    if station["stations_id"] != "05480" or station["location_id"] != "station_05480":
        raise SystemExit("benchmark station contract mismatch")
    lat = float(station["latitude"])
    lon = float(station["longitude"])

    results: list[dict[str, object]] = []
    for provider, init_text, phase in GAPS:
        config = MODELS[provider]
        init = datetime.fromisoformat(init_text.replace("Z", "+00:00")).astimezone(timezone.utc)
        params: dict[str, object] = {
            "latitude": lat,
            "longitude": lon,
            "models": config["api_model"],
            "run": init.strftime("%Y-%m-%dT%H:%M"),
            "timezone": "GMT",
            "wind_speed_unit": "ms",
        }
        if phase == "exact_run_required_variables_1h":
            params["hourly"] = ",".join(HOURLY_VARIABLES)
            params["forecast_hours"] = 1
        else:
            params["hourly"] = "temperature_2m"
            params["forecast_days"] = config["forecast_days"]

        status, content_type, payload, attempts = _request(params)
        reason = _api_reason(status, payload)
        last_valid: str | None = None
        if reason is None:
            assert isinstance(payload, dict)
            hourly = payload["hourly"]
            assert isinstance(hourly, dict)
            if phase == "exact_run_required_variables_1h":
                for variable in HOURLY_VARIABLES:
                    values = hourly.get(variable)
                    if not isinstance(values, list) or not values:
                        reason = f"MISSING_{variable.upper()}"
                        break
            else:
                values = hourly.get("temperature_2m")
                if not isinstance(values, list) or not values:
                    reason = "MISSING_TEMPERATURE_2M"
                else:
                    last_time = datetime.fromisoformat(str(hourly["time"][-1]).replace("Z", "+00:00"))
                    if last_time.tzinfo is None:
                        last_time = last_time.replace(tzinfo=timezone.utc)
                    last_time = last_time.astimezone(timezone.utc)
                    expected_last = init + timedelta(hours=int(config["forecast_days"]) * 24 - 1)
                    last_valid = last_time.isoformat().replace("+00:00", "Z")
                    if last_time < expected_last:
                        reason = "TRUNCATED_HORIZON"
        result = {
            "provider": provider,
            "init_time_utc": init_text,
            "phase": phase,
            "status": status,
            "content_type": content_type,
            "attempts": attempts,
            "state": "PASS" if reason is None else "BLOCKED",
            "reason": reason,
            "last_valid_time_utc": last_valid,
        }
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)

    passed = sum(item["state"] == "PASS" for item in results)
    summary = {
        "schema_version": 1,
        "contract": "rozkalns-weather.exact-run-window-gap-closure.v1",
        "state": "PASS" if passed == len(results) else "BLOCKED",
        "source_probe_run": 35614910970,
        "candidate_window": {"start_date": "2026-08-13", "end_date": "2026-08-26"},
        "expected_gap_probes": len(results),
        "passed_gap_probes": passed,
        "results": results,
        "retry_semantics": {
            "transport_only": True,
            "max_attempts": 3,
            "api_or_model_error_retried": False,
            "production_write": False,
            "live_retry": False,
        },
    }
    fingerprint_input = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()
    summary["evidence_fingerprint"] = hashlib.sha256(fingerprint_input).hexdigest()
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if summary["state"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
