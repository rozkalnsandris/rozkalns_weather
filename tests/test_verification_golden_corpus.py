from __future__ import annotations

import json
from pathlib import Path

import pytest

from rozkalns_weather.leaderboard import SkillSample, common_sample_leaderboard
from rozkalns_weather.probabilistic import (
    EnsembleVerificationPair,
    brier_from_members,
    ensemble_crps,
    event_probability,
    summarize_crps,
    weighted_interval_score,
)
from rozkalns_weather.semantics import (
    metric_eligibility,
    semantic_identity,
    validate_semantics,
)
from rozkalns_weather.verification import (
    ErrorPair,
    ProbabilityPair,
    brier_score,
    lead_bucket,
    reliability_bins,
    summarize,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "verification_golden_corpus.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_golden_point_metrics_interval_coverage_and_missingness() -> None:
    data = _fixture()["point_and_interval"]
    pairs = [
        ErrorPair(
            provider=data["provider"],
            model_version=item["model_version"],
            lead_hours=item["lead_hours"],
            forecast=item["forecast"],
            observed=item["observed"],
            p10=item["p10"],
            p90=item["p90"],
        )
        for item in data["pairs"]
    ]
    result = summarize(pairs, expected_n=data["expected_n"])
    expected = data["expected"]

    assert result["n"] == expected["n"]
    for name in ("mae", "rmse", "bias", "p10_p90_coverage"):
        assert result[name] == pytest.approx(expected[name])
    assert result["coverage_n"] == expected["coverage_n"]
    assert result["sample_sufficiency_state"] == expected["sample_sufficiency_state"]
    assert result["missingness"] == expected["missingness"]


def test_golden_lead_bucket_boundaries() -> None:
    for case in _fixture()["lead_buckets"]:
        assert lead_bucket(case["lead_hours"]) == case["expected"]


def test_genuine_ensemble_crps_and_wis_are_frozen() -> None:
    data = _fixture()["ensemble_temperature"]
    pairs = []
    for case in data["cases"]:
        members = tuple(case["members"])
        observed = case["observed"]
        assert ensemble_crps(members, observed) == pytest.approx(case["expected_crps"])
        assert weighted_interval_score(members, observed) == pytest.approx(case["expected_wis"])
        pairs.append(
            EnsembleVerificationPair(
                provider=data["provider"],
                model_version=data["model_version"],
                lead_hours=18,
                members=members,
                observed=observed,
            )
        )

    summary = summarize_crps(pairs)
    assert summary["n"] == len(data["cases"])
    assert summary["mean_crps"] == pytest.approx(data["expected_mean_crps"])


def test_precip_probability_brier_reliability_and_member_fraction() -> None:
    data = _fixture()["explicit_precip_probability"]
    pairs = [
        ProbabilityPair(
            provider=data["provider"],
            lead_hours=18,
            probability=item["probability"],
            observed_event=item["observed_event"],
        )
        for item in data["pairs"]
    ]
    score = brier_score(pairs, expected_n=data["expected_n"])
    assert score["brier_score"] == pytest.approx(data["expected_brier"])
    assert score["missingness"] == data["expected_missingness"]

    actual_bins = reliability_bins(pairs, bins=data["reliability_bins"])
    expected_bins = data["expected_reliability"]
    assert len(actual_bins) == len(expected_bins)
    for actual, expected in zip(actual_bins, expected_bins, strict=True):
        assert actual["n"] == expected["n"]
        for name in ("bin_lower", "bin_upper", "mean_probability", "observed_frequency"):
            assert actual[name] == pytest.approx(expected[name])

    ensemble = _fixture()["ensemble_precipitation"]
    actual_probabilities = [
        event_probability(members, threshold=ensemble["threshold_mm"])
        for members in ensemble["member_sets"]
    ]
    assert actual_probabilities == pytest.approx(ensemble["expected_event_probabilities"])
    member_score = brier_from_members(
        ensemble["member_sets"],
        ensemble["observations_mm"],
        threshold=ensemble["threshold_mm"],
    )
    assert member_score["brier_score"] == pytest.approx(ensemble["expected_brier"])


def test_summary_quantiles_and_precipitation_semantics_do_not_fake_ensembles() -> None:
    data = _fixture()

    for case in data["weather_next_summary_semantics"]:
        identity = semantic_identity(
            variable="temperature_2m",
            value=case["value"],
            unit="degC",
            accumulation_window_minutes=None,
            statistic=case["statistic"],
        )
        assert identity.statistic_family == case["expected_family"]
        assert metric_eligibility(identity, metric=case["metric"]) == (
            case["eligible"],
            case["reason"],
        )

    for name in ("explicit_probability", "deterministic_amount", "genuine_member_amount"):
        case = data["precipitation_semantics"][name]
        identity = semantic_identity(
            variable=case["variable"],
            value=case["value"],
            unit=case["unit"],
            accumulation_window_minutes=case["window_minutes"],
            statistic=case["statistic"],
        )
        assert metric_eligibility(identity, metric=case["metric"]) == (
            case["eligible"],
            case["reason"],
        )

    with pytest.raises(ValueError, match="probability source"):
        ProbabilityPair(
            "synthetic_invalid",
            18,
            0.5,
            1.0,
            probability_source=data["precipitation_semantics"]["rejected_probability_source"],
        )

    unit_case = data["unit_drift"]
    errors = validate_semantics(
        variable=unit_case["variable"],
        value=unit_case["value"],
        unit=unit_case["bad_unit"],
        accumulation_window_minutes=unit_case["window_minutes"],
        statistic=unit_case["statistic"],
    )
    assert errors == [unit_case["expected_error"]]


def test_common_sample_matching_freezes_versions_missingness_and_exclusions() -> None:
    data = _fixture()["common_sample"]
    rows = common_sample_leaderboard(SkillSample(**sample) for sample in data["samples"])
    assert len(rows) == len(data["expected_rows"])

    for expected in data["expected_rows"]:
        row = next(
            item
            for item in rows
            if item["provider"] == expected["provider"]
            and dict(item["comparison_cohort"])["weathernext3"] == expected["peer_version"]
        )
        assert row["lead_bucket"] == "12-24h"
        assert dict(row["comparison_cohort"])["dwd_icon_d2"] == "2026a"
        assert row["matched_sample_ids"] == expected["matched_sample_ids"]
        assert row["excluded_sample_ids"] == expected["excluded_sample_ids"]
        assert row["n"] == expected["n"]
        for name in ("mae", "rmse", "bias"):
            assert row[name] == pytest.approx(expected[name])
        assert row["sample_sufficiency_state"] == "insufficient_sample"
        assert row["missingness"]["expected_n"] == 4
        assert row["missingness"]["available_n"] == expected["available_n"]
        assert row["missingness"]["missing_n"] == expected["missing_n"]
