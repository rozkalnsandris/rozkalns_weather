from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
import json
from pathlib import Path

import pytest

from rozkalns_weather.canonical_serialization import (
    CANONICAL_SERIALIZATION_CONTRACT,
    CanonicalSerializationError,
    canonical_contract_evidence,
    canonical_json_bytes,
    canonical_sha256,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "canonical_serialization_cases.json"


class ExampleState(Enum):
    PASS = "PASS"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_equivalent_fixture_payloads_have_identical_bytes_and_checksums() -> None:
    fixture = _fixture()
    for case in fixture["equivalent_pairs"]:
        left = canonical_json_bytes(case["left"])
        right = canonical_json_bytes(case["right"])
        assert left == right, case["name"]
        assert canonical_sha256(case["left"]) == canonical_sha256(case["right"]), case["name"]
        if "expected_sha256" in case:
            assert canonical_sha256(case["left"]) == case["expected_sha256"]


def test_first_fixture_has_stable_versioned_byte_representation() -> None:
    payload = _fixture()["equivalent_pairs"][0]["left"]
    assert canonical_json_bytes(payload) == (
        '{"checked_at_utc":"2026-09-25T10:00:00Z","negative_zero":0,'
        '"value":1e-6,"z":[true,null,"Å"]}\n'
    ).encode("utf-8")


def test_utc_named_schema_metadata_tokens_remain_plain_strings() -> None:
    payload = {
        "tables": {
            "forecast_runs": {
                "init_time_utc": "TEXT",
                "retrieved_at_utc": "TEXT",
            }
        }
    }
    assert canonical_json_bytes(payload) == (
        '{"tables":{"forecast_runs":{"init_time_utc":"TEXT","retrieved_at_utc":"TEXT"}}}\n'
    ).encode("utf-8")


def test_materially_different_fixture_payloads_change_identity() -> None:
    fixture = _fixture()
    for case in fixture["different_pairs"]:
        assert canonical_sha256(case["left"]) != canonical_sha256(case["right"]), case["name"]


def test_nested_types_enum_tuple_and_utc_datetime_are_canonical() -> None:
    payload = {
        "state": ExampleState.PASS,
        "items": (3, 2, 1),
        "checked_at_utc": datetime(2026, 9, 25, 10, 0, 0, 120000, tzinfo=timezone.utc),
        "nested": {"enabled": True, "value": None},
    }
    assert canonical_json_bytes(payload) == (
        '{"checked_at_utc":"2026-09-25T10:00:00.12Z","items":[3,2,1],'
        '"nested":{"enabled":true,"value":null},"state":"PASS"}\n'
    ).encode("utf-8")


def test_finite_float_policy_preserves_value_precision_without_display_rounding() -> None:
    raw_value = 1.2345678901234567
    encoded = canonical_json_bytes({"value": raw_value})
    assert b"1.2345678901234567" in encoded
    assert canonical_sha256({"value": raw_value}) != canonical_sha256({"value": 1.23})
    assert canonical_json_bytes({"value": -0.0}) == b'{"value":0}\n'
    assert canonical_json_bytes({"value": 1e20}) == b'{"value":1e20}\n'


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_fail_closed(value: float) -> None:
    with pytest.raises(CanonicalSerializationError) as excinfo:
        canonical_json_bytes({"value": value})
    assert excinfo.value.reason_code == "NON_FINITE_NUMBER"


def test_unsupported_numeric_representation_fails_closed() -> None:
    with pytest.raises(CanonicalSerializationError) as excinfo:
        canonical_json_bytes({"value": Decimal("1.25")})
    assert excinfo.value.reason_code == "UNSUPPORTED_NUMERIC_TYPE"


def test_invalid_utc_semantics_and_non_string_keys_fail_closed() -> None:
    with pytest.raises(CanonicalSerializationError) as timestamp_error:
        canonical_json_bytes({"retrieved_at_utc": "2026-09-25T12:00:00+02:00"})
    assert timestamp_error.value.reason_code == "INVALID_UTC_TIMESTAMP"

    with pytest.raises(CanonicalSerializationError) as datetime_error:
        canonical_json_bytes(
            {"checked_at_utc": datetime(2026, 9, 25, 12, 0, tzinfo=timezone(timedelta(hours=2)))}
        )
    assert datetime_error.value.reason_code == "INVALID_UTC_TIMESTAMP"

    with pytest.raises(CanonicalSerializationError) as key_error:
        canonical_json_bytes({1: "not-a-json-object-key"})
    assert key_error.value.reason_code == "NON_STRING_OBJECT_KEY"


def test_contract_evidence_declares_no_domain_rounding() -> None:
    evidence = canonical_contract_evidence()
    assert evidence["contract"] == CANONICAL_SERIALIZATION_CONTRACT
    assert evidence["numeric_policy"]["finite_only"] is True
    assert evidence["numeric_policy"]["domain_rounding"] is False
    assert evidence["raw_provider_precision_preserved"] is True
