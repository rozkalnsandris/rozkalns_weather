from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from rozkalns_weather.models import ForecastRun, ForecastValue
from rozkalns_weather.weathernext_ensemble import (
    MemberSourceEvidence, admit_members, verification_eligibility, verify_member_slice,
)

INIT = datetime(2026, 9, 1, tzinfo=timezone.utc)
VALID = INIT + timedelta(hours=6)
EVIDENCE = MemberSourceEvidence("fixture-v1", "a" * 64, "fixture-native", "0p1",
                                ("member_0", "member_1"), "b" * 64, True)


def candidate(variable="temperature_2m"):
    rain = variable == "precipitation_1h"
    return ForecastRun(
        provider="weathernext3", model_provider="Google", model_name="WeatherNext 3",
        model_version="fixture-v1", init_time_utc=INIT, retrieved_at_utc=INIT + timedelta(hours=3),
        source_surface="fixture-native", raw_payload_hash="c" * 64,
        source_metadata={"location_id": "station_10416", "resolution": "0p1",
                         "schema_fingerprint": "a" * 64, "member_origin": "provider_native",
                         "member_evidence_sha256": "b" * 64, "ensemble_size": 2},
        values=tuple(ForecastValue(VALID, 6, variable, v, "mm" if rain else "degC",
                                  statistic=f"member_{i}",
                                  accumulation_window_minutes=60 if rain else None)
                     for i, v in enumerate((0.0, 1.0) if rain else (10.0, 12.0))),
    )


def eligibility(run, evidence=EVIDENCE, variable="temperature_2m"):
    return verification_eligibility([run], evidence=evidence, valid_time_utc=VALID, variable=variable)


def test_complete_members_and_order_invariance():
    run = candidate()
    assert admit_members([run], evidence=EVIDENCE, valid_time_utc=VALID,
                         variable="temperature_2m") == (10, 12)
    assert admit_members([replace(run, values=run.values[::-1])], evidence=EVIDENCE,
                         valid_time_utc=VALID, variable="temperature_2m") == (10, 12)
    assert eligibility(run)["crps"] is True
    assert eligibility(run)["brier"] is False


@pytest.mark.parametrize("change,reason", [
    (lambda r: replace(r, values=r.values[:1]), "MEMBER_SET_INCOMPLETE"),
    (lambda r: replace(r, values=r.values + r.values[:1]), "MEMBER_DUPLICATE"),
    (lambda r: replace(r, model_version="other"), "MODEL_VERSION_DRIFT"),
    (lambda r: replace(r, raw_payload_hash=None), "PROVENANCE_MISSING"),
    (lambda r: replace(r, source_metadata={**r.source_metadata, "resolution": "0p05"}), "SOURCE_IDENTITY_DRIFT"),
    (lambda r: replace(r, source_metadata={**r.source_metadata, "member_origin": "quantile_inferred"}), "NATIVE_MEMBERS_UNVERIFIED"),
    (lambda r: replace(r, source_metadata={**r.source_metadata, "location_id": "home"}), "LOCATION_INCOMPATIBLE"),
    (lambda r: replace(r, source_metadata={**r.source_metadata, "ensemble_size": 3}), "ENSEMBLE_SIZE_MISMATCH"),
    (lambda r: replace(r, retrieved_at_utc=INIT-timedelta(hours=1)), "TEMPORAL_PROVENANCE_INVALID"),
    (lambda r: replace(r, values=(replace(r.values[0], lead_hours=7), r.values[1])), "VALUE_OR_LEAD_INVALID"),
    (lambda r: replace(r, values=tuple(replace(v, statistic=s) for v, s in zip(r.values, ("p10", "p90")))), "NOT_NATIVE_MEMBER"),
])
def test_fail_closed_with_explicit_summary_fallback(change, reason):
    result = eligibility(change(candidate()))
    assert result["state"] == "BLOCKED"
    assert result["reason_code"] == reason
    assert all(result[k] is False for k in ("crps", "empirical_interval", "brier", "reliability", "event_probability"))
    assert result["summary_quantiles"] == "separate_validation_required"


def test_missing_members_and_unverified_source():
    assert verification_eligibility([], evidence=EVIDENCE, valid_time_utc=VALID,
                                    variable="temperature_2m")["reason_code"] == "MEMBERS_UNAVAILABLE"
    assert eligibility(candidate(), replace(EVIDENCE, native_members_verified=False))["reason_code"] == "NATIVE_MEMBERS_UNVERIFIED"
    assert eligibility(candidate(), variable="invented_variable")["reason_code"] == "VARIABLE_UNSUPPORTED"
    assert eligibility(candidate(), replace(EVIDENCE, member_ids=("p10", "p90")))["reason_code"] == "MEMBER_ROSTER_INVALID"


def test_mixed_runs_rejected():
    run = candidate()
    second = replace(run, values=run.values[1:], init_time_utc=INIT-timedelta(hours=1))
    result = verification_eligibility([replace(run, values=run.values[:1]), second],
                                      evidence=EVIDENCE, valid_time_utc=VALID, variable="temperature_2m")
    assert result["reason_code"] == "MIXED_RUN_PROVENANCE"


@pytest.mark.parametrize("variable,unit,observed,window", [
    ("temperature_2m", "degC", 11.0, None), ("precipitation_1h", "mm", 1.0, 60),
])
def test_metrics_use_only_admitted_members_and_matched_truth(variable, unit, observed, window):
    args = dict(evidence=EVIDENCE, valid_time_utc=VALID, variable=variable, observed=observed,
                observation_location_id="station_10416", observation_time_utc=VALID,
                observation_unit=unit, observation_window_minutes=window)
    result = verify_member_slice([candidate(variable)], **args)
    assert result["n"] == 1
    assert result["crps_score"] == pytest.approx(0.25 if window else 0.5)
    assert result["interval"]["width"] > 0
    if window:
        assert result["brier_score"]["brier_score"] == 0.25
        assert sum(b["n"] for b in result["reliability_bins"]) == 1
    with pytest.raises(ValueError, match="TRUTH_INCOMPATIBLE"):
        verify_member_slice([candidate(variable)], **{**args, "observation_location_id": "home"})
