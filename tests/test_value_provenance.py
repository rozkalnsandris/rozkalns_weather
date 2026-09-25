from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from rozkalns_weather.value_provenance import (
    VALUE_PROVENANCE_CONTRACT,
    ValueProvenanceError,
    build_forecast_value_trace,
    build_truth_value_trace,
    build_verification_value_trace,
    forecast_trace_evidence,
    validate_trace_bundle,
)


FIXTURE = Path(__file__).parent / "fixtures" / "value_provenance_cases.json"


def _cases() -> dict[str, dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _text(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def test_home_forecast_trace_is_deterministic_and_privacy_safe() -> None:
    row = _cases()["home_forecast"]
    first = build_forecast_value_trace(row)
    second = build_forecast_value_trace(deepcopy(row))

    assert first == second
    assert first["contract"] == VALUE_PROVENANCE_CONTRACT
    assert first["kind"] == "forecast_value"
    assert first["state"] == "PASS"
    assert first["location"] == {
        "id": "home",
        "scope": "private_home",
        "coordinates_exposed": False,
    }
    assert first["snapshot"]["id"] == "a" * 64
    assert first["source"]["provider"] == "ecmwf_ifs"
    assert first["source"]["model_version"] == "2026-09"
    assert first["time"]["lead_hours"] == 12.0
    assert first["normalized_value"]["statistic"] == "deterministic"
    assert len(first["trace_identity_sha256"]) == 64

    serialized = _text(first).lower()
    for forbidden in ("home_lat", "home_lon", "latitude", "longitude", "database_path", "password", "credential", "raw_log"):
        assert forbidden not in serialized


def test_station_verification_trace_binds_forecast_truth_metric_and_receipt() -> None:
    cases = _cases()
    trace = build_verification_value_trace(
        cases["station_forecast"],
        cases["station_truth"],
        metric_identity={"name": "absolute_error", "version": 1, "comparison_mode": "station_run_skill"},
        report_lineage=cases["report_lineage"],
    )

    assert trace["state"] == "PASS"
    assert trace["forecast"]["location"]["id"] == "station_05480"
    assert trace["truth"]["source"] == {"provider": "DWD", "station_id": "05480"}
    assert trace["metric_identity"]["name"] == "absolute_error"
    assert trace["report_lineage"]["lineage_identity_sha256"] == "c" * 64
    assert trace["forecast_trace_identity_sha256"] == trace["forecast"]["trace_identity_sha256"]
    assert trace["truth_trace_identity_sha256"] == trace["truth"]["trace_identity_sha256"]


def test_truth_trace_has_exact_station_time_variable_identity() -> None:
    truth = build_truth_value_trace(_cases()["station_truth"])
    assert truth["location"]["id"] == "station_05480"
    assert truth["time"]["observed_at_utc"] == "2026-09-25T12:00:00Z"
    assert truth["normalized_value"]["variable"] == "temperature_2m"
    assert truth["normalized_value"]["unit"] == "degC"


def test_missing_snapshot_id_is_blocked_with_stable_reason_code() -> None:
    row = deepcopy(_cases()["home_forecast"])
    del row["raw_payload_hash"]

    with pytest.raises(ValueProvenanceError) as exc:
        build_forecast_value_trace(row)
    assert exc.value.reason_code == "MISSING_SNAPSHOT_ID"

    evidence = forecast_trace_evidence(row)
    assert evidence["state"] == "BLOCKED"
    assert evidence["reason_codes"] == ["MISSING_SNAPSHOT_ID"]
    assert evidence["location"]["coordinates_exposed"] is False


def test_broken_lineage_is_detected_after_trace_tampering() -> None:
    trace = build_forecast_value_trace(_cases()["station_forecast"])
    trace["normalized_value"]["value"] = 99.0

    with pytest.raises(ValueProvenanceError) as exc:
        validate_trace_bundle([trace])
    assert exc.value.reason_code == "BROKEN_LINEAGE"


def test_mixed_model_versions_are_rejected_per_provider() -> None:
    first_row = _cases()["station_forecast"]
    second_row = deepcopy(first_row)
    second_row["model_version"] = "2026-10"
    second_row["raw_payload_hash"] = "d" * 64

    with pytest.raises(ValueProvenanceError) as exc:
        validate_trace_bundle([
            build_forecast_value_trace(first_row),
            build_forecast_value_trace(second_row),
        ])
    assert exc.value.reason_code == "MIXED_MODEL_VERSIONS"


def test_mismatched_verification_receipts_are_rejected() -> None:
    cases = _cases()
    other_receipt = deepcopy(cases["report_lineage"])
    other_receipt["lineage_identity_sha256"] = "d" * 64
    second_row = deepcopy(cases["station_forecast"])
    second_row["provider"] = "ecmwf_ifs"
    second_row["model_provider"] = "ECMWF"
    second_row["model_name"] = "IFS"
    second_row["raw_payload_hash"] = "e" * 64

    with pytest.raises(ValueProvenanceError) as exc:
        validate_trace_bundle([
            build_forecast_value_trace(cases["station_forecast"], report_lineage=cases["report_lineage"]),
            build_forecast_value_trace(second_row, report_lineage=other_receipt),
        ])
    assert exc.value.reason_code == "VERIFICATION_RECEIPT_MISMATCH"


def test_verification_trace_rejects_mismatched_truth_identity() -> None:
    cases = _cases()
    truth = deepcopy(cases["station_truth"])
    truth["observed_at_utc"] = "2026-09-25T13:00:00Z"

    with pytest.raises(ValueProvenanceError) as exc:
        build_verification_value_trace(
            cases["station_forecast"],
            truth,
            metric_identity={"name": "absolute_error"},
        )
    assert exc.value.reason_code == "BROKEN_LINEAGE"


def test_trace_bundle_never_emits_combined_weighting() -> None:
    traces = [
        build_forecast_value_trace(_cases()["home_forecast"]),
        build_forecast_value_trace(_cases()["station_forecast"]),
    ]
    result = validate_trace_bundle(traces)
    assert result["state"] == "PASS"
    text = _text(result).lower()
    assert "combined" not in text
    assert result["privacy"]["coordinates_exposed"] is False
