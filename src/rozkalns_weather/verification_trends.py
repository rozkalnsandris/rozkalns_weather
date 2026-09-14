from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Mapping, Sequence

from .backfill import COMMON_BENCHMARK_START
from .verification import sample_confidence
from .verification_drilldown import build_verification_drilldown

TREND_CONTRACT = "verification-trends-v1"
TREND_SCHEMA_VERSION = 1
DEFAULT_ROLLING_DAYS = 30
DEFAULT_ROLLING_STEP_DAYS = 7

SHIFT_POLICY = {
    "relative_metric_fraction": 0.25,
    "absolute_metric_floor": 0.10,
    "missing_fraction_delta": 0.20,
    "coverage_delta": 0.15,
    "brier_delta": 0.05,
    "freshness_age_relative_fraction": 0.25,
    "freshness_age_absolute_hours": 2.0,
}

_FRESHNESS_SEVERITY = {
    "fresh": 0,
    "lagging": 1,
    "unknown": 2,
    "not_ingested": 2,
    "stale": 3,
    "degraded": 3,
    "error": 4,
}


def _utc_date(value: object, *, field: str) -> date:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc).date()


def _month_end(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1) - timedelta(days=1)
    return date(value.year, value.month + 1, 1) - timedelta(days=1)


def _month_periods(start: date, end: date) -> list[dict[str, object]]:
    cursor = date(start.year, start.month, 1)
    output: list[dict[str, object]] = []
    while cursor <= end:
        natural_start = cursor
        natural_end = _month_end(cursor)
        clipped_start = max(start, natural_start)
        clipped_end = min(end, natural_end)
        if clipped_start <= clipped_end:
            output.append(
                {
                    "family": "monthly",
                    "period_id": cursor.strftime("%Y-%m"),
                    "start": clipped_start.isoformat(),
                    "end": clipped_end.isoformat(),
                    "clipped": clipped_start != natural_start or clipped_end != natural_end,
                }
            )
        cursor = natural_end + timedelta(days=1)
    return output


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _season_identity(value: date) -> tuple[str, date, date]:
    if value.month in {3, 4, 5}:
        return f"{value.year}-MAM", date(value.year, 3, 1), date(value.year, 5, 31)
    if value.month in {6, 7, 8}:
        return f"{value.year}-JJA", date(value.year, 6, 1), date(value.year, 8, 31)
    if value.month in {9, 10, 11}:
        return f"{value.year}-SON", date(value.year, 9, 1), date(value.year, 11, 30)
    if value.month == 12:
        return (
            f"{value.year + 1}-DJF",
            date(value.year, 12, 1),
            date(value.year + 1, 2, 28)
            + (timedelta(days=1) if _is_leap(value.year + 1) else timedelta(0)),
        )
    return (
        f"{value.year}-DJF",
        date(value.year - 1, 12, 1),
        date(value.year, 2, 28)
        + (timedelta(days=1) if _is_leap(value.year) else timedelta(0)),
    )


def _seasonal_periods(start: date, end: date) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    cursor = start
    seen: set[str] = set()
    while cursor <= end:
        period_id, natural_start, natural_end = _season_identity(cursor)
        if period_id not in seen:
            clipped_start = max(start, natural_start)
            clipped_end = min(end, natural_end)
            if clipped_start <= clipped_end:
                output.append(
                    {
                        "family": "seasonal",
                        "period_id": period_id,
                        "start": clipped_start.isoformat(),
                        "end": clipped_end.isoformat(),
                        "clipped": clipped_start != natural_start or clipped_end != natural_end,
                    }
                )
            seen.add(period_id)
        cursor = natural_end + timedelta(days=1)
    return output


def _rolling_periods(
    start: date,
    end: date,
    *,
    rolling_days: int,
    rolling_step_days: int,
) -> list[dict[str, object]]:
    if rolling_days < 1 or rolling_step_days < 1:
        raise ValueError("rolling_days and rolling_step_days must be positive")
    output: list[dict[str, object]] = []
    cursor = start
    while cursor <= end:
        natural_end = cursor + timedelta(days=rolling_days - 1)
        clipped_end = min(end, natural_end)
        output.append(
            {
                "family": "rolling",
                "period_id": f"rolling-{cursor.isoformat()}--{clipped_end.isoformat()}",
                "start": cursor.isoformat(),
                "end": clipped_end.isoformat(),
                "clipped": clipped_end != natural_end,
                "rolling_days": rolling_days,
                "rolling_step_days": rolling_step_days,
            }
        )
        if clipped_end == end:
            break
        cursor += timedelta(days=rolling_step_days)
    return output


def _filter_period_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    field: str,
    start: date,
    end: date,
) -> list[Mapping[str, object]]:
    return [row for row in rows if start <= _utc_date(row.get(field), field=field) <= end]


def _cohort_id(cohort: Mapping[str, object]) -> str:
    return "|".join(f"{provider}={cohort[provider]}" for provider in sorted(cohort))


def _flatten_deterministic(
    drilldown: Mapping[str, object],
    period: Mapping[str, object],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    deterministic = drilldown["deterministic"]
    assert isinstance(deterministic, Mapping)
    for slice_row in deterministic["slices"]:
        assert isinstance(slice_row, Mapping)
        for cohort in slice_row["cohorts"]:
            assert isinstance(cohort, Mapping)
            cohort_map = cohort["comparison_cohort"]
            assert isinstance(cohort_map, Mapping)
            for metric in cohort["metrics"]:
                assert isinstance(metric, Mapping)
                output.append(
                    {
                        "period_family": period["family"],
                        "period_id": period["period_id"],
                        "period_start": period["start"],
                        "period_end": period["end"],
                        "period_clipped": period["clipped"],
                        "provider": metric["provider"],
                        "model_version": metric["model_version"],
                        "comparison_cohort_id": _cohort_id(cohort_map),
                        "init_cycle_utc": metric["init_cycle_utc"],
                        "lead_bucket": metric["lead_bucket"],
                        "variable": metric["variable"],
                        "n": metric["n"],
                        "sample_sufficiency_state": metric["sample_sufficiency_state"],
                        "missingness": metric["missingness"],
                        "mae": metric["mae"],
                        "rmse": metric["rmse"],
                        "bias": metric["bias"],
                        "event_summaries": metric["event_summaries"],
                        "probabilistic_metrics_eligible": False,
                    }
                )
    return output


def _flatten_ensemble(
    drilldown: Mapping[str, object],
    period: Mapping[str, object],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    ensemble = drilldown["ensemble"]
    assert isinstance(ensemble, Mapping)
    for slice_row in ensemble["slices"]:
        assert isinstance(slice_row, Mapping)
        for cohort in slice_row["cohorts"]:
            assert isinstance(cohort, Mapping)
            cohort_map = cohort["comparison_cohort"]
            assert isinstance(cohort_map, Mapping)
            for metric in cohort["metrics"]:
                assert isinstance(metric, Mapping)
                output.append(
                    {
                        "period_family": period["family"],
                        "period_id": period["period_id"],
                        "period_start": period["start"],
                        "period_end": period["end"],
                        "period_clipped": period["clipped"],
                        "provider": metric["provider"],
                        "model_version": metric["model_version"],
                        "comparison_cohort_id": _cohort_id(cohort_map),
                        "init_cycle_utc": metric["init_cycle_utc"],
                        "lead_bucket": metric["lead_bucket"],
                        "variable": metric["variable"],
                        "n": metric["n"],
                        "sample_sufficiency_state": metric["sample_sufficiency_state"],
                        "missingness": metric["missingness"],
                        "mean_crps": metric.get("mean_crps"),
                        "coverage": metric.get("coverage"),
                        "mean_interval_width": metric.get("mean_interval_width"),
                        "mean_wis": metric.get("mean_wis"),
                        "brier_score": metric.get("brier_score"),
                        "reliability_bins": metric.get("reliability_bins"),
                        "member_input": metric["member_input"],
                    }
                )
    return output


def _freshness_points(
    freshness_rows: Sequence[Mapping[str, object]],
    period: Mapping[str, object],
) -> list[dict[str, object]]:
    start = date.fromisoformat(str(period["start"]))
    end = date.fromisoformat(str(period["end"]))
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in freshness_rows:
        timestamp = row.get("observed_at_utc", row.get("timestamp_utc"))
        if timestamp is None:
            raise ValueError("freshness rows require observed_at_utc or timestamp_utc")
        if start <= _utc_date(timestamp, field="freshness timestamp") <= end:
            provider = str(row.get("provider") or "")
            if not provider:
                raise ValueError("freshness rows require provider")
            grouped[provider].append(row)

    output: list[dict[str, object]] = []
    for provider, rows in sorted(grouped.items()):
        states = [str(row.get("freshness_state") or "unknown") for row in rows]
        unknown = [state for state in states if state not in _FRESHNESS_SEVERITY]
        if unknown:
            raise ValueError(f"unsupported freshness_state: {unknown[0]}")
        worst = max(states, key=lambda state: _FRESHNESS_SEVERITY[state])
        ages = [float(row["source_age_hours"]) for row in rows if row.get("source_age_hours") is not None]
        output.append(
            {
                "period_family": period["family"],
                "period_id": period["period_id"],
                "period_start": period["start"],
                "period_end": period["end"],
                "provider": provider,
                "n": len(rows),
                "sample_sufficiency_state": sample_confidence(len(rows)),
                "worst_freshness_state": worst,
                "mean_source_age_hours": mean(ages) if ages else None,
            }
        )
    return output


def _metric_delta_material(previous: float, current: float) -> bool:
    absolute = abs(current - previous)
    threshold = max(
        float(SHIFT_POLICY["absolute_metric_floor"]),
        abs(previous) * float(SHIFT_POLICY["relative_metric_fraction"]),
    )
    return absolute >= threshold


def _direction(previous: float, current: float, *, lower_is_better: bool) -> str:
    if current == previous:
        return "unchanged"
    improved = current < previous if lower_is_better else current > previous
    return "improved" if improved else "degraded"


def _point_identity(point: Mapping[str, object]) -> tuple[str, ...]:
    return (
        str(point["period_family"]),
        str(point["provider"]),
        str(point["model_version"]),
        str(point["comparison_cohort_id"]),
        str(point["init_cycle_utc"]),
        str(point["lead_bucket"]),
        str(point["variable"]),
    )


def _sample_ok(point: Mapping[str, object]) -> bool:
    return str(point.get("sample_sufficiency_state")) != "insufficient_sample"


def _numeric(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def detect_material_shifts(
    deterministic_points: Sequence[Mapping[str, object]],
    ensemble_points: Sequence[Mapping[str, object]],
    freshness_points: Sequence[Mapping[str, object]] = (),
) -> list[dict[str, object]]:
    shifts: list[dict[str, object]] = []

    def consecutive(points: Sequence[Mapping[str, object]], identity):
        grouped: dict[tuple[str, ...], list[Mapping[str, object]]] = defaultdict(list)
        for point in points:
            grouped[identity(point)].append(point)
        for key, items in sorted(grouped.items()):
            ordered = sorted(items, key=lambda item: str(item["period_start"]))
            for previous, current in zip(ordered, ordered[1:], strict=False):
                yield key, previous, current

    for _identity, previous, current in consecutive(deterministic_points, _point_identity):
        if not (_sample_ok(previous) and _sample_ok(current)):
            continue
        for metric_name in ("mae", "rmse"):
            old = _numeric(previous.get(metric_name))
            new = _numeric(current.get(metric_name))
            if old is not None and new is not None and _metric_delta_material(old, new):
                shifts.append(
                    _shift(
                        family="skill",
                        metric=metric_name,
                        previous=previous,
                        current=current,
                        previous_value=old,
                        current_value=new,
                        direction=_direction(old, new, lower_is_better=True),
                    )
                )
        old_missing = _numeric(
            (previous.get("missingness") or {}).get("missing_fraction")
            if isinstance(previous.get("missingness"), Mapping)
            else None
        )
        new_missing = _numeric(
            (current.get("missingness") or {}).get("missing_fraction")
            if isinstance(current.get("missingness"), Mapping)
            else None
        )
        if (
            old_missing is not None
            and new_missing is not None
            and abs(new_missing - old_missing) >= float(SHIFT_POLICY["missing_fraction_delta"])
        ):
            shifts.append(
                _shift(
                    family="sample_availability",
                    metric="missing_fraction",
                    previous=previous,
                    current=current,
                    previous_value=old_missing,
                    current_value=new_missing,
                    direction=_direction(old_missing, new_missing, lower_is_better=True),
                )
            )

    for _identity, previous, current in consecutive(ensemble_points, _point_identity):
        if not (_sample_ok(previous) and _sample_ok(current)):
            continue
        for metric_name in ("mean_crps", "mean_wis"):
            old = _numeric(previous.get(metric_name))
            new = _numeric(current.get(metric_name))
            if old is not None and new is not None and _metric_delta_material(old, new):
                shifts.append(
                    _shift(
                        family="probabilistic_skill",
                        metric=metric_name,
                        previous=previous,
                        current=current,
                        previous_value=old,
                        current_value=new,
                        direction=_direction(old, new, lower_is_better=True),
                    )
                )
        old_brier = _numeric(previous.get("brier_score"))
        new_brier = _numeric(current.get("brier_score"))
        if (
            old_brier is not None
            and new_brier is not None
            and abs(new_brier - old_brier) >= float(SHIFT_POLICY["brier_delta"])
        ):
            shifts.append(
                _shift(
                    family="calibration",
                    metric="brier_score",
                    previous=previous,
                    current=current,
                    previous_value=old_brier,
                    current_value=new_brier,
                    direction=_direction(old_brier, new_brier, lower_is_better=True),
                )
            )
        old_coverage = _numeric(previous.get("coverage"))
        new_coverage = _numeric(current.get("coverage"))
        if (
            old_coverage is not None
            and new_coverage is not None
            and abs(new_coverage - old_coverage) >= float(SHIFT_POLICY["coverage_delta"])
        ):
            shifts.append(
                _shift(
                    family="calibration",
                    metric="coverage",
                    previous=previous,
                    current=current,
                    previous_value=old_coverage,
                    current_value=new_coverage,
                    direction="changed",
                )
            )

    def freshness_identity(point: Mapping[str, object]) -> tuple[str, ...]:
        return (str(point["period_family"]), str(point["provider"]))

    for _identity, previous, current in consecutive(freshness_points, freshness_identity):
        old_state = str(previous["worst_freshness_state"])
        new_state = str(current["worst_freshness_state"])
        if old_state != new_state:
            shifts.append(
                {
                    "shift_family": "provider_freshness",
                    "metric": "worst_freshness_state",
                    "provider": current["provider"],
                    "from_period_id": previous["period_id"],
                    "to_period_id": current["period_id"],
                    "previous_value": old_state,
                    "current_value": new_state,
                    "direction": (
                        "improved"
                        if _FRESHNESS_SEVERITY[new_state] < _FRESHNESS_SEVERITY[old_state]
                        else "degraded"
                    ),
                    "descriptive_only": True,
                }
            )
        old_age = _numeric(previous.get("mean_source_age_hours"))
        new_age = _numeric(current.get("mean_source_age_hours"))
        if old_age is not None and new_age is not None:
            threshold = max(
                float(SHIFT_POLICY["freshness_age_absolute_hours"]),
                abs(old_age) * float(SHIFT_POLICY["freshness_age_relative_fraction"]),
            )
            if abs(new_age - old_age) >= threshold:
                shifts.append(
                    {
                        "shift_family": "provider_freshness",
                        "metric": "mean_source_age_hours",
                        "provider": current["provider"],
                        "from_period_id": previous["period_id"],
                        "to_period_id": current["period_id"],
                        "previous_value": old_age,
                        "current_value": new_age,
                        "direction": _direction(old_age, new_age, lower_is_better=True),
                        "descriptive_only": True,
                    }
                )

    return shifts


def _shift(
    *,
    family: str,
    metric: str,
    previous: Mapping[str, object],
    current: Mapping[str, object],
    previous_value: float,
    current_value: float,
    direction: str,
) -> dict[str, object]:
    return {
        "shift_family": family,
        "metric": metric,
        "provider": current["provider"],
        "model_version": current["model_version"],
        "init_cycle_utc": current["init_cycle_utc"],
        "lead_bucket": current["lead_bucket"],
        "variable": current["variable"],
        "from_period_id": previous["period_id"],
        "to_period_id": current["period_id"],
        "previous_value": previous_value,
        "current_value": current_value,
        "direction": direction,
        "descriptive_only": True,
    }


def _build_period_result(
    *,
    period: Mapping[str, object],
    forecast_rows: Sequence[Mapping[str, object]],
    observation_rows: Sequence[Mapping[str, object]],
    freshness_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    start = date.fromisoformat(str(period["start"]))
    end = date.fromisoformat(str(period["end"]))
    period_forecasts = _filter_period_rows(
        forecast_rows,
        field="valid_time_utc",
        start=start,
        end=end,
    )
    period_observations = _filter_period_rows(
        observation_rows,
        field="observed_at_utc",
        start=start,
        end=end,
    )
    drilldown = build_verification_drilldown(
        forecast_rows=period_forecasts,
        observation_rows=period_observations,
        start=start,
        end=end,
    )
    deterministic = _flatten_deterministic(drilldown, period)
    ensemble = _flatten_ensemble(drilldown, period)
    freshness = _freshness_points(freshness_rows, period)
    return {
        **dict(period),
        "state": "PASS",
        "deterministic": deterministic,
        "ensemble": ensemble,
        "provider_freshness": freshness,
    }


def build_verification_trends(
    *,
    forecast_rows: Sequence[Mapping[str, object]],
    observation_rows: Sequence[Mapping[str, object]],
    start: date,
    end: date,
    freshness_rows: Sequence[Mapping[str, object]] = (),
    rolling_days: int = DEFAULT_ROLLING_DAYS,
    rolling_step_days: int = DEFAULT_ROLLING_STEP_DAYS,
) -> dict[str, object]:
    if end < start:
        raise ValueError("end must not be before start")
    if rolling_days < 1 or rolling_step_days < 1:
        raise ValueError("rolling_days and rolling_step_days must be positive")

    historical_end = min(end, COMMON_BENCHMARK_START - timedelta(days=1))
    historical = {
        "provider": "ecmwf_ifs",
        "start": start.isoformat() if start < COMMON_BENCHMARK_START else None,
        "end": historical_end.isoformat() if start <= historical_end else None,
        "included_in_common_trends": False,
        "reason_code": "PRE_COMMON_WINDOW_SEPARATE",
    }
    if end < COMMON_BENCHMARK_START:
        return {
            "schema_version": TREND_SCHEMA_VERSION,
            "contract": TREND_CONTRACT,
            "state": "WARN",
            "reason_code": "HISTORICAL_IFS_ONLY",
            "requested_window": {"start": start.isoformat(), "end": end.isoformat()},
            "common_window": None,
            "historical_ifs_only": historical,
            "period_families": {"monthly": [], "seasonal": [], "rolling": []},
            "material_shifts": [],
            **_policy_payload(),
        }

    common_start = max(start, COMMON_BENCHMARK_START)
    period_definitions = {
        "monthly": _month_periods(common_start, end),
        "seasonal": _seasonal_periods(common_start, end),
        "rolling": _rolling_periods(
            common_start,
            end,
            rolling_days=rolling_days,
            rolling_step_days=rolling_step_days,
        ),
    }
    period_families: dict[str, list[dict[str, object]]] = {}
    all_deterministic: list[dict[str, object]] = []
    all_ensemble: list[dict[str, object]] = []
    all_freshness: list[dict[str, object]] = []
    for family, periods in period_definitions.items():
        results = [
            _build_period_result(
                period=period,
                forecast_rows=forecast_rows,
                observation_rows=observation_rows,
                freshness_rows=freshness_rows,
            )
            for period in periods
        ]
        period_families[family] = results
        for result in results:
            all_deterministic.extend(result["deterministic"])
            all_ensemble.extend(result["ensemble"])
            all_freshness.extend(result["provider_freshness"])

    shifts = detect_material_shifts(all_deterministic, all_ensemble, all_freshness)
    return {
        "schema_version": TREND_SCHEMA_VERSION,
        "contract": TREND_CONTRACT,
        "state": "PASS",
        "reason_code": "OK",
        "requested_window": {"start": start.isoformat(), "end": end.isoformat()},
        "common_window": {"start": common_start.isoformat(), "end": end.isoformat()},
        "historical_ifs_only": historical,
        "period_families": period_families,
        "material_shifts": shifts,
        **_policy_payload(),
    }


def _policy_payload() -> dict[str, object]:
    return {
        "sample_policy": (
            "strict common valid-times inside each provider class and exact model-version cohort; "
            "unlike samples are never collapsed"
        ),
        "shift_policy": {
            **SHIFT_POLICY,
            "insufficient_samples_suppress_shift_detection": True,
            "model_version_boundaries_are_not_compared": True,
            "descriptive_only": True,
        },
        "weathernext": {
            "state": "pending",
            "reason_code": "DEFENSIBLE_REAL_CORPUS_REQUIRED",
            "fabricated_values": False,
            "included_in_public_trends": False,
        },
        "ranking": {
            "overall_winner_emitted": False,
            "combined_weighting_emitted": False,
            "automatic_model_weighting_emitted": False,
        },
        "authority": {
            "production_data_authority_granted": False,
            "runtime_live_authority_granted": False,
        },
    }
