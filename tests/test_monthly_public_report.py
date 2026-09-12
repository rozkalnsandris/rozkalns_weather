from __future__ import annotations

import hashlib
import json

from rozkalns_weather.monthly_public_report import (
    build_monthly_public_report,
    build_monthly_public_report_files,
    render_monthly_public_report_markdown,
)

SOURCE_SHA = "b" * 40
INIT = "2026-09-01T00:00:00Z"
VALID = "2026-09-01T03:00:00Z"
RETRIEVED = "2026-09-01T00:20:00Z"


def forecast_row(
    provider: str,
    value: float,
    *,
    model_version: str,
    statistic: str = "deterministic",
    variable: str = "temperature_2m",
    unit: str = "degC",
    raw_char: str = "1",
    init_time: str = INIT,
    valid_time: str = VALID,
    retrieved_at: str = RETRIEVED,
) -> dict[str, object]:
    identities = {
        "icon_d2": ("DWD", "ICON-D2"),
        "ecmwf_ifs": ("ECMWF", "IFS HRES"),
        "ecmwf_aifs": ("ECMWF", "AIFS"),
        "icon_d2_eps": ("DWD", "ICON-D2-EPS"),
    }
    model_provider, model_name = identities[provider]
    return {
        "provider": provider,
        "model_provider": model_provider,
        "model_name": model_name,
        "model_version": model_version,
        "location_id": "station_10416",
        "init_time_utc": init_time,
        "retrieved_at_utc": retrieved_at,
        "upstream_available_at_utc": None,
        "init_time_quality": "provider_run",
        "source_surface": "fixture",
        "transport_provider": "fixture",
        "raw_payload_hash": raw_char * 64,
        "revision": 1,
        "valid_time_utc": valid_time,
        "lead_hours": 3.0,
        "variable": variable,
        "statistic": statistic,
        "value": value,
        "unit": unit,
        "accumulation_window_minutes": 60 if variable == "precipitation_1h" else None,
        "quality_status": "ok",
    }


def observation(
    variable: str,
    value: float,
    unit: str,
    *,
    observed_at: str = VALID,
) -> dict[str, object]:
    return {
        "source_provider": "DWD",
        "station_id": "10416",
        "location_id": "station_10416",
        "observed_at_utc": observed_at,
        "variable": variable,
        "value": value,
        "unit": unit,
        "quality_status": "ok",
    }


def fixture_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    forecasts = [
        forecast_row("icon_d2", 10.0, model_version="icon-v1", raw_char="1"),
        forecast_row("ecmwf_ifs", 12.0, model_version="ifs-v1", raw_char="2"),
        forecast_row("ecmwf_aifs", 14.0, model_version="aifs-v1", raw_char="3"),
    ]
    for index, value in enumerate((9.0, 11.0, 13.0)):
        forecasts.append(
            forecast_row(
                "icon_d2_eps",
                value,
                model_version="icon-eps-v1",
                statistic=f"member_{index:02d}",
                raw_char="4",
            )
        )
    for index, value in enumerate((0.0, 0.2, 0.4)):
        forecasts.append(
            forecast_row(
                "icon_d2_eps",
                value,
                model_version="icon-eps-v1",
                statistic=f"member_{index:02d}",
                variable="precipitation_1h",
                unit="mm",
                raw_char="5",
            )
        )
    observations = [
        observation("temperature_2m", 11.0, "degC"),
        observation("precipitation_1h", 0.2, "mm"),
    ]
    return forecasts, observations


def test_common_month_emits_json_markdown_metrics_reliability_and_pending_weathernext() -> None:
    forecasts, observations = fixture_rows()
    report = build_monthly_public_report(
        source_sha=SOURCE_SHA,
        month="2026-09",
        forecast_rows=forecasts,
        observation_rows=observations,
    )
    assert report["state"] == "PASS"
    assert report["window"]["classification"] == "common_full_month"
    temperature = next(
        row
        for row in report["deterministic_common_sample"]
        if row["variable"] == "temperature_2m" and row["lead_bucket"] == "0-6h"
    )
    by_provider = {row["provider"]: row for row in temperature["metrics"]}
    assert by_provider["icon_d2"]["mae"] == 1.0
    assert by_provider["ecmwf_ifs"]["rmse"] == 1.0
    assert by_provider["ecmwf_aifs"]["bias"] == 3.0

    precip = next(row for row in report["ensemble"] if row["variable"] == "precipitation_1h")
    assert precip["brier_score"] is not None
    reliability = report["precipitation_reliability"][0]
    assert reliability["provider"] == "icon_d2_eps"
    assert sum(bin_["n"] for bin_ in reliability["bins"]) == 1

    assert report["weathernext"]["state"] == "pending"
    assert report["weathernext"]["fabricated_values"] is False
    markdown = render_monthly_public_report_markdown(report)
    assert "Deterministic common-sample metrics" in markdown
    assert "WeatherNext 3: `pending`" in markdown
    assert "No pre-common-window days" in markdown


def test_report_files_are_byte_stable_and_checksummed() -> None:
    forecasts, observations = fixture_rows()
    first = build_monthly_public_report(
        source_sha=SOURCE_SHA,
        month="2026-09",
        forecast_rows=forecasts,
        observation_rows=observations,
    )
    second = build_monthly_public_report(
        source_sha=SOURCE_SHA,
        month="2026-09",
        forecast_rows=list(reversed(forecasts)),
        observation_rows=list(reversed(observations)),
    )
    files_a = build_monthly_public_report_files(first)
    files_b = build_monthly_public_report_files(second)
    assert files_a == files_b
    checksums = json.loads(files_a["checksums.json"])
    assert checksums["report.json"] == hashlib.sha256(files_a["report.json"]).hexdigest()
    assert checksums["report.md"] == hashlib.sha256(files_a["report.md"]).hexdigest()


def test_april_clips_common_window_and_keeps_ifs_history_separate() -> None:
    forecasts, observations = fixture_rows()
    for row in forecasts:
        row["init_time_utc"] = "2026-04-02T00:00:00Z"
        row["retrieved_at_utc"] = "2026-04-02T00:20:00Z"
        row["valid_time_utc"] = "2026-04-02T03:00:00Z"
    for row in observations:
        row["observed_at_utc"] = "2026-04-02T03:00:00Z"
    report = build_monthly_public_report(
        source_sha=SOURCE_SHA,
        month="2026-04",
        forecast_rows=forecasts,
        observation_rows=observations,
        historical_ifs_only={
            "provider": "ecmwf_ifs",
            "start": "2026-04-01",
            "end": "2026-04-01",
            "run_count": 4,
            "forecast_value_rows": 40,
            "included_in_common_metrics": False,
        },
    )
    assert report["state"] == "PASS"
    assert report["window"]["classification"] == "common_clipped"
    assert report["window"]["common_start"] == "2026-04-02"
    assert report["historical_ifs_only"]["run_count"] == 4
    assert report["historical_ifs_only"]["included_in_common_metrics"] is False


def test_pre_common_month_is_warn_historical_context_only() -> None:
    report = build_monthly_public_report(
        source_sha=SOURCE_SHA,
        month="2026-03",
        forecast_rows=[],
        observation_rows=[],
        historical_ifs_only={
            "provider": "ecmwf_ifs",
            "start": "2026-03-01",
            "end": "2026-03-31",
            "run_count": 8,
            "forecast_value_rows": 80,
            "included_in_common_metrics": False,
        },
    )
    assert report["state"] == "WARN"
    assert report["reason_code"] == "HISTORICAL_IFS_ONLY"
    assert report["deterministic_common_sample"] == []
    assert report["historical_ifs_only"]["run_count"] == 8


def test_rows_outside_month_block_fail_closed() -> None:
    forecasts, observations = fixture_rows()
    report = build_monthly_public_report(
        source_sha=SOURCE_SHA,
        month="2026-04",
        forecast_rows=forecasts,
        observation_rows=observations,
    )
    assert report["state"] == "BLOCKED"
    assert report["reason_code"] == "ROW_OUTSIDE_REPORT_WINDOW"


def test_mixed_model_versions_block_instead_of_hiding_boundary() -> None:
    forecasts, observations = fixture_rows()
    extra = dict(forecasts[0])
    extra["model_version"] = "icon-v2"
    extra["retrieved_at_utc"] = "2026-09-01T00:21:00Z"
    extra["raw_payload_hash"] = "6" * 64
    forecasts.append(extra)
    report = build_monthly_public_report(
        source_sha=SOURCE_SHA,
        month="2026-09",
        forecast_rows=forecasts,
        observation_rows=observations,
    )
    assert report["state"] == "BLOCKED"
    assert report["reason_code"] == "MIXED_MODEL_VERSIONS"
    assert report["weathernext"]["fabricated_values"] is False
