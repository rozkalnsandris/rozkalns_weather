from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rozkalns_weather.corpus_value_integrity import audit_corpus_values
from rozkalns_weather.missing_values import (
    MissingValueError,
    normalize_missing_value,
    summarize_missingness,
)
from rozkalns_weather.provider_health import classify_public_provider_health
from rozkalns_weather.verification import ErrorPair, ProbabilityPair
from rozkalns_weather.verification_missingness import (
    ExpectedVerificationSample,
    build_verification_missingness_report,
)
from rozkalns_weather.verification_value_missingness import (
    attach_value_missingness,
    build_value_missingness_evidence,
)

FIXTURES = Path(__file__).parent / "fixtures" / "missing_value_normalization.json"
NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)


def _fixture_value(case: dict[str, object]) -> tuple[object, bool, bool]:
    kind = str(case["kind"])
    if kind == "none":
        return None, True, False
    if kind == "nan":
        return float("nan"), True, False
    if kind == "pos_inf":
        return float("inf"), True, False
    if kind == "neg_inf":
        return float("-inf"), True, False
    if kind == "absent":
        return None, False, False
    if kind == "transport_omitted":
        return None, True, True
    return case.get("value"), True, False


def test_fixture_matrix_classifies_missingness_without_confusing_zero() -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    for case in payload["cases"]:
        value, field_present, transport_omitted = _fixture_value(case)
        evidence = normalize_missing_value(
            value,
            provider=str(case["provider"]),
            field=str(case["field"]),
            field_present=field_present,
            transport_omitted=transport_omitted,
            provider_sentinels=tuple(case.get("sentinels", [])),
        )
        assert evidence.state == case["expected_state"], case["name"]
        assert evidence.reason_code == case["expected_reason"], case["name"]
        assert evidence.imputed is False
        if evidence.state == "present" and isinstance(value, (int, float)):
            assert evidence.numeric_value == float(value)


def test_non_finite_metric_inputs_fail_before_verification_scoring() -> None:
    with pytest.raises(MissingValueError) as exc:
        ErrorPair("icon_d2", "fixture", 12.0, float("nan"), 10.0)
    assert exc.value.reason_code == "MISSING_NON_FINITE_NUMERIC"

    with pytest.raises(MissingValueError) as exc:
        ProbabilityPair("icon_d2", 12.0, float("inf"), 1.0)
    assert exc.value.reason_code == "MISSING_NON_FINITE_NUMERIC"

    zero = ProbabilityPair("icon_d2", 12.0, 0.0, 0.0)
    assert zero.probability == 0.0


def test_provider_health_attaches_missingness_without_overwriting_freshness() -> None:
    missing = normalize_missing_value(
        None, provider="icon_d2", field="temperature_2m"
    )
    summary = summarize_missingness([missing])
    health = classify_public_provider_health(
        "icon_d2",
        {
            "state": "ok",
            "last_attempt_at_utc": "2026-09-25T11:40:00Z",
            "last_success_at_utc": "2026-09-25T11:40:00Z",
        },
        {
            "last_init_time_utc": "2026-09-25T11:00:00Z",
            "last_retrieved_at_utc": "2026-09-25T11:40:00Z",
        },
        now=NOW,
        value_missingness_summary=summary,
    )
    assert health["freshness_state"] == "fresh"
    assert health["reason_code"] == "FRESH"
    assert health["value_missingness"]["state"] == "DEGRADED"
    assert health["value_missingness"]["reason_counts"]["MISSING_UPSTREAM_NULL"] == 1


def test_verification_missingness_report_preserves_granular_normalization_reason() -> None:
    rows = [
        ExpectedVerificationSample(
            sample_id="a",
            provider="icon_d2",
            model_version="icon-v1",
            lead_hours=12.0,
            variable="temperature_2m",
            valid_time_utc="2026-09-25T12:00:00Z",
            init_time_utc="2026-09-25T00:00:00Z",
            verification_included=False,
        ),
        ExpectedVerificationSample(
            sample_id="a",
            provider="ecmwf_ifs",
            model_version="ifs-v1",
            lead_hours=12.0,
            variable="temperature_2m",
            valid_time_utc="2026-09-25T12:00:00Z",
            init_time_utc="2026-09-25T00:00:00Z",
        ),
    ]
    base = build_verification_missingness_report(rows)
    normalized = normalize_missing_value(
        float("nan"), provider="icon_d2", field="temperature_2m"
    )
    value_evidence = build_value_missingness_evidence([("a", normalized)])
    report = attach_value_missingness(base, value_evidence)

    assert report["value_normalization"]["reason_code"] == "VALUE_NORMALIZATION_EXCLUDED"
    assert report["value_normalization"]["normalization_reason_counts"] == {
        "MISSING_NON_FINITE_NUMERIC": 1
    }
    assert report["automatic_weighting"] is False


def test_corpus_value_integrity_is_read_only_and_blocks_missing_values() -> None:
    report = audit_corpus_values(
        forecast_values=[
            {"provider": "icon_d2", "variable": "precipitation_1h", "value": 0.0},
            {"provider": "icon_d2", "variable": "temperature_2m", "value": float("inf")},
            {"provider": "ecmwf_ifs", "variable": "temperature_2m", "value": -9999.0},
        ],
        observations=[
            {"source_provider": "DWD", "variable": "wind_speed_10m", "value": 0.0},
            {"source_provider": "DWD", "variable": "temperature_2m"},
        ],
        forecast_provider_sentinels={"ecmwf_ifs": (-9999.0,)},
    )
    assert report["state"] == "BLOCKED"
    assert report["read_only"] is True
    assert report["repair_performed"] is False
    assert report["imputation_performed"] is False
    assert report["reason_counts"] == {
        "MISSING_ABSENT_FIELD": 1,
        "MISSING_NON_FINITE_NUMERIC": 1,
        "MISSING_PROVIDER_SENTINEL": 1,
    }
    assert report["finding_count"] == 3
