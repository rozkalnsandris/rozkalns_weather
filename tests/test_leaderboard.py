from rozkalns_weather.leaderboard import SkillSample, bootstrap_mean_ci, common_sample_leaderboard


def test_bootstrap_ci_is_explicitly_suppressed_for_small_samples() -> None:
    assert bootstrap_mean_ci([1.0] * 29) is None
    interval = bootstrap_mean_ci([1.0] * 30, samples=200, seed=7)
    assert interval is not None
    assert interval.lower == 1.0
    assert interval.upper == 1.0


def test_common_sample_leaderboard_excludes_provider_only_samples() -> None:
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


def test_leaderboard_keeps_modes_and_model_versions_separate() -> None:
    samples = [
        SkillSample("a", "icon", "old", 6, 2.0, 1.0, mode="run_to_run"),
        SkillSample("a", "ifs", "v1", 6, 1.5, 1.0, mode="run_to_run"),
        SkillSample("b", "icon", "new", 6, 1.0, 1.0, mode="run_to_run"),
        SkillSample("b", "ifs", "v1", 6, 1.5, 1.0, mode="run_to_run"),
        SkillSample("u", "icon", "new", 6, 1.0, 1.0, mode="user_available"),
        SkillSample("u", "ifs", "v1", 6, 1.1, 1.0, mode="user_available"),
    ]
    rows = common_sample_leaderboard(samples)
    icon_run_versions = {
        row["model_version"]
        for row in rows
        if row["provider"] == "icon" and row["mode"] == "run_to_run"
    }
    assert icon_run_versions == {"old", "new"}
    assert {row["mode"] for row in rows} == {"run_to_run", "user_available"}
