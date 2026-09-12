from __future__ import annotations

from datetime import date
import hashlib
import json

import pytest

from rozkalns_weather.benchmark_export import (
    BenchmarkExportError,
    build_benchmark_export_files,
)


SOURCE_SHA = "a" * 40
INIT = "2026-04-02T00:00:00Z"
VALID = "2026-04-02T03:00:00Z"
RETRIEVED = "2026-04-02T00:20:00Z"


def forecast_row(
    provider: str,
    value: float,
    *,
    model_version: str,
    statistic: str = "deterministic",
    variable: str = "temperature_2m",
    unit: str = "degC",
    raw_char: str = "1",
) -> dict[str, object]:
    model_names = {
        "icon_d2": ("DWD", "ICON-D2"),
        "ecmwf_ifs": ("ECMWF", "IFS HRES"),
        "ecmwf_aifs": ("ECMWF", "AIFS"),
        "icon_d2_eps": ("DWD", "ICON-D2-EPS"),
    }
    model_provider, model_name = model_names[provider]
    return {
        "provider": provider,
        "model_provider": model_provider,
        "model_name": model_name,
        "model_version": model_version,
        "location_id": "station_10416",
        "init_time_utc": INIT,
        "retrieved_at_utc": RETRIEVED,
        "upstream_available_at_utc": None,
        "init_time_quality": "provider_run",
        "source_surface": "fixture",
        "transport_provider": "fixture",
        "raw_payload_hash": raw_char * 64,
        "revision": 1,
        "valid_time_utc": VALID,
        "lead_hours": 3.0,
        "variable": variable,
        "statistic": statistic,
        "value": value,
        "unit": unit,
        "accumulation_window_minutes": 60 if variable == "precipitation_1h" else None,
        "quality_status": "ok",
    }


def observation_row(variable: str, value: float, unit: str) -> dict[str, object]:
    return {
        "source_provider": "DWD",
        "station_id": "10416",
        "location_id": "station_10416",
        "observed_at_utc": VALID,
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
        observation_row("temperature_2m", 11.0, "degC"),
        observation_row("precipitation_1h", 0.2, "mm"),
    ]
    return forecasts, observations


def parse_json_file(files: dict[str, bytes], name: str) -> object:
    return json.loads(files[name].decode("utf-8"))


def test_bundle_is_byte_stable_and_contains_reproducible_metrics() -> None:
    forecasts, observations = fixture_rows()
    files_a, summary_a = build_benchmark_export_files(
        source_sha=SOURCE_SHA,
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
        forecast_rows=forecasts,
        observation_rows=observations,
    )
    files_b, summary_b = build_benchmark_export_files(
        source_sha=SOURCE_SHA,
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
        forecast_rows=list(reversed(forecasts)),
        observation_rows=list(reversed(observations)),
    )
    assert files_a == files_b
    assert summary_a["bundle_fingerprint_sha256"] == summary_b["bundle_fingerprint_sha256"]
    checksums = parse_json_file(files_a, "checksums.json")
    assert isinstance(checksums, dict)
    for name in ("forecasts.ndjson", "observations.ndjson", "metrics.json", "manifest.json"):
        assert checksums[name] == hashlib.sha256(files_a[name]).hexdigest()

    metrics = parse_json_file(files_a, "metrics.json")
    deterministic = metrics["deterministic_common_sample"]
    temp = next(item for item in deterministic if item["variable"] == "temperature_2m" and item["lead_bucket"] == "0-6h")
    assert temp["n_common"] == 1
    by_provider = {item["provider"]: item for item in temp["metrics"]}
    assert by_provider["icon_d2"]["mae"] == 1.0
    assert by_provider["ecmwf_ifs"]["rmse"] == 1.0
    assert by_provider["ecmwf_aifs"]["bias"] == 3.0

    ensemble = metrics["ensemble"]
    temp_eps = next(item for item in ensemble if item["variable"] == "temperature_2m")
    precip_eps = next(item for item in ensemble if item["variable"] == "precipitation_1h")
    assert temp_eps["n"] == 1
    assert temp_eps["mean_crps"] is not None
    assert temp_eps["coverage"] == 1.0
    assert precip_eps["n"] == 1
    assert precip_eps["brier_score"] is not None


def test_incomplete_provenance_fails_closed() -> None:
    forecasts, observations = fixture_rows()
    forecasts[0]["raw_payload_hash"] = None
    with pytest.raises(BenchmarkExportError, match="forecast provenance missing") as exc:
        build_benchmark_export_files(
            source_sha=SOURCE_SHA,
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
            forecast_rows=forecasts,
            observation_rows=observations,
        )
    assert exc.value.reason_code == "INCOMPLETE_PROVENANCE"


def test_mixed_model_versions_fail_closed() -> None:
    forecasts, observations = fixture_rows()
    extra = dict(forecasts[0])
    extra["model_version"] = "icon-v2"
    extra["retrieved_at_utc"] = "2026-04-02T00:21:00Z"
    extra["raw_payload_hash"] = "6" * 64
    forecasts.append(extra)
    with pytest.raises(BenchmarkExportError) as exc:
        build_benchmark_export_files(
            source_sha=SOURCE_SHA,
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
            forecast_rows=forecasts,
            observation_rows=observations,
        )
    assert exc.value.reason_code == "MIXED_MODEL_VERSIONS"


def test_private_fields_fail_closed() -> None:
    forecasts, observations = fixture_rows()
    forecasts[0]["home_lat"] = 51.0
    with pytest.raises(BenchmarkExportError) as exc:
        build_benchmark_export_files(
            source_sha=SOURCE_SHA,
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
            forecast_rows=forecasts,
            observation_rows=observations,
        )
    assert exc.value.reason_code == "PRIVATE_FIELD_PRESENT"


def test_non_common_window_and_missing_provider_fail_closed() -> None:
    forecasts, observations = fixture_rows()
    with pytest.raises(BenchmarkExportError) as exc:
        build_benchmark_export_files(
            source_sha=SOURCE_SHA,
            start=date(2026, 4, 1),
            end=date(2026, 4, 2),
            forecast_rows=forecasts,
            observation_rows=observations,
        )
    assert exc.value.reason_code == "NON_COMMON_WINDOW"

    forecasts = [row for row in forecasts if row["provider"] != "ecmwf_aifs"]
    with pytest.raises(BenchmarkExportError) as exc:
        build_benchmark_export_files(
            source_sha=SOURCE_SHA,
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
            forecast_rows=forecasts,
            observation_rows=observations,
        )
    assert exc.value.reason_code == "MISSING_DETERMINISTIC_PROVIDER"
