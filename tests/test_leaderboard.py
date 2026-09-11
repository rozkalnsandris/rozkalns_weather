import pytest

from rozkalns_weather.leaderboard import SkillSample, bootstrap_mean_ci, common_sample_leaderboard


def test_bootstrap_ci_is_explicitly_suppressed_for_small_samples() -> None:
    assert bootstrap_mean_ci([1.0] * 29) is None
    interval = bootstrap_mean_ci([1.0] * 30, samples=200, seed=7)
    assert interval is not None
    assert interval.lower == 1.0
    assert interval.upper == 1.0


def test_common_sample_leaderboard_excludes_provider_only_samples_and_reports_missingness() -> None:
    samples = [
        SkillSample("a", "icon", "v1", 12, 2.0, 1.0),
        SkillSample("b", "icon", "v1", 12, 9.0, 1.0),
        SkillSample("a", "ifs", "v1", 12, 1.5, 1.0),
        SkillSample("c", "ifs", "v1", 12, 0.0, 1.0),
    ]
    rows = common_sample_leaderboard(samples)
    assert len(rows) == 2
    assert {row["provider"] for row in rows} == {"icon", "ifs"}
    assert all(row["n"] == 1 for row in rows)
    assert all(row["common_sample_ids"] == ["a"] for row in rows)
    assert all(row["sample_sufficiency_state"] == "insufficient_sample" for row in rows)
    assert all(row["missingness"]["expected_n"] == 3 for row in rows)
    assert all(row["missingness"]["available_n"] == 2 for row in rows)
    assert all(row["missingness"]["missing_n"] == 1 for row in rows)
    assert all(row["missingness"]["common_n"] == 1 for row in rows)
    assert all(row["missingness"]["excluded_non_common_n"] == 1 for row in rows)


def test_leaderboard_keeps_modes_and_complete_model_version_cohorts_separate() -> None:
    samples = [
        SkillSample("a", "icon", "old", 6, 2.0, 1.0, mode="run_to_run"),
        SkillSample("a", "ifs", "v1", 6, 1.5, 1.0, mode="run_to_run"),
        SkillSample("b", "icon", "new", 6, 1.0, 1.0, mode="run_to_run"),
        SkillSample("b", "ifs", "v1", 6, 1.5, 1.0, mode="run_to_run"),
        SkillSample("u", "icon", "new", 6, 1.0, 1.0, mode="user_available"),
        SkillSample("u", "ifs", "v1", 6, 1.1, 1.0, mode="user_available"),
    ]
    rows = common_sample_leaderboard(samples)
    run_rows = [row for row in rows if row["mode"] == "run_to_run"]
    assert len(run_rows) == 4
    assert {tuple(sorted(row["comparison_cohort"].items())) for row in run_rows} == {
        (("icon", "new"), ("ifs", "v1")),
        (("icon", "old"), ("ifs", "v1")),
    }
    assert all(row["n"] == 1 for row in run_rows)
    assert {row["mode"] for row in rows} == {"run_to_run", "user_available"}


def test_leaderboard_never_pools_different_variables() -> None:
    rows = common_sample_leaderboard(
        [
            SkillSample("a", "icon", "v1", 12, 2.0, 1.0, variable="temperature_2m"),
            SkillSample("a", "ifs", "v1", 12, 1.5, 1.0, variable="temperature_2m"),
            SkillSample("a", "icon", "v1", 12, 0.3, 0.2, variable="precipitation_1h"),
            SkillSample("a", "ifs", "v1", 12, 0.1, 0.2, variable="precipitation_1h"),
        ]
    )
    assert {row["variable"] for row in rows} == {"temperature_2m", "precipitation_1h"}
    assert len(rows) == 4


def test_duplicate_provider_sample_identity_fails_closed() -> None:
    with pytest.raises(ValueError, match="duplicate sample identity"):
        common_sample_leaderboard(
            [
                SkillSample("a", "icon", "v1", 12, 2.0, 1.0),
                SkillSample("a", "icon", "v1", 12, 2.1, 1.0),
                SkillSample("a", "ifs", "v1", 12, 1.5, 1.0),
            ]
        )
