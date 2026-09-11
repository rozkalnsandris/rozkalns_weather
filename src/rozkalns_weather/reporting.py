from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from .db import Database
from .events import EventPair, matched_event_groups
from .leaderboard import SkillSample, common_sample_leaderboard
from .locations import DWD_10416
from .probabilistic import (
    brier_from_members,
    ensemble_crps,
    interval_score,
    reliability_from_members,
    weighted_interval_score,
)
from .verification import lead_bucket, sample_confidence, sample_evidence

WEATHERNEXT_RELEASE_NOTES_URL = "https://developers.google.com/weathernext/release-notes"
PRECIP_EVENT_THRESHOLD_MM = 0.1

EVENT_DEFINITIONS = (
    ("temperature_2m", 30.0, "at_or_above", "temperature_high_30c"),
    ("temperature_2m", 0.0, "at_or_below", "temperature_freeze_0c"),
    ("precipitation_1h", PRECIP_EVENT_THRESHOLD_MM, "at_or_above", "precipitation_0p1mm_h"),
    ("wind_gust_10m", 15.0, "at_or_above", "wind_gust_15ms"),
)


def _month_bounds(month: str) -> tuple[str, str]:
    start = datetime.strptime(month + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


def _deterministic_rows(database: Database, *, start: str, end: str) -> list[dict[str, object]]:
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT r.provider,r.model_version,r.init_time_utc,r.retrieved_at_utc,
                      v.valid_time_utc,v.lead_hours,v.variable,v.value AS forecast_value,v.statistic,
                      o.value AS observed_value
               FROM forecast_runs r
               JOIN forecast_values v ON v.run_id=r.id
               JOIN observations o ON o.location_id=r.location_id
                 AND o.observed_at_utc=v.valid_time_utc
                 AND o.variable=v.variable
                 AND o.source_provider='DWD'
               WHERE r.location_id=?
                 AND v.statistic IN ('deterministic','mean')
                 AND v.variable IN ('temperature_2m','precipitation_1h','wind_gust_10m')
                 AND v.valid_time_utc>=? AND v.valid_time_utc<?
               ORDER BY r.provider,v.valid_time_utc,v.variable,v.lead_hours ASC,r.retrieved_at_utc DESC""",
            (DWD_10416.id, start, end),
        ).fetchall()
    return [dict(row) for row in rows]


def _freshest_temperature_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    selected: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        if row["variable"] != "temperature_2m":
            continue
        bucket = lead_bucket(float(row["lead_hours"]))
        key = (str(row["provider"]), bucket, str(row["valid_time_utc"]))
        if key not in selected:
            selected[key] = row
    return list(selected.values())


def _skill_samples(rows: list[dict[str, object]]) -> list[SkillSample]:
    return [
        SkillSample(
            sample_id=str(row["valid_time_utc"]),
            provider=str(row["provider"]),
            model_version=str(row["model_version"]) if row.get("model_version") is not None else None,
            lead_hours=float(row["lead_hours"]),
            forecast=float(row["forecast_value"]),
            observed=float(row["observed_value"]),
            mode="monthly_common_valid_time",
            variable="temperature_2m",
        )
        for row in rows
    ]


def _common_wins_losses(rows: list[dict[str, object]]) -> tuple[dict[str, int], list[dict[str, object]]]:
    by_bucket: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_bucket[lead_bucket(float(row["lead_hours"]))].append(row)

    common_counts: dict[str, int] = {}
    counters: dict[tuple[str, str, str], dict[str, int]] = {}
    for bucket, bucket_rows in sorted(by_bucket.items()):
        providers = sorted({str(row["provider"]) for row in bucket_rows})
        if len(providers) < 2:
            common_counts[bucket] = 0
            continue
        times_by_provider = {
            provider: {
                str(row["valid_time_utc"])
                for row in bucket_rows
                if str(row["provider"]) == provider
            }
            for provider in providers
        }
        common_times = set.intersection(*(times_by_provider[provider] for provider in providers))
        common_counts[bucket] = len(common_times)
        by_provider_time = {
            (str(row["provider"]), str(row["valid_time_utc"])): row
            for row in bucket_rows
            if str(row["valid_time_utc"]) in common_times
        }
        for valid_time in sorted(common_times):
            sample_rows = [by_provider_time[(provider, valid_time)] for provider in providers]
            errors = {
                str(row["provider"]): abs(float(row["forecast_value"]) - float(row["observed_value"]))
                for row in sample_rows
            }
            best = min(errors.values())
            worst = max(errors.values())
            best_providers = {provider for provider, error in errors.items() if error == best}
            worst_providers = {provider for provider, error in errors.items() if error == worst}
            for row in sample_rows:
                provider = str(row["provider"])
                version = str(row["model_version"] or "unknown")
                key = (bucket, provider, version)
                counter = counters.setdefault(
                    key,
                    {"n_common": 0, "wins": 0, "losses": 0, "best_ties": 0, "worst_ties": 0},
                )
                counter["n_common"] += 1
                if provider in best_providers:
                    if len(best_providers) == 1:
                        counter["wins"] += 1
                    else:
                        counter["best_ties"] += 1
                if provider in worst_providers:
                    if len(worst_providers) == 1:
                        counter["losses"] += 1
                    else:
                        counter["worst_ties"] += 1
    rows_out = [
        {
            "lead_bucket": bucket,
            "provider": provider,
            "model_version": version,
            **counts,
        }
        for (bucket, provider, version), counts in sorted(counters.items())
    ]
    return common_counts, rows_out


def _ensemble_calibration(database: Database, *, start: str, end: str) -> dict[str, object]:
    with database.connect() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                """SELECT r.id AS run_id,r.provider,r.model_version,
                          v.valid_time_utc,v.lead_hours,v.variable,v.statistic,v.value,
                          o.value AS observed_value
                   FROM forecast_runs r
                   JOIN forecast_values v ON v.run_id=r.id
                   JOIN observations o ON o.location_id=r.location_id
                     AND o.observed_at_utc=v.valid_time_utc
                     AND o.variable=v.variable
                     AND o.source_provider='DWD'
                   WHERE r.location_id=?
                     AND v.statistic LIKE 'member_%'
                     AND v.variable IN ('temperature_2m','precipitation_1h','wind_gust_10m')
                     AND v.valid_time_utc>=? AND v.valid_time_utc<?
                   ORDER BY r.provider,r.id,v.valid_time_utc,v.variable,v.statistic""",
                (DWD_10416.id, start, end),
            ).fetchall()
        ]

    grouped: dict[tuple[str, int, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row["provider"]),
                int(row["run_id"]),
                str(row["valid_time_utc"]),
                str(row["variable"]),
            )
        ].append(row)

    crps: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    temperature_wis: dict[str, list[float]] = defaultdict(list)
    temperature_coverage: dict[str, list[float]] = defaultdict(list)
    temperature_width: dict[str, list[float]] = defaultdict(list)
    precipitation_members: dict[str, list[list[float]]] = defaultdict(list)
    precipitation_observed: dict[str, list[float]] = defaultdict(list)
    group_counts: dict[str, int] = defaultdict(int)

    for (provider, _run_id, _valid, variable), member_rows in grouped.items():
        members = [float(row["value"]) for row in member_rows]
        observed = float(member_rows[0]["observed_value"])
        group_counts[provider] += 1
        crps[provider][variable].append(ensemble_crps(members, observed))
        if variable == "temperature_2m":
            interval = interval_score(members, observed, alpha=0.2)
            temperature_wis[provider].append(weighted_interval_score(members, observed))
            temperature_coverage[provider].append(float(interval["covered"]))
            temperature_width[provider].append(float(interval["width"]))
        elif variable == "precipitation_1h":
            precipitation_members[provider].append(members)
            precipitation_observed[provider].append(observed)

    result: dict[str, object] = {}
    providers = sorted(set(group_counts) | set(precipitation_members) | set(temperature_wis))
    for provider in providers:
        precip_members = precipitation_members.get(provider, [])
        precip_observed = precipitation_observed.get(provider, [])
        crps_values = crps.get(provider, {})
        temp_n = len(temperature_wis.get(provider, []))
        precip_n = len(precip_members)
        result[provider] = {
            "n_member_groups": group_counts.get(provider, 0),
            "sample_sufficiency_state": sample_confidence(group_counts.get(provider, 0)),
            "mean_crps_by_variable": {
                variable: mean(values)
                for variable, values in sorted(crps_values.items())
                if values
            },
            "crps_sample_evidence_by_variable": {
                variable: sample_evidence(len(values))
                for variable, values in sorted(crps_values.items())
            },
            "temperature_80_interval": {
                "n": temp_n,
                "sample_sufficiency_state": sample_confidence(temp_n),
                "mean_wis": mean(temperature_wis[provider]) if temperature_wis.get(provider) else None,
                "coverage": mean(temperature_coverage[provider]) if temperature_coverage.get(provider) else None,
                "mean_width": mean(temperature_width[provider]) if temperature_width.get(provider) else None,
            },
            "precipitation_probability": {
                **brier_from_members(precip_members, precip_observed, threshold=PRECIP_EVENT_THRESHOLD_MM),
                "sample_sufficiency_state": sample_confidence(precip_n),
                "missingness": sample_evidence(precip_n)["missingness"],
                "reliability_bins": reliability_from_members(
                    precip_members,
                    precip_observed,
                    threshold=PRECIP_EVENT_THRESHOLD_MM,
                )
                if precip_members
                else [],
            },
        }
    return result


def _event_summaries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    pairs: list[EventPair] = []
    definitions_by_variable: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for variable, threshold, direction, _label in EVENT_DEFINITIONS:
        definitions_by_variable[variable].append((threshold, direction))
    for row in rows:
        variable = str(row["variable"])
        for threshold, direction in definitions_by_variable.get(variable, []):
            pairs.append(
                EventPair(
                    provider=str(row["provider"]),
                    model_version=str(row["model_version"]) if row.get("model_version") is not None else None,
                    variable=variable,
                    lead_hours=float(row["lead_hours"]),
                    forecast=float(row["forecast_value"]),
                    observed=float(row["observed_value"]),
                    threshold=float(threshold),
                    direction=direction,
                )
            )
    return matched_event_groups(pairs)


def monthly_weather_next_report(database: Database, *, month: str) -> dict[str, Any]:
    start, end = _month_bounds(month)
    deterministic_rows = _deterministic_rows(database, start=start, end=end)
    temperature_rows = _freshest_temperature_rows(deterministic_rows)
    leaderboard = common_sample_leaderboard(_skill_samples(temperature_rows))
    common_counts, wins_losses = _common_wins_losses(temperature_rows)
    ensemble = _ensemble_calibration(database, start=start, end=end)
    events = _event_summaries(deterministic_rows)

    notable = [
        {
            "provider": str(row["provider"]),
            "model_version": row.get("model_version"),
            "valid_time_utc": row["valid_time_utc"],
            "lead_bucket": lead_bucket(float(row["lead_hours"])),
            "error_abs_degC": abs(float(row["forecast_value"]) - float(row["observed_value"])),
        }
        for row in temperature_rows
    ]
    notable_misses = sorted(notable, key=lambda item: float(item["error_abs_degC"]), reverse=True)[:10]
    wn_cases = [item for item in notable if item["provider"] == "weathernext3"]
    wn_misses = sorted(wn_cases, key=lambda item: float(item["error_abs_degC"]), reverse=True)[:10]
    wn_wins = sorted(wn_cases, key=lambda item: float(item["error_abs_degC"]))[:10]
    wn_n = sum(int(row["n"]) for row in leaderboard if row["provider"] == "weathernext3")

    with database.connect() as connection:
        release_events = [
            dict(row)
            for row in connection.execute(
                """SELECT provider,model_version,effective_at_utc,event_type,source_url,note
                   FROM model_events
                   WHERE provider='weathernext3'
                     AND effective_at_utc>=? AND effective_at_utc<?
                   ORDER BY effective_at_utc""",
                (start, end),
            ).fetchall()
        ]

    return {
        "report_type": "station_benchmark_monthly_v3",
        "sample_sufficiency_contract": "common-sample-sufficiency-v1",
        "month": month,
        "comparison_location": {"id": DWD_10416.id, "station_id": "10416"},
        "truth_source": "DWD WMO 10416",
        "comparison_mode": "monthly_common_valid_time",
        "forecast_selection": "freshest lead within the same provider/lead-bucket/valid-time; never selected by observed error",
        "common_comparison_timestamps_by_lead_bucket": common_counts,
        "common_sample_leaderboard": leaderboard,
        "common_sample_wins_losses": wins_losses,
        "ensemble_calibration": ensemble,
        "event_definitions": [
            {"variable": variable, "threshold": threshold, "direction": direction, "id": label}
            for variable, threshold, direction, label in EVENT_DEFINITIONS
        ],
        "event_summaries": events,
        "notable_misses": notable_misses,
        "weather_next_sample_confidence": sample_confidence(wn_n),
        "small_sample_warning": wn_n < 30,
        "notable_weather_next_misses": wn_misses,
        "notable_weather_next_wins": wn_wins,
        "release_notes_source": WEATHERNEXT_RELEASE_NOTES_URL,
        "release_note_events": release_events,
        "note": (
            "Home forecasts are excluded from measured skill until a home observation source exists. "
            "Monthly deterministic comparisons use only common station valid-times inside each lead bucket and exact provider model-version cohort; "
            "each comparison row exposes missingness and sample-sufficiency evidence, and bootstrap MAE intervals are emitted only when n>=30. "
            "Ensemble calibration exposes n/sufficiency beside CRPS, interval/WIS and precipitation Brier evidence and uses stored member_* values only. "
            "Release events are included only when previously recorded from verified source metadata."
        ),
    }
