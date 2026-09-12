from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from rozkalns_weather.private_runtime_activation import evaluate_private_runtime_activation
from rozkalns_weather.weathernext_access import expected_required_schema_fingerprint


NOW = datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)
SOURCE_SHA = "a" * 40
SNAPSHOT_SHA = "b" * 64


def _evidence() -> dict[str, object]:
    schema = expected_required_schema_fingerprint()
    return {
        "schema_version": 1,
        "source_sha": SOURCE_SHA,
        "checked_at_utc": "2026-09-12T20:00:00Z",
        "runtime_mode": "private-research",
        "home": {
            "coordinates_present": True,
            "exact_coordinates_exposed": False,
            "forecast_display_enabled": True,
            "measured_home_accuracy_claimed": False,
        },
        "credentials": {
            "google_auth_present": True,
            "project_dataset_config_present": True,
            "credential_material_exposed": False,
        },
        "weathernext_access": {
            "verified": True,
            "state": "canary_ready_for_snapshot",
            "verified_at_utc": "2026-09-12T19:30:00Z",
            "provider": "weathernext3",
            "model_name": "WeatherNext 3",
            "model_version": "3.0.0",
            "schema_fingerprint_sha256": schema,
        },
        "accepted_snapshot": {
            "present": True,
            "provenance_complete": True,
            "provider": "weathernext3",
            "model_name": "WeatherNext 3",
            "model_version": "3.0.0",
            "schema_fingerprint_sha256": schema,
            "product_surfaces": ["0p05", "0p1"],
            "statistics": ["mean", "p10", "p25", "p50", "p75", "p90"],
            "snapshot_identity_sha256": SNAPSHOT_SHA,
            "real_values_exposed": False,
        },
        "production_corpus": {
            "schema_ready": True,
            "station_10416_truth_ready": True,
            "public_forecast_corpus_ready": True,
            "immutable_forecast_history_ready": True,
        },
        "ui_safety": {
            "station_measured_accuracy_location_id": "station_10416",
            "home_display_role": "forecast_only",
            "official_warning_authority": "DWD",
            "model_warning_authority": False,
        },
        "authority": {
            "live_authority_granted": False,
            "production_data_authority_granted": False,
            "credential_mutation_authority_granted": False,
            "runtime_mutation_performed": False,
        },
    }


def test_private_runtime_activation_descriptor_keeps_source_full_non_live() -> None:
    payload = json.loads(Path("deploy/private-runtime-activation.json").read_text())
    assert payload["contract"] == "private-home-weathernext-runtime-activation.v1"
    assert payload["location_semantics"]["station_10416"]["measured_accuracy_allowed"] is True
    assert payload["location_semantics"]["home"]["measured_accuracy_allowed"] is False
    assert payload["ui_safety"]["official_severe_weather_warning_authority"] == "DWD"
    assert payload["authority"]["source_auto_full_authorizes_credentials"] is False
    assert payload["authority"]["source_auto_full_authorizes_real_bigquery_reads"] is False
    assert payload["authority"]["source_auto_full_authorizes_rpi5_deploy_or_restart"] is False
    assert payload["authority"]["source_auto_full_authorizes_production_data_writes"] is False


def test_complete_sanitized_evidence_is_source_ready_only() -> None:
    result = evaluate_private_runtime_activation(_evidence(), now=NOW)
    assert result["state"] == "PASS"
    assert result["ready"] is True
    assert result["blockers"] == []
    assert result["location_semantics"] == {
        "station_10416_measured_accuracy": True,
        "home_forecast_only": True,
    }
    assert result["warning_authority"] == "DWD"
    assert result["authority"]["live_authority_granted"] is False
    assert result["authority"]["production_data_authority_granted"] is False
    rendered = json.dumps(result)
    assert "HOME_LAT" not in rendered
    assert "HOME_LON" not in rendered


def test_missing_home_credentials_and_corpus_prerequisites_fail_closed() -> None:
    evidence = _evidence()
    evidence["home"]["coordinates_present"] = False
    evidence["credentials"]["google_auth_present"] = False
    evidence["credentials"]["project_dataset_config_present"] = False
    evidence["production_corpus"]["schema_ready"] = False
    evidence["production_corpus"]["station_10416_truth_ready"] = False
    evidence["production_corpus"]["public_forecast_corpus_ready"] = False
    result = evaluate_private_runtime_activation(evidence, now=NOW)
    assert result["state"] == "BLOCKED"
    assert {
        "HOME_COORDINATES_MISSING",
        "GOOGLE_AUTH_MISSING",
        "PROJECT_DATASET_CONFIG_MISSING",
        "PRODUCTION_SCHEMA_NOT_READY",
        "STATION_TRUTH_NOT_READY",
        "PUBLIC_CORPUS_NOT_READY",
    }.issubset(set(result["blockers"]))


def test_stale_access_and_model_schema_drift_fail_closed() -> None:
    evidence = _evidence()
    evidence["weathernext_access"]["verified_at_utc"] = (
        NOW - timedelta(days=2)
    ).isoformat().replace("+00:00", "Z")
    evidence["weathernext_access"]["model_version"] = "3.0.1"
    evidence["weathernext_access"]["schema_fingerprint_sha256"] = "c" * 64
    result = evaluate_private_runtime_activation(evidence, now=NOW)
    assert result["state"] == "BLOCKED"
    assert "ACCESS_EVIDENCE_STALE" in result["blockers"]
    assert "MODEL_IDENTITY_DRIFT" in result["blockers"]
    assert "SCHEMA_FINGERPRINT_DRIFT" in result["blockers"]


def test_snapshot_provenance_and_surface_contract_are_exact() -> None:
    evidence = _evidence()
    evidence["accepted_snapshot"]["provenance_complete"] = False
    evidence["accepted_snapshot"]["product_surfaces"] = ["0p1", "0p05"]
    evidence["accepted_snapshot"]["statistics"] = ["mean", "p50"]
    evidence["accepted_snapshot"]["snapshot_identity_sha256"] = "not-a-hash"
    result = evaluate_private_runtime_activation(evidence, now=NOW)
    assert {
        "SNAPSHOT_PROVENANCE_INCOMPLETE",
        "SNAPSHOT_SURFACE_DRIFT",
        "SNAPSHOT_STATISTIC_DRIFT",
        "SNAPSHOT_IDENTITY_INVALID",
    }.issubset(set(result["blockers"]))


def test_home_accuracy_and_dwd_warning_authority_cannot_drift() -> None:
    evidence = _evidence()
    evidence["home"]["measured_home_accuracy_claimed"] = True
    evidence["ui_safety"]["home_display_role"] = "measured_accuracy"
    evidence["ui_safety"]["official_warning_authority"] = "WeatherNext 3"
    evidence["ui_safety"]["model_warning_authority"] = True
    result = evaluate_private_runtime_activation(evidence, now=NOW)
    assert result["state"] == "BLOCKED"
    assert "HOME_ACCURACY_SEMANTICS_VIOLATION" in result["blockers"]
    assert "DWD_WARNING_AUTHORITY_VIOLATION" in result["blockers"]


def test_activation_evidence_rejects_private_or_unknown_fields() -> None:
    evidence = _evidence()
    evidence["home_lat"] = 51.5
    with pytest.raises(ValueError, match="private evidence field forbidden"):
        evaluate_private_runtime_activation(evidence, now=NOW)

    evidence = _evidence()
    evidence["unexpected"] = True
    with pytest.raises(ValueError, match="schema mismatch"):
        evaluate_private_runtime_activation(evidence, now=NOW)


def test_activation_evidence_cannot_expand_authority_or_expose_values() -> None:
    evidence = _evidence()
    evidence["authority"]["live_authority_granted"] = True
    evidence["accepted_snapshot"]["real_values_exposed"] = True
    evidence["home"]["exact_coordinates_exposed"] = True
    evidence["credentials"]["credential_material_exposed"] = True
    result = evaluate_private_runtime_activation(evidence, now=NOW)
    assert result["state"] == "BLOCKED"
    assert {
        "AUTHORITY_EXPANSION",
        "REAL_VALUES_EXPOSED",
        "HOME_COORDINATES_EXPOSED",
        "CREDENTIAL_MATERIAL_EXPOSED",
    }.issubset(set(result["blockers"]))
