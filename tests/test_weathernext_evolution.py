from datetime import datetime, timedelta, timezone

import pytest

from rozkalns_weather.weathernext_evolution import (
    EvolutionSample,
    FreshnessSample,
    QuantileEvolutionSample,
    VersionBoundary,
    build_version_evolution_report,
    common_version_samples,
    event_evolution_summary,
    freshness_evolution,
    notable_error_delta_cases,
    plan_comparison_windows,
    quantile_calibration_delta,
    skill_delta_summary,
    validate_report_payload,
)

UTC = timezone.utc
BEFORE = "3.0.0"
AFTER = "3.1.0"
BOUNDARY_AT = datetime(2026, 8, 1, tzinfo=UTC)


def boundary() -> VersionBoundary:
    return VersionBoundary(
        before_model_version=BEFORE,
        after_model_version=AFTER,
        before_schema_fingerprint="a" * 64,
        after_schema_fingerprint="b" * 64,
        effective_at_utc=BOUNDARY_AT,
        release_source_url="https://developers.google.com/weathernext/release-notes",
        release_metadata_verified=True,
    )


def deterministic_pair(
    *,
    valid_time: datetime,
    before_forecast: float,
    after_forecast: float,
    observed: float,
    variable: str = "temperature_2m",
    lead_hours: float = 24.0,
    run_class: str = "synoptic_360h",
    unit: str = "degC",
    accumulation_window_minutes: int | None = None,
) -> list[EvolutionSample]:
    return [
        EvolutionSample(
            model_version=BEFORE,
            valid_time_utc=valid_time,
            variable=variable,
            lead_hours=lead_hours,
            run_class=run_class,
            forecast=before_forecast,
            observed=observed,
            unit=unit,
            accumulation_window_minutes=accumulation_window_minutes,
        ),
        EvolutionSample(
            model_version=AFTER,
            valid_time_utc=valid_time,
            variable=variable,
            lead_hours=lead_hours,
            run_class=run_class,
            forecast=after_forecast,
            observed=observed,
            unit=unit,
            accumulation_window_minutes=accumulation_window_minutes,
        ),
    ]


def test_boundary_requires_verified_weather_next_3_metadata_and_schema_fingerprints() -> None:
    item = boundary()
    assert item.as_dict()["effective_at_utc"] == "2026-08-01T00:00:00Z"

    with pytest.raises(ValueError, match="WeatherNext-3"):
        VersionBoundary(
            before_model_version="2.0.0",
            after_model_version=AFTER,
            before_schema_fingerprint="a" * 64,
            after_schema_fingerprint="b" * 64,
            effective_at_utc=BOUNDARY_AT,
            release_source_url="https://developers.google.com/weathernext/release-notes",
            release_metadata_verified=True,
        )

    with pytest.raises(ValueError, match="fingerprint"):
        VersionBoundary(
            before_model_version=BEFORE,
            after_model_version=AFTER,
            before_schema_fingerprint="not-a-fingerprint",
            after_schema_fingerprint="b" * 64,
            effective_at_utc=BOUNDARY_AT,
            release_source_url="https://developers.google.com/weathernext/release-notes",
            release_metadata_verified=True,
        )

    with pytest.raises(ValueError, match="verified"):
        VersionBoundary(
            before_model_version=BEFORE,
            after_model_version=AFTER,
            before_schema_fingerprint="a" * 64,
            after_schema_fingerprint="b" * 64,
            effective_at_utc=BOUNDARY_AT,
            release_source_url="https://developers.google.com/weathernext/release-notes",
            release_metadata_verified=False,
        )


def test_window_planner_is_symmetric_and_exposes_clipping_limitation() -> None:
    planned = plan_comparison_windows(boundary(), days_per_side=30)
    assert planned.before_days == 30
    assert planned.after_days == 30
    assert planned.comparable_duration is True
    assert planned.as_dict()["performance_based_selection"] is False

    clipped = plan_comparison_windows(
        boundary(),
        days_per_side=30,
        corpus_start_utc=BOUNDARY_AT - timedelta(days=12),
        corpus_end_utc=BOUNDARY_AT + timedelta(days=30),
    )
    assert clipped.before_days == 12
    assert clipped.after_days == 30
    assert clipped.comparable_duration is False
    assert "unequal_or_empty_windows" in str(clipped.limitation)


def test_common_sample_intersection_requires_matching_station_semantics() -> None:
    valid = datetime(2026, 8, 10, 12, tzinfo=UTC)
    rows = deterministic_pair(valid_time=valid, before_forecast=20.0, after_forecast=19.0, observed=18.0)
    rows.append(
        EvolutionSample(
            model_version=BEFORE,
            valid_time_utc=valid + timedelta(hours=1),
            variable="temperature_2m",
            lead_hours=24,
            run_class="synoptic_360h",
            forecast=18.0,
            observed=18.0,
        )
    )
    common = common_version_samples(rows, before_version=BEFORE, after_version=AFTER)
    assert common["before_n"] == 2
    assert common["after_n"] == 1
    assert common["common_n"] == 1
    assert common["private_home_excluded"] is True

    with pytest.raises(ValueError, match="station_10416"):
        EvolutionSample(
            model_version=BEFORE,
            valid_time_utc=valid,
            variable="temperature_2m",
            lead_hours=24,
            run_class="synoptic_360h",
            forecast=20,
            observed=18,
            location_id="home",
        )


def test_skill_deltas_use_only_common_samples_and_keep_low_n_explicit() -> None:
    rows: list[EvolutionSample] = []
    for hour, before_forecast, after_forecast in ((0, 3.0, 2.0), (1, 4.0, 2.5)):
        rows.extend(
            deterministic_pair(
                valid_time=datetime(2026, 8, 10, hour, tzinfo=UTC),
                before_forecast=before_forecast,
                after_forecast=after_forecast,
                observed=2.0,
            )
        )
    common = common_version_samples(rows, before_version=BEFORE, after_version=AFTER)
    summary = skill_delta_summary(common["pairs"])
    assert len(summary) == 1
    item = summary[0]
    assert item["common_n"] == 2
    assert item["before"]["mae"] == pytest.approx(1.5)
    assert item["after"]["mae"] == pytest.approx(0.25)
    assert item["delta_after_minus_before"]["mae"]["absolute"] == pytest.approx(-1.25)
    assert item["uncertainty_eligible"] is False
    assert item["global_winner_label"] is None


def test_quantile_calibration_preserves_summary_quantile_semantics() -> None:
    valid = datetime(2026, 8, 10, 12, tzinfo=UTC)
    samples = [
        QuantileEvolutionSample(BEFORE, valid, "temperature_2m", 24, "synoptic_360h", 20, 15, 17, 19, 21, 23),
        QuantileEvolutionSample(AFTER, valid, "temperature_2m", 24, "synoptic_360h", 20, 16, 18, 20, 22, 24),
    ]
    delta = quantile_calibration_delta(samples, before_version=BEFORE, after_version=AFTER)
    assert delta[0]["common_n"] == 1
    assert delta[0]["before"]["p50_mae"] == 1
    assert delta[0]["after"]["p50_mae"] == 0
    assert delta[0]["synthetic_crps"] is None
    assert delta[0]["synthetic_brier"] is None
    assert delta[0]["synthetic_precipitation_probability"] is None

    with pytest.raises(ValueError, match="monotonic"):
        QuantileEvolutionSample(BEFORE, valid, "temperature_2m", 24, "synoptic_360h", 20, 15, 19, 18, 21, 23)


def test_event_and_notable_case_selection_is_deterministic() -> None:
    rows = []
    rows.extend(
        deterministic_pair(
            valid_time=datetime(2026, 8, 10, 12, tzinfo=UTC),
            before_forecast=29,
            after_forecast=31,
            observed=31,
        )
    )
    rows.extend(
        deterministic_pair(
            valid_time=datetime(2026, 8, 11, 12, tzinfo=UTC),
            before_forecast=31,
            after_forecast=28,
            observed=31,
        )
    )
    common = common_version_samples(rows, before_version=BEFORE, after_version=AFTER)
    events = event_evolution_summary(common["pairs"])
    high = next(row for row in events["summaries"] if row["event_id"] == "temperature_high_30c")
    assert high["improved"] == 1
    assert high["regressed"] == 1

    notable = notable_error_delta_cases(common["pairs"], limit=2)
    assert [row["valid_time_utc"] for row in notable] == sorted(row["valid_time_utc"] for row in notable)
    assert {row["classification"] for row in notable} == {"improvement", "regression"}


def test_precipitation_semantics_fail_closed_without_one_hour_accumulation() -> None:
    with pytest.raises(ValueError, match="60-minute"):
        EvolutionSample(
            model_version=BEFORE,
            valid_time_utc=datetime(2026, 8, 10, 12, tzinfo=UTC),
            variable="precipitation_1h",
            lead_hours=24,
            run_class="synoptic_360h",
            forecast=1.0,
            observed=0.5,
            unit="mm",
        )


def test_freshness_evolution_keeps_expected_observed_and_retrieved_times_distinct() -> None:
    init = datetime(2026, 8, 10, 0, tzinfo=UTC)
    samples = [
        FreshnessSample(BEFORE, init, init + timedelta(hours=2), init + timedelta(hours=2, minutes=10)),
        FreshnessSample(
            AFTER,
            init + timedelta(days=1),
            init + timedelta(days=1, hours=2),
            init + timedelta(days=1, hours=2, minutes=5),
            upstream_available_at_utc=init + timedelta(days=1, hours=2, minutes=2),
            state="delayed",
        ),
    ]
    result = freshness_evolution(samples, before_version=BEFORE, after_version=AFTER)
    assert result["before"]["mean_retrieval_lag_from_expected_minutes"] == 10
    assert result["after"]["mean_observed_upstream_lag_from_expected_minutes"] == 2
    assert result["after"]["delayed_runs"] == 1
    assert result["private_provider_identity_exposed"] is False


def test_report_is_sanitized_read_only_and_requires_verified_release_provenance() -> None:
    valid = datetime(2026, 8, 10, 12, tzinfo=UTC)
    report = build_version_evolution_report(
        boundary=boundary(),
        windows=plan_comparison_windows(boundary()),
        deterministic_samples=deterministic_pair(
            valid_time=valid,
            before_forecast=20,
            after_forecast=19,
            observed=18,
        ),
        release_provenance={
            "source_url": "https://developers.google.com/weathernext/release-notes",
            "effective_at_utc": "2026-08-01T00:00:00Z",
            "verified": True,
            "locally_first_observed_at_utc": "2026-08-01T03:00:00Z",
        },
    )
    receipt = validate_report_payload(report)
    assert receipt["state"] == "version_evolution_report_valid"
    assert receipt["private_fields_exposed"] is False
    assert report["warning_authority"] == "DWD"
    assert report["corpus_mutation_performed"] is False
    assert report["common_sample_counts"]["location_id"] == "station_10416"

    unsafe = dict(report)
    unsafe["token"] = "secret"
    with pytest.raises(ValueError, match="private report field"):
        validate_report_payload(unsafe)

    with pytest.raises(ValueError, match="verified"):
        build_version_evolution_report(
            boundary=boundary(),
            windows=plan_comparison_windows(boundary()),
            deterministic_samples=[],
            release_provenance={
                "source_url": "https://developers.google.com/weathernext/release-notes",
                "effective_at_utc": "2026-08-01T00:00:00Z",
                "verified": False,
            },
        )
