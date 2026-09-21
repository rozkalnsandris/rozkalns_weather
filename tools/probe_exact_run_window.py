#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SINGLE_RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
RUN_HOURS = (0, 6, 12, 18)
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


def _dates(start: date, end: date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def _request_json(params: dict[str, object], timeout: float) -> tuple[int, str | None, object]:
    url = f"{SINGLE_RUNS_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "rozkalns-weather-exact-run-proof/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            content_type = response.headers.get("Content-Type")
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = int(exc.code)
        content_type = exc.headers.get("Content-Type") if exc.headers else None
        body = exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        return 0, None, {"transport_error": str(exc.reason)}
    try:
        payload: object = json.loads(body)
    except json.JSONDecodeError:
        payload = {"non_json_body": body[:240]}
    return status, content_type, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded public exact-run availability proof for issue #159")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--truth-end", type=date.fromisoformat, default=date(2026, 9, 10))
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    if args.end < args.start:
        raise SystemExit("end before start")

    benchmark = json.loads(Path("deploy/dwd-cdc-05480-benchmark.json").read_text())
    station = benchmark["station"]
    if station["stations_id"] != "05480" or station["location_id"] != "station_05480":
        raise SystemExit("benchmark station contract mismatch")
    lat = float(station["latitude"])
    lon = float(station["longitude"])

    failures: list[dict[str, object]] = []
    model_results: dict[str, dict[str, object]] = {}
    total_expected = 0
    total_passed = 0

    for provider, config in MODELS.items():
        expected = 0
        passed = 0
        earliest: str | None = None
        latest: str | None = None
        for day in _dates(args.start, args.end):
            for hour in RUN_HOURS:
                init = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
                expected += 1
                total_expected += 1
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": ",".join(HOURLY_VARIABLES),
                    "models": config["api_model"],
                    "forecast_days": config["forecast_days"],
                    "run": init.strftime("%Y-%m-%dT%H:%M"),
                    "timezone": "GMT",
                    "wind_speed_unit": "ms",
                }
                status, content_type, payload = _request_json(params, args.timeout_seconds)
                reason = None
                if status != 200:
                    reason = f"HTTP_{status}"
                elif not isinstance(payload, dict):
                    reason = "NON_OBJECT_JSON"
                elif payload.get("error") is True:
                    reason = str(payload.get("reason") or "API_ERROR")
                else:
                    hourly = payload.get("hourly")
                    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list) or not hourly["time"]:
                        reason = "MISSING_HOURLY_TIME"
                    else:
                        for variable in HOURLY_VARIABLES:
                            values = hourly.get(variable)
                            if not isinstance(values, list) or not values:
                                reason = f"MISSING_{variable.upper()}"
                                break
                if reason is None:
                    passed += 1
                    total_passed += 1
                    stamp = init.isoformat().replace("+00:00", "Z")
                    earliest = earliest or stamp
                    latest = stamp
                else:
                    failures.append(
                        {
                            "provider": provider,
                            "init_time_utc": init.isoformat().replace("+00:00", "Z"),
                            "status": status,
                            "content_type": content_type,
                            "reason": reason,
                            "payload_excerpt": payload if isinstance(payload, dict) else str(payload)[:240],
                        }
                    )
                if args.delay_seconds:
                    time.sleep(args.delay_seconds)
        model_results[provider] = {
            "expected_runs": expected,
            "retrievable_runs": passed,
            "earliest_retrievable_init_utc": earliest,
            "latest_retrievable_init_utc": latest,
            "complete": passed == expected,
        }

    latest_horizon_end = datetime(args.end.year, args.end.month, args.end.day, 18, tzinfo=timezone.utc) + timedelta(days=15)
    truth_end = datetime(args.truth_end.year, args.truth_end.month, args.truth_end.day, 23, 59, 59, tzinfo=timezone.utc)
    horizon_within_truth = latest_horizon_end <= truth_end
    state = "PASS" if total_passed == total_expected and horizon_within_truth else "BLOCKED"
    summary = {
        "schema_version": 1,
        "contract": "rozkalns-weather.exact-run-window-public-probe.v1",
        "state": state,
        "surface": SINGLE_RUNS_URL,
        "benchmark_location_id": "station_05480",
        "truth_station_id": "05480",
        "candidate_window": {
            "start_date": args.start.isoformat(),
            "end_date": args.end.isoformat(),
            "run_hours_utc": list(RUN_HOURS),
        },
        "models": model_results,
        "total_expected_runs": total_expected,
        "total_retrievable_runs": total_passed,
        "failure_count": len(failures),
        "failures": failures,
        "latest_aifs_requested_horizon_end_utc": latest_horizon_end.isoformat().replace("+00:00", "Z"),
        "verified_truth_end": args.truth_end.isoformat(),
        "requested_horizon_within_verified_truth": horizon_within_truth,
        "probe_semantics": {
            "exact_run_parameter": True,
            "full_adapter_variable_set": list(HOURLY_VARIABLES),
            "production_write": False,
            "private_home_coordinates": False,
            "retry": False,
        },
    }
    digest_payload = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()
    summary["evidence_fingerprint"] = hashlib.sha256(digest_payload).hexdigest()
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if state == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
