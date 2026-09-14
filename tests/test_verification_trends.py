from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from rozkalns_weather.verification_trends import (
    SHIFT_POLICY,
    TREND_CONTRACT,
    build_verification_trends,
    detect_material_shifts,
)

DETERMINISTIC = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _observation(valid: datetime, value: float = 10.0) -> dict[str, object]:
    return {
        "source_provider": "DWD",
        "station_id": "10416",
        "location_id": "station_10416",
        "observed_at_utc": _iso(valid),
        "variable": "temperature_2m",
        "value": value,
        "unit": "degC",
    }


def _forecast(
    provider: str,
    valid: datetime,
    *,
    error: float,
    version: str = "v1",
) -> dict[str, object]:
    init = valid - timedelta(hours=6)
    return {
        "provider": provider,
        "model_provider": provider,
        "model_name": provider,
        "model_version": version,
        "location_id": "station_10416",
        "init_time_utc": _iso(init),
        "retrieved_at_utc": _iso(init + timedelta(hours=1)),
        "init_time_quality": "native",
        "source_surface": "fixture",
        "raw_payload_hash": f"{provider}-{valid:%Y%m%d}",
        "revision": 1,
        "valid_time_utc": _iso(valid),
        "lead_hours": 6.0,
        "variable": "temperature_2m",
        "statistic": "deterministic",
        "value": 10.0 + error,
        "unit": "degC",
    }


def _month_rows(
    year: int,
    month: int,
    *,
    days: int,
    icon_error: float,
    icon_version: str = "v1",
    omit_provider: str | None = None,
    omit_after: int | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    forecasts: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    for day in range(1, days + 1):
        valid = datetime(year, month, day, 6, tzinfo=timezone.utc)
        observations.append(_observation(valid))
        for provider in DETERMINISTIC:
            if omit_provider == provider and omit_after is not None and day > omit_after:
                continue
            forecasts.append(
                _forecast(
                    provider,
                    valid,
                    error=icon_error if provider == "icon_d2" else 1.0,
                    version=icon_version if provider == "icon_d2" else "v1",
                )
            )
    return forecasts, observations


def _monthly_point(report: dict[str, object], month: str, provider: str) -> dict[str, object]:
    periods = report["period_families"]["monthly"]
    period = next(item for item in periods if item["period_id"] == month)
    return next(item for item in period["deterministic"] if item["provider"] == provider)


def test_monthly_trends_preserve_common_sample_metrics_and_detect_skill_shift() -> None:
    may_forecasts, may_observations = _month_rows(2026, 5, days=30, icon_error=1.0)
    june_forecasts, june_observations = _month_rows(2026, 6, days=30, icon_error=2.0)

    report = build_verification_trends(
        forecast_rows=[*may_forecasts, *june_forecasts],
        observation_rows=[*may_observations, *june_observations],
        start=date(2026, 5, 1),
        end=date(2026, 6, 30),
        rolling_days=30,
        rolling_step_days=30,
    )

    assert report["contract"] == TREND_CONTRACT
    may = _monthly_point(report, "2026-05", "icon_d2")
    june = _monthly_point(report, "2026-06", "icon_d2")
    assert may["n"] == 30
    assert may["sample_sufficiency_state"] == "limited_sample"
    assert may["missingness"]["missing_fraction"] == 0.0
    assert may["mae"] == pytest.approx(1.0)
    assert may["rmse"] == pytest.approx(1.0)
    assert may["bias"] == pytest.approx(1.0)
    assert june["mae"] == pytest.approx(2.0)

    assert any(
        shift["shift_family"] == "skill"
        and shift["metric"] == "mae"
        and shift["provider"] == "icon_d2"
        and shift["from_period_id"] == "2026-05"
        and shift["to_period_id"] == "2026-06"
        and shift["direction"] == "degraded"
        for shift in report["material_shifts"]
    )
    assert report["ranking"] == {
        "overall_winner_emitted": False,
        "combined_weighting_emitted": False,
        "automatic_model_weighting_emitted": False,
    }


def test_missing_cycle_fixture_keeps_attrition_visible() -> None:
    may_forecasts, may_observations = _month_rows(2026, 5, days=30, icon_error=1.0)
    june_forecasts, june_observations = _month_rows(
        2026,
        6,
        days=30,
        icon_error=1.0,
        omit_provider="ecmwf_aifs",
        omit_after=20,
    )
    report = build_verification_trends(
        forecast_rows=[*may_forecasts, *june_forecasts],
        observation_rows=[*may_observations, *june_observations],
        start=date(2026, 5, 1),
        end=date(2026, 6, 30),
        rolling_days=60,
        rolling_step_days=60,
    )
    june = _monthly_point(report, "2026-06", "ecmwf_aifs")
    assert june["n"] == 20
    assert june["sample_sufficiency_state"] == "insufficient_sample"
    assert june["missingness"]["expected_n"] == 30
    assert june["missingness"]["available_n"] == 20
    assert june["missingness"]["missing_n"] == 10
    assert june["missingness"]["missing_fraction"] == pytest.approx(1 / 3)


def test_sparse_periods_do_not_generate_material_skill_claims() -> None:
    may_forecasts, may_observations = _month_rows(2026, 5, days=5, icon_error=1.0)
    june_forecasts, june_observations = _month_rows(2026, 6, days=5, icon_error=4.0)
    report = build_verification_trends(
        forecast_rows=[*may_forecasts, *june_forecasts],
        observation_rows=[*may_observations, *june_observations],
        start=date(2026, 5, 1),
        end=date(2026, 6, 5),
        rolling_days=30,
        rolling_step_days=30,
    )
    assert _monthly_point(report, "2026-05", "icon_d2")["sample_sufficiency_state"] == "insufficient_sample"
    assert not any(
        shift["shift_family"] == "skill"
        and shift.get("provider") == "icon_d2"
        and shift["from_period_id"] == "2026-05"
        for shift in report["material_shifts"]
    )


def test_model_version_boundary_is_not_compared_as_skill_shift() -> None:
    may_forecasts, may_observations = _month_rows(
        2026, 5, days=30, icon_error=1.0, icon_version="icon-v1"
    )
    june_forecasts, june_observations = _month_rows(
        2026, 6, days=30, icon_error=3.0, icon_version="icon-v2"
    )
    report = build_verification_trends(
        forecast_rows=[*may_forecasts, *june_forecasts],
        observation_rows=[*may_observations, *june_observations],
        start=date(2026, 5, 1),
        end=date(2026, 6, 30),
        rolling_days=60,
        rolling_step_days=60,
    )
    assert _monthly_point(report, "2026-05", "icon_d2")["model_version"] == "icon-v1"
    assert _monthly_point(report, "2026-06", "icon_d2")["model_version"] == "icon-v2"
    assert not any(
        shift["shift_family"] == "skill"
        and shift.get("provider") == "icon_d2"
        and shift["from_period_id"] == "2026-05"
        and shift["to_period_id"] == "2026-06"
        for shift in report["material_shifts"]
    )


def test_seasonal_window_clips_at_common_start_and_requested_end() -> None:
    report = build_verification_trends(
        forecast_rows=[],
        observation_rows=[],
        start=date(2026, 3, 15),
        end=date(2026, 6, 5),
        rolling_days=30,
        rolling_step_days=30,
    )
    assert report["historical_ifs_only"] == {
        "provider": "ecmwf_ifs",
        "start": "2026-03-15",
        "end": "2026-04-01",
        "included_in_common_trends": False,
        "reason_code": "PRE_COMMON_WINDOW_SEPARATE",
    }
    seasons = report["period_families"]["seasonal"]
    assert seasons[0]["period_id"] == "2026-MAM"
    assert seasons[0]["start"] == "2026-04-02"
    assert seasons[0]["end"] == "2026-05-31"
    assert seasons[0]["clipped"] is True
    assert seasons[1]["period_id"] == "2026-JJA"
    assert seasons[1]["start"] == "2026-06-01"
    assert seasons[1]["end"] == "2026-06-05"
    assert seasons[1]["clipped"] is True


def test_calibration_shift_fixture_is_descriptive_and_eligible_only() -> None:
    identity = {
        "period_family": "monthly",
        "provider": "icon_d2_eps",
        "model_version": "v1",
        "comparison_cohort_id": "icon_d2_eps=v1|ecmwf_aifs_ens=v1|ecmwf_ifs_ens=v1",
        "init_cycle_utc": "00Z",
        "lead_bucket": "6-12h",
        "variable": "precipitation_1h",
        "n": 30,
        "sample_sufficiency_state": "limited_sample",
        "missingness": {"missing_fraction": 0.0},
        "mean_crps": 0.2,
        "mean_wis": None,
        "coverage": None,
        "member_input": "genuine_member_N_only",
    }
    may = {**identity, "period_id": "2026-05", "period_start": "2026-05-01", "brier_score": 0.10}
    june = {**identity, "period_id": "2026-06", "period_start": "2026-06-01", "brier_score": 0.30}
    shifts = detect_material_shifts([], [may, june])
    shift = next(item for item in shifts if item["metric"] == "brier_score")
    assert shift["shift_family"] == "calibration"
    assert shift["direction"] == "degraded"
    assert shift["descriptive_only"] is True


def test_provider_freshness_shift_is_separate_from_skill() -> None:
    report = build_verification_trends(
        forecast_rows=[],
        observation_rows=[],
        freshness_rows=[
            {
                "timestamp_utc": "2026-05-15T00:00:00Z",
                "provider": "icon_d2",
                "freshness_state": "fresh",
                "source_age_hours": 1.0,
            },
            {
                "timestamp_utc": "2026-06-15T00:00:00Z",
                "provider": "icon_d2",
                "freshness_state": "stale",
                "source_age_hours": 8.0,
            },
        ],
        start=date(2026, 5, 1),
        end=date(2026, 6, 30),
        rolling_days=60,
        rolling_step_days=60,
    )
    assert any(
        shift["shift_family"] == "provider_freshness"
        and shift["metric"] == "worst_freshness_state"
        and shift["from_period_id"] == "2026-05"
        and shift["to_period_id"] == "2026-06"
        and shift["direction"] == "degraded"
        for shift in report["material_shifts"]
    )


def test_pre_common_window_is_warn_only_and_never_mixed() -> None:
    report = build_verification_trends(
        forecast_rows=[],
        observation_rows=[],
        start=date(2026, 2, 1),
        end=date(2026, 3, 31),
    )
    assert report["state"] == "WARN"
    assert report["reason_code"] == "HISTORICAL_IFS_ONLY"
    assert report["common_window"] is None
    assert report["period_families"] == {"monthly": [], "seasonal": [], "rolling": []}
    assert report["weathernext"]["fabricated_values"] is False


def test_frozen_contract_matches_source_shift_policy() -> None:
    contract = json.loads(
        Path("contracts/verification-trends-v1.json").read_text(encoding="utf-8")
    )
    assert contract["schema"] == TREND_CONTRACT
    assert contract["material_shift_policy"]["relative_metric_fraction"] == SHIFT_POLICY[
        "relative_metric_fraction"
    ]
    assert contract["material_shift_policy"]["missing_fraction_delta"] == SHIFT_POLICY[
        "missing_fraction_delta"
    ]
    assert contract["ranking"]["overall_winner_allowed"] is False
    assert contract["weathernext"]["fabricated_values_allowed"] is False
