#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
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
FULL_HORIZON_BOUNDARY_DATES = ("start", "end")


def _dates(start: date, end: date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def _request_json(params: dict[str, object], timeout: float) -> tuple[int, str | None, object]:
    url = f"{SINGLE_RUNS_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "rozkalns-weather-exact-run-proof/2"})
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


def _base_params(*, lat: float, lon: float, api_model: str, init: datetime) -> dict[str, object]:
    return {
        "latitude": lat,
        "longitude": lon,
        "models": api_model,
        "run": init.strftime("%Y-%m-%dT%H:%M"),
        "timezone": "GMT",
        "wind_speed_unit": "ms",
    }


def _response_error(status: int, payload: object) -> str | None:
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


def _parse_api_time(value: object) -> datetime:
    text = str(value)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _probe_run_variables(
    *,
    lat: float,
    lon: float,
    api_model: str,
    init: datetime,
    timeout: float,
) -> tuple[int, str | None, object, str | None]:
    params = _base_params(lat=lat, lon=lon, api_model=api_model, init=init)
    params.update(
        {
            "hourly": ",".join(HOURLY_VARIABLES),
            "forecast_hours": 1,
        }
    )
    status, content_type, payload = _request_json(params, timeout)
    reason = _response_error(status, payload)
    if reason is None:
        assert isinstance(payload, dict)
        hourly = payload["hourly"]
        assert isinstance(hourly, dict)
        for variable in HOURLY_VARIABLES:
            values = hourly.get(variable)
            if not isinstance(values, list) or not values:
                reason = f"MISSING_{variable.upper()}"
                break
    return status, content_type, payload, reason


def _probe_full_horizon(
    *,
    lat: float,
    lon: float,
    api_model: str,
    forecast_days: int,
    init: datetime,
    timeout: float,
) -> tuple[int, str | None, object, str | None, str | None]:
    params = _base_params(lat=lat, lon=lon, api_model=api_model, init=init)
    params.update(
        {
            "hourly": "temperature_2m",
            "forecast_days": forecast_days,
        }
    )
    status, content_type, payload = _request_json(params, timeout)
    reason = _response_error(status, payload)
    last_valid: str | None = None
    if reason is None:
        assert isinstance(payload, dict)
        hourly = payload["hourly"]
        assert isinstance(hourly, dict)
        values = hourly.get("temperature_2m")
        if not isinstance(values, list) or not values:
            reason = "MISSING_TEMPERATURE_2M"
        else:
            times = hourly["time"]
            last_time = _parse_api_time(times[-1])
            expected_last = init + timedelta(hours=forecast_days * 24 - 1)
            last_valid = last_time.isoformat().replace("+00:00", "Z")
            if last_time < expected_last:
                reason = f"TRUNCATED_HORIZON_EXPECTED_AT_LEAST_{expected_last.isoformat().replace('+00:00', 'Z')}"
    return status, content_type, payload, reason, last_valid


def _failure(
    *,
    provider: str,
    init: datetime,
    phase: str,
    status: int,
    content_type: str | None,
    reason: str,
    payload: object,
) -> dict[str, object]:
    return {
        "provider": provider,
        "init_time_utc": init.isoformat().replace("+00:00", "Z"),
        "phase": phase,
        "status": status,
        "content_type": content_type,
        "reason": reason,
        "payload_excerpt": payload if isinstance(payload, dict) else str(payload)[:240],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded public exact-run availability proof for issue #159")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--truth-end", type=date.fromisoformat, default=date(2026, 9, 10))
    parser.add_argument("--delay-seconds", type=float, default=0.15)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
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
    total_horizon_expected = 0
    total_horizon_passed = 0

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
                status, content_type, payload, reason = _probe_run_variables(
                    lat=lat,
                    lon=lon,
                    api_model=str(config["api_model"]),
                    init=init,
                    timeout=args.timeout_seconds,
                )
                if reason is None:
                    passed += 1
                    total_passed += 1
                    stamp = init.isoformat().replace("+00:00", "Z")
                    earliest = earliest or stamp
                    latest = stamp
                else:
                    failures.append(
                        _failure(
                            provider=provider,
                            init=init,
                            phase="exact_run_required_variables_1h",
                            status=status,
                            content_type=content_type,
                            reason=reason,
                            payload=payload,
                        )
                    )
                if args.delay_seconds:
                    time.sleep(args.delay_seconds)

        horizon_expected = 0
        horizon_passed = 0
        horizon_last_valid: list[str] = []
        for boundary_day in (args.start, args.end):
            for hour in RUN_HOURS:
                init = datetime(boundary_day.year, boundary_day.month, boundary_day.day, hour, tzinfo=timezone.utc)
                horizon_expected += 1
                total_horizon_expected += 1
                status, content_type, payload, reason, last_valid = _probe_full_horizon(
                    lat=lat,
                    lon=lon,
                    api_model=str(config["api_model"]),
                    forecast_days=int(config["forecast_days"]),
                    init=init,
                    timeout=args.timeout_seconds,
                )
                if reason is None:
                    horizon_passed += 1
                    total_horizon_passed += 1
                    if last_valid is not None:
                        horizon_last_valid.append(last_valid)
                else:
                    failures.append(
                        _failure(
                            provider=provider,
                            init=init,
                            phase="full_horizon_boundary",
                            status=status,
                            content_type=content_type,
                            reason=reason,
                            payload=payload,
                        )
                    )
                if args.delay_seconds:
                    time.sleep(args.delay_seconds)

        model_results[provider] = {
            "expected_runs": expected,
            "retrievable_runs": passed,
            "earliest_retrievable_init_utc": earliest,
            "latest_retrievable_init_utc": latest,
            "required_variables_complete": passed == expected,
            "full_horizon_boundary_probes_expected": horizon_expected,
            "full_horizon_boundary_probes_passed": horizon_passed,
            "full_horizon_boundary_last_valid_times_utc": horizon_last_valid,
            "full_horizon_complete": horizon_passed == horizon_expected,
            "complete": passed == expected and horizon_passed == horizon_expected,
        }
        print(
            f"{provider}: exact_run={passed}/{expected} full_horizon_boundary={horizon_passed}/{horizon_expected}",
            file=sys.stderr,
            flush=True,
        )

    latest_horizon_end = datetime(args.end.year, args.end.month, args.end.day, 18, tzinfo=timezone.utc) + timedelta(days=15)
    truth_end = datetime(args.truth_end.year, args.truth_end.month, args.truth_end.day, 23, 59, 59, tzinfo=timezone.utc)
    horizon_within_truth = latest_horizon_end <= truth_end
    state = (
        "PASS"
        if total_passed == total_expected
        and total_horizon_passed == total_horizon_expected
        and horizon_within_truth
        else "BLOCKED"
    )
    summary = {
        "schema_version": 2,
        "contract": "rozkalns-weather.exact-run-window-public-probe.v2",
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
        "total_full_horizon_boundary_probes_expected": total_horizon_expected,
        "total_full_horizon_boundary_probes_passed": total_horizon_passed,
        "failure_count": len(failures),
        "failures": failures,
        "latest_aifs_requested_horizon_end_utc": latest_horizon_end.isoformat().replace("+00:00", "Z"),
        "verified_truth_end": args.truth_end.isoformat(),
        "requested_horizon_within_verified_truth": horizon_within_truth,
        "probe_semantics": {
            "exact_run_parameter": True,
            "required_variable_probe_hours": 1,
            "full_adapter_variable_set": list(HOURLY_VARIABLES),
            "full_horizon_boundary_days": list(FULL_HORIZON_BOUNDARY_DATES),
            "full_horizon_boundary_run_hours_utc": list(RUN_HOURS),
            "full_horizon_probe_variable": "temperature_2m",
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
