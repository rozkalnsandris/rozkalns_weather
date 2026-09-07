import pytest

from rozkalns_weather.probabilistic import (
    EnsembleVerificationPair,
    brier_from_members,
    empirical_quantile,
    ensemble_crps,
    event_probability,
    interval_score,
    reliability_from_members,
    summarize_crps,
    weighted_interval_score,
)


def test_crps_is_zero_for_perfect_degenerate_ensemble() -> None:
    assert ensemble_crps((5.0, 5.0, 5.0), 5.0) == 0.0


def test_crps_rewards_members_near_truth() -> None:
    close = ensemble_crps((4.0, 5.0, 6.0), 5.0)
    far = ensemble_crps((0.0, 1.0, 2.0), 5.0)
    assert close < far
    summary = summarize_crps(
        [EnsembleVerificationPair(provider="ens", lead_hours=6, members=(4.0, 5.0, 6.0), observed=5.0)]
    )
    assert summary["n"] == 1
    assert summary["mean_crps"] == pytest.approx(close)


def test_interval_score_reports_width_coverage_and_penalty() -> None:
    covered = interval_score((0.0, 1.0, 2.0, 3.0, 4.0), 2.0, alpha=0.2)
    missed = interval_score((0.0, 1.0, 2.0, 3.0, 4.0), 10.0, alpha=0.2)
    assert covered["covered"] == 1.0
    assert covered["width"] > 0
    assert missed["covered"] == 0.0
    assert missed["interval_score"] > missed["width"]
    assert weighted_interval_score((0.0, 1.0, 2.0, 3.0, 4.0), 2.0) >= 0


def test_empirical_quantile_interpolates_members() -> None:
    assert empirical_quantile((0.0, 10.0), 0.5) == 5.0


def test_precipitation_probability_is_only_member_fraction() -> None:
    members = (0.0, 0.05, 0.1, 0.2)
    assert event_probability(members, threshold=0.1) == 0.5
    with pytest.raises(ValueError, match="must not be empty"):
        event_probability((), threshold=0.1)


def test_brier_and_reliability_use_member_derived_probabilities() -> None:
    member_sets = [(0.0, 0.2), (0.0, 0.0), (0.2, 0.2)]
    observations = [0.2, 0.0, 0.0]
    result = brier_from_members(member_sets, observations, threshold=0.1)
    assert result["n"] == 3
    assert result["brier_score"] == pytest.approx((0.25 + 0.0 + 1.0) / 3)
    bins = reliability_from_members(member_sets, observations, threshold=0.1, bins=2)
    assert sum(int(row["n"]) for row in bins) == 3
