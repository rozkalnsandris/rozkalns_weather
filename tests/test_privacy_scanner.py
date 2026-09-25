from __future__ import annotations

import json
from pathlib import Path

import pytest

from rozkalns_weather.privacy_scanner import (
    ARTIFACT_KINDS,
    require_github_safe_artifact,
    scan_github_safe_artifact,
)


def _codes(result):
    return {finding.reason_code for finding in result.findings}


def test_safe_public_station_metadata_passes() -> None:
    payload = {
        "location_id": "station_05480",
        "location": {"latitude": 51.5, "longitude": 7.7},
        "provider": "dwd",
        "metadata": {
            "station_name": "Werl",
            "legacy_reference": "station_10416",
            "latency_ms": 125,
            "token_count": 4,
        },
    }

    result = scan_github_safe_artifact("api_snapshot", payload)

    assert result.status == "PASS"
    assert result.github_safe is True
    assert result.findings == ()


def test_legacy_public_station_metadata_is_not_private_home() -> None:
    payload = {
        "station_id": "station_10416",
        "lat": 51.0,
        "lon": 7.0,
        "classification": "legacy_mosmix_reference",
    }
    assert scan_github_safe_artifact("report", payload).status == "PASS"


def test_nested_private_coordinate_field_blocks_without_echoing_value() -> None:
    sensitive = "51.123456"
    payload = {"outer": {"config": {"HOME_LAT": sensitive}}}

    result = scan_github_safe_artifact("rollout_evidence", payload)
    encoded = json.dumps(result.to_dict(), sort_keys=True)

    assert result.status == "BLOCKED"
    assert "PRIVATE_HOME_COORDINATE_FIELD" in _codes(result)
    assert sensitive not in encoded


def test_unscoped_coordinate_pair_blocks_but_does_not_echo_coordinates() -> None:
    payload = {"location": {"latitude": 50.111111, "longitude": 8.222222}}

    result = scan_github_safe_artifact("diagnostics_bundle", payload)
    encoded = json.dumps(result.to_dict(), sort_keys=True)

    assert "PRIVATE_OR_UNSCOPED_COORDINATE_PAIR" in _codes(result)
    assert "50.111111" not in encoded
    assert "8.222222" not in encoded


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("https://user:pass@example.invalid/path", "URL_EMBEDDED_CREDENTIAL"),
        ("https://example.invalid/data?access_token=fake-test-value", "URL_QUERY_CREDENTIAL"),
        ("API_KEY=fake-test-value", "CREDENTIAL_OR_SECRET_TEXT"),
        ("/home/example/private/weather.db", "PRIVATE_RUNTIME_PATH_TEXT"),
    ],
)
def test_sensitive_text_patterns_block_without_recording_source_value(
    text: str, reason: str
) -> None:
    result = scan_github_safe_artifact("benchmark_export", {"note": text})
    encoded = json.dumps(result.to_dict(), sort_keys=True)

    assert reason in _codes(result)
    assert text not in encoded


@pytest.mark.parametrize(
    "field",
    [
        "password",
        "client_secret",
        "private_key",
        "credentials",
        "runtime_path",
        "database_path",
        "raw_logs",
        "home_address",
    ],
)
def test_structured_prohibited_fields_are_blocked(field: str) -> None:
    result = scan_github_safe_artifact(
        "reproducibility_receipt", {"metadata": {field: "synthetic-fixture"}}
    )
    assert result.status == "BLOCKED"


def test_placeholder_credential_fields_are_allowed() -> None:
    payload = {
        "api_key": "<redacted>",
        "access_token": "${TOKEN}",
        "note": "API_KEY=${API_KEY}",
    }
    result = scan_github_safe_artifact("diagnostics_bundle", payload)
    assert result.status == "PASS"


def test_reason_output_is_deterministic_and_sanitized() -> None:
    first = {
        "z": {"password": "synthetic-one"},
        "a": {"runtime_path": "/home/example/private/app.db"},
    }
    second = {
        "a": {"runtime_path": "/home/example/private/app.db"},
        "z": {"password": "synthetic-one"},
    }

    left = scan_github_safe_artifact("report", first).to_dict()
    right = scan_github_safe_artifact("report", second).to_dict()

    assert left == right
    encoded = json.dumps(left, sort_keys=True)
    assert "synthetic-one" not in encoded
    assert "/home/example/private/app.db" not in encoded


@pytest.mark.parametrize("artifact_kind", sorted(ARTIFACT_KINDS))
def test_all_required_artifact_classes_use_same_gate(artifact_kind: str) -> None:
    payload = {"status": "ok", "location_id": "station_05480"}
    assert scan_github_safe_artifact(artifact_kind, payload).status == "PASS"


def test_unknown_artifact_kind_fails_closed() -> None:
    result = scan_github_safe_artifact("unknown", {"status": "ok"})
    assert result.status == "BLOCKED"
    assert _codes(result) == {"UNSUPPORTED_ARTIFACT_KIND"}


def test_require_helper_raises_with_reason_codes_only() -> None:
    secret = "synthetic-should-not-appear"
    with pytest.raises(ValueError) as exc:
        require_github_safe_artifact("api_snapshot", {"access_token": secret})
    message = str(exc.value)
    assert "CREDENTIAL_OR_SECRET_FIELD" in message
    assert secret not in message


def test_require_helper_returns_machine_evidence_for_safe_payload() -> None:
    evidence = require_github_safe_artifact(
        "benchmark_export",
        {"location_id": "station_05480", "provider": "dwd"},
    )
    assert evidence == {
        "schema": "rozkalns.weather.privacy-scan.v1",
        "artifact_kind": "benchmark_export",
        "status": "PASS",
        "github_safe": True,
        "findings": [],
    }


def test_machine_contract_matches_source_constants() -> None:
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "privacy-scanner-v1.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    assert contract["scanner_schema"] == "rozkalns.weather.privacy-scan.v1"
    assert set(contract["artifact_kinds"]) == set(ARTIFACT_KINDS)

    source_reason_codes = {
        "CREDENTIAL_OR_SECRET_FIELD",
        "CREDENTIAL_OR_SECRET_TEXT",
        "PRIVATE_ADDRESS_FIELD",
        "PRIVATE_HOME_COORDINATE_FIELD",
        "PRIVATE_OR_UNSCOPED_COORDINATE_PAIR",
        "PRIVATE_RUNTIME_PATH_FIELD",
        "PRIVATE_RUNTIME_PATH_TEXT",
        "RAW_PRIVATE_LOG_FIELD",
        "UNSUPPORTED_ARTIFACT_KIND",
        "URL_EMBEDDED_CREDENTIAL",
        "URL_QUERY_CREDENTIAL",
    }
    assert set(contract["reason_codes"]) == source_reason_codes
    assert contract["execution"]["secret_retrieval_required"] is False
    assert contract["execution"]["runtime_mutation_authority"] is False
