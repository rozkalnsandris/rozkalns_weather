from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from statistics import mean
from typing import Mapping, Sequence

from .backfill import COMMON_BENCHMARK_START
from .benchmark_export import (
    DETERMINISTIC_PROVIDERS,
    ENSEMBLE_PROVIDERS,
    EXPORT_VARIABLES,
    PRECIP_EVENT_THRESHOLD_MM,
    TEMPERATURE_INTERVAL_ALPHA,
    load_benchmark_rows,
)
from .db import Database
from .events import EventPair, summarize_events
from .locations import DWD_10416
from .probabilistic import (
    brier_from_members,
    ensemble_crps,
    interval_score,
    reliability_from_members,
    weighted_interval_score,
)
from .reporting import EVENT_DEFINITIONS
from .verification import ErrorPair, lead_bucket, sample_confidence, summarize

DRILLDOWN_CONTRACT = "verification-drilldown-v1"


def month_bounds(month: str) -> tuple[date, date]:
    try:
        start = datetime.strptime(month + "-01", "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("month must be YYYY-MM") from exc
    if start.month == 12:
        next_month = date(start.year + 1, 1, 1)
    else:
        next_month = date(start.year, start.month + 1, 1)
    end = date.fromordinal(next_month.toordinal() - 1)
    if end < COMMON_BENCHMARK_START:
        raise ValueError(f"month must overlap the common benchmark window starting {COMMON_BENCHMARK_START.isoformat()}")
    return max(start, COMMON_BENCHMARK_START), end


def _utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("drilldown timestamps must be UTC")
    return parsed.astimezone(timezone.utc)


def _month(value: object) -> str:
    return _utc(value).strftime("%Y-%m")


def _cycle(value: object) -> str:
    return _utc(value).strftime("%HZ")


def _latest_revision_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    latest: dict[tuple[str, str, str, str], int] = {}
    for row in rows:
        key = (
            str(row["provider"]),
            str(row["model_name"]),
            str(row["model_version"]),
            str(row["init_time_utc"]),
        )
        latest[key] = max(latest.get(key, 0), int(row.get("revision") or 1))
    return [
        dict(row)
        for row in rows
        if int(row.get("revision") or 1)
        == latest[(str(row["provider"]), str(row["model_name"]), str(row["model_version"]), str(row["init_time_utc"]))]
    ]


def _truth_map(observations: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], float]:
    return {
        (str(row["observed_at_utc"]), str(row["variable"])): float(row["value"])
        for row in observations
        if str(row.get("source_provider")) == "DWD" and str(row.get("station_id")) == "10416"
    }


def _select_deterministic(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    selected: dict[tuple[str, str, str, str, str, str], dict[str, object]] = {}
    for raw in _latest_revision_rows(rows):
        provider = str(raw["provider"])
        statistic = str(raw["statistic"])
        variable = str(raw["variable"])
        if provider not in DETERMINISTIC_PROVIDERS or statistic not in {"deterministic", "mean"}:
            continue
        if variable not in EXPORT_VARIABLES:
            continue
        row = dict(raw)
        key = (
            provider,
            variable,
            _month(row["valid_time_utc"]),
            _cycle(row["init_time_utc"]),
            lead_bucket(float(row["lead_hours"])),
            str(row["valid_time_utc"]),
        )
        current = selected.get(key)
        if current is None:
            selected[key] = row
            continue
        rank = (float(row["lead_hours"]), str(row["retrieved_at_utc"]))
        current_rank = (float(current["lead_hours"]), str(current["retrieved_at_utc"]))
        if rank[0] < current_rank[0] or (rank[0] == current_rank[0] and rank[1] > current_rank[1]):
            selected[key] = row
    return list(selected.values())


def _missingness(
    *,
    expected_ids: set[str],
    provider_ids: set[str],
    truth_ids: set[str],
    common_ids: set[str],
    cohort_ids: Sequence[str],
) -> dict[str, int | float]:
    expected_n = len(expected_ids)
    missing_n = len(expected_ids - provider_ids)
    return {
        "expected_n": expected_n,
        "available_n": len(provider_ids),
        "missing_n": missing_n,
        "missing_fraction": (missing_n / expected_n) if expected_n else 0.0,
        "truth_available_n": len(expected_ids & truth_ids),
        "truth_missing_n": len(expected_ids - truth_ids),
        "total_common_n": len(common_ids),
        "cohort_common_n": len(cohort_ids),
        "excluded_non_common_n": len((provider_ids & truth_ids) - common_ids),
        "excluded_other_version_cohort_n": len(common_ids) - len(cohort_ids),
    }


def _event_metrics(variable: str, pairs: Sequence[ErrorPair]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for event_variable, threshold, direction, event_id in EVENT_DEFINITIONS:
        if event_variable != variable:
            continue
        events = [
            EventPair(
                provider=item.provider,
                model_version=item.model_version,
                variable=variable,
                lead_hours=item.lead_hours,
                forecast=item.forecast,
                observed=item.observed,
                threshold=float(threshold),
                direction=direction,
            )
            for item in pairs
        ]
        output.append(
            {
                "event_id": event_id,
                "threshold": threshold,
                "direction": direction,
                **summarize_events(events),
            }
        )
    return output


def _deterministic_slices(
    rows: Sequence[Mapping[str, object]], observations: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    selected = _select_deterministic(rows)
    truth = _truth_map(observations)
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in selected:
        grouped[
            (
                _month(row["valid_time_utc"]),
                str(row["variable"]),
                _cycle(row["init_time_utc"]),
                lead_bucket(float(row["lead_hours"])),
            )
        ].append(row)

    output: list[dict[str, object]] = []
    for (month, variable, cycle, bucket), slice_rows in sorted(grouped.items()):
        by_provider: dict[str, dict[str, dict[str, object]]] = {provider: {} for provider in DETERMINISTIC_PROVIDERS}
        for row in slice_rows:
            by_provider[str(row["provider"])][str(row["valid_time_utc"])] = row
        expected_ids = set().union(*(set(items) for items in by_provider.values()))
        truth_ids = {valid for valid, truth_variable in truth if truth_variable == variable}
        provider_truth_ids = {provider: set(items) & truth_ids for provider, items in by_provider.items()}
        common_ids = set.intersection(*(provider_truth_ids[provider] for provider in DETERMINISTIC_PROVIDERS))
        cohorts: dict[tuple[tuple[str, str], ...], list[str]] = defaultdict(list)
        for valid in sorted(common_ids):
            version_vector = tuple(
                (provider, str(by_provider[provider][valid].get("model_version") or "unknown"))
                for provider in DETERMINISTIC_PROVIDERS
            )
            cohorts[version_vector].append(valid)

        availability = [
            {
                "provider": provider,
                "versions_present": sorted({str(row.get("model_version") or "unknown") for row in by_provider[provider].values()}),
                **_missingness(
                    expected_ids=expected_ids,
                    provider_ids=set(by_provider[provider]),
                    truth_ids=truth_ids,
                    common_ids=common_ids,
                    cohort_ids=tuple(common_ids),
                ),
            }
            for provider in DETERMINISTIC_PROVIDERS
        ]
        cohort_rows: list[dict[str, object]] = []
        for version_vector, cohort_ids in sorted(cohorts.items()):
            versions = dict(version_vector)
            metrics = []
            for provider in DETERMINISTIC_PROVIDERS:
                pairs = [
                    ErrorPair(
                        provider=provider,
                        model_version=versions[provider],
                        lead_hours=float(by_provider[provider][valid]["lead_hours"]),
                        forecast=float(by_provider[provider][valid]["value"]),
                        observed=truth[(valid, variable)],
                    )
                    for valid in cohort_ids
                ]
                row = {
                    "provider": provider,
                    "model_version": versions[provider],
                    "month": month,
                    "init_cycle_utc": cycle,
                    "lead_bucket": bucket,
                    "variable": variable,
                    **summarize(pairs),
                    "missingness": _missingness(
                        expected_ids=expected_ids,
                        provider_ids=set(by_provider[provider]),
                        truth_ids=truth_ids,
                        common_ids=common_ids,
                        cohort_ids=cohort_ids,
                    ),
                    "event_summaries": _event_metrics(variable, pairs),
                    "probabilistic_metrics_eligible": False,
                    "probabilistic_reason": "deterministic forecast values never imply probability, CRPS or Brier",
                }
                metrics.append(row)
            cohort_rows.append(
                {
                    "comparison_cohort": versions,
                    "common_sample_ids": list(cohort_ids),
                    "metrics": metrics,
                }
            )
        output.append(
            {
                "month": month,
                "variable": variable,
                "init_cycle_utc": cycle,
                "lead_bucket": bucket,
                "expected_n": len(expected_ids),
                "truth_available_n": len(expected_ids & truth_ids),
                "truth_missing_n": len(expected_ids - truth_ids),
                "total_common_n": len(common_ids),
                "sample_sufficiency_state": sample_confidence(len(common_ids)),
                "availability": availability,
                "cohorts": cohort_rows,
            }
        )
    return output


def _ensemble_groups(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in _latest_revision_rows(rows):
        if str(row["provider"]) not in ENSEMBLE_PROVIDERS or not str(row["statistic"]).startswith("member_"):
            continue
        key = (
            str(row["provider"]),
            str(row.get("model_version") or "unknown"),
            str(row["init_time_utc"]),
            str(row["valid_time_utc"]),
            str(row["variable"]),
        )
        grouped[key].append(dict(row))
    output = []
    for (provider, version, init_time, valid_time, variable), member_rows in sorted(grouped.items()):
        statistics = [str(row["statistic"]) for row in member_rows]
        if len(statistics) != len(set(statistics)):
            raise ValueError("duplicate ensemble member identity in drilldown")
        leads = {float(row["lead_hours"]) for row in member_rows}
        if len(leads) != 1:
            raise ValueError("ensemble members must share lead_hours")
        output.append(
            {
                "provider": provider,
                "model_version": version,
                "init_time_utc": init_time,
                "valid_time_utc": valid_time,
                "variable": variable,
                "lead_hours": next(iter(leads)),
                "members": tuple(float(row["value"]) for row in sorted(member_rows, key=lambda item: str(item["statistic"]))),
            }
        )
    return output


def _ensemble_slices(
    rows: Sequence[Mapping[str, object]], observations: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    groups = _ensemble_groups(rows)
    truth = _truth_map(observations)
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in groups:
        grouped[
            (
                _month(row["valid_time_utc"]),
                str(row["variable"]),
                _cycle(row["init_time_utc"]),
                lead_bucket(float(row["lead_hours"])),
            )
        ].append(row)
    output = []
    for (month, variable, cycle, bucket), slice_rows in sorted(grouped.items()):
        by_provider: dict[str, dict[str, dict[str, object]]] = {provider: {} for provider in ENSEMBLE_PROVIDERS}
        for row in slice_rows:
            by_provider[str(row["provider"])][str(row["valid_time_utc"])] = row
        expected_ids = set().union(*(set(items) for items in by_provider.values()))
        truth_ids = {valid for valid, truth_variable in truth if truth_variable == variable}
        provider_truth_ids = {provider: set(items) & truth_ids for provider, items in by_provider.items()}
        common_ids = set.intersection(*(provider_truth_ids[provider] for provider in ENSEMBLE_PROVIDERS))
        cohorts: dict[tuple[tuple[str, str], ...], list[str]] = defaultdict(list)
        for valid in sorted(common_ids):
            vector = tuple(
                (provider, str(by_provider[provider][valid]["model_version"]))
                for provider in ENSEMBLE_PROVIDERS
            )
            cohorts[vector].append(valid)
        cohort_rows = []
        for version_vector, cohort_ids in sorted(cohorts.items()):
            versions = dict(version_vector)
            metrics = []
            for provider in ENSEMBLE_PROVIDERS:
                member_sets = [by_provider[provider][valid]["members"] for valid in cohort_ids]
                observed = [truth[(valid, variable)] for valid in cohort_ids]
                crps = [ensemble_crps(members, obs) for members, obs in zip(member_sets, observed, strict=True)]
                row: dict[str, object] = {
                    "provider": provider,
                    "model_version": versions[provider],
                    "month": month,
                    "init_cycle_utc": cycle,
                    "lead_bucket": bucket,
                    "variable": variable,
                    "n": len(cohort_ids),
                    "sample_confidence": sample_confidence(len(cohort_ids)),
                    "sample_sufficiency_state": sample_confidence(len(cohort_ids)),
                    "missingness": _missingness(
                        expected_ids=expected_ids,
                        provider_ids=set(by_provider[provider]),
                        truth_ids=truth_ids,
                        common_ids=common_ids,
                        cohort_ids=cohort_ids,
                    ),
                    "mean_crps": mean(crps) if crps else None,
                    "member_input": "genuine_member_N_only",
                }
                if variable == "temperature_2m":
                    intervals = [
                        interval_score(members, obs, alpha=TEMPERATURE_INTERVAL_ALPHA)
                        for members, obs in zip(member_sets, observed, strict=True)
                    ]
                    row.update(
                        {
                            "interval_alpha": TEMPERATURE_INTERVAL_ALPHA,
                            "coverage": mean(float(item["covered"]) for item in intervals) if intervals else None,
                            "mean_interval_width": mean(float(item["width"]) for item in intervals) if intervals else None,
                            "mean_wis": mean(
                                weighted_interval_score(members, obs)
                                for members, obs in zip(member_sets, observed, strict=True)
                            ) if cohort_ids else None,
                        }
                    )
                if variable == "precipitation_1h":
                    row.update(
                        brier_from_members(member_sets, observed, threshold=PRECIP_EVENT_THRESHOLD_MM)
                    )
                    row["reliability_bins"] = reliability_from_members(
                        member_sets, observed, threshold=PRECIP_EVENT_THRESHOLD_MM
                    )
                metrics.append(row)
            cohort_rows.append({"comparison_cohort": versions, "common_sample_ids": list(cohort_ids), "metrics": metrics})
        output.append(
            {
                "month": month,
                "variable": variable,
                "init_cycle_utc": cycle,
                "lead_bucket": bucket,
                "expected_n": len(expected_ids),
                "truth_available_n": len(expected_ids & truth_ids),
                "truth_missing_n": len(expected_ids - truth_ids),
                "total_common_n": len(common_ids),
                "sample_sufficiency_state": sample_confidence(len(common_ids)),
                "cohorts": cohort_rows,
            }
        )
    return output


def build_verification_drilldown(
    *,
    forecast_rows: Sequence[Mapping[str, object]],
    observation_rows: Sequence[Mapping[str, object]],
    start: date,
    end: date,
) -> dict[str, object]:
    if end < start:
        raise ValueError("end must not be before start")
    return {
        "contract": DRILLDOWN_CONTRACT,
        "state": "PASS",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "comparison_location": {"id": DWD_10416.id, "station_id": "10416", "coordinates_exposed": False},
        "truth_source": "DWD WMO 10416",
        "dimensions": ["provider", "model_version", "init_cycle_utc", "lead_bucket", "variable", "month"],
        "sample_policy": "strict common valid-times across the exact provider class, split by exact model-version cohort",
        "deterministic": {"providers": list(DETERMINISTIC_PROVIDERS), "slices": _deterministic_slices(forecast_rows, observation_rows)},
        "ensemble": {"providers": list(ENSEMBLE_PROVIDERS), "slices": _ensemble_slices(forecast_rows, observation_rows)},
        "probability_policy": "Brier/reliability are emitted only from genuine member_N ensembles; deterministic amount forecasts never imply probability",
        "ranking": {"overall_winner_emitted": False, "combined_weighting_emitted": False},
        "production_data_authority_granted": False,
        "runtime_live_authority_granted": False,
    }


def verification_drilldown(database: Database, *, start: date, end: date) -> dict[str, object]:
    forecast_rows, observation_rows = load_benchmark_rows(database, start=start, end=end)
    return build_verification_drilldown(
        forecast_rows=forecast_rows,
        observation_rows=observation_rows,
        start=start,
        end=end,
    )


def verification_drilldown_month(database: Database, *, month: str) -> dict[str, object]:
    start, end = month_bounds(month)
    return verification_drilldown(database, start=start, end=end)
