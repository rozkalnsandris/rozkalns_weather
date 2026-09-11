from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Iterable

from .backfill import ARCHIVE_START, COMMON_BENCHMARK_START, MODEL_REGISTRY, iter_run_times
from .db import Database
from .locations import DWD_10416
from .models import utc_iso
from .verification import LEAD_BUCKETS, lead_bucket

DEFAULT_MODELS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
DEFAULT_RUN_HOURS = (0, 6, 12, 18)
MAX_EXAMPLES = 50
CRITICAL_PROVENANCE_FIELDS = (
    "model_provider",
    "model_name",
    "init_time_utc",
    "retrieved_at_utc",
    "init_time_quality",
    "source_surface",
    "raw_payload_hash",
)


def _readonly_connection(database: Database) -> sqlite3.Connection:
    if database.path == ":memory:":
        raise ValueError("corpus report requires a persistent SQLite file")
    path = Path(database.path)
    if not path.is_file():
        raise FileNotFoundError("corpus database does not exist")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _window(start: date, end: date) -> tuple[str, str]:
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return utc_iso(start_dt), utc_iso(end_dt)


def _examples(values: Iterable[str]) -> dict[str, object]:
    items = sorted(set(values))
    return {"count": len(items), "examples": items[:MAX_EXAMPLES], "truncated": len(items) > MAX_EXAMPLES}


def _model_summary(
    *,
    provider: str,
    expected_init_times: tuple[str, ...],
    rows: list[sqlite3.Row],
    value_window: dict[str, object],
    lead_counts: dict[str, int],
    lead_run_inits: dict[str, set[str]],
) -> tuple[dict[str, object], list[str], list[str]]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["init_time_utc"])].append(row)
    expected = set(expected_init_times)
    present = set(grouped)
    missing = expected - present
    unexpected = present - expected
    revision_inits: set[str] = set()
    duplicate_payload_inits: set[str] = set()
    critical_gaps: list[str] = []
    model_version_missing = 0
    snapshot_count = 0
    for init_time, snapshots in grouped.items():
        snapshot_count += len(snapshots)
        hashes = [str(row["raw_payload_hash"]) for row in snapshots if row["raw_payload_hash"]]
        if len(snapshots) > 1 or any(int(row["revision"]) > 1 for row in snapshots):
            revision_inits.add(init_time)
        if len(hashes) != len(set(hashes)):
            duplicate_payload_inits.add(init_time)
        for row in snapshots:
            for field in CRITICAL_PROVENANCE_FIELDS:
                if row[field] in (None, ""):
                    critical_gaps.append(f"{init_time}:{field}")
            if row["model_version"] in (None, ""):
                model_version_missing += 1
    expected_by_hour = Counter(datetime.fromisoformat(value.replace("Z", "+00:00")).hour for value in expected_init_times)
    present_by_hour = Counter(
        datetime.fromisoformat(value.replace("Z", "+00:00")).hour for value in present if value in expected
    )
    by_run_hour = {
        f"{hour:02d}": {
            "expected_runs": expected_by_hour.get(hour, 0),
            "present_runs": present_by_hour.get(hour, 0),
            "missing_runs": expected_by_hour.get(hour, 0) - present_by_hour.get(hour, 0),
        }
        for hour in DEFAULT_RUN_HOURS
    }
    blockers: list[str] = []
    warnings: list[str] = []
    prefix = provider.upper()
    if missing:
        blockers.append(f"{prefix}_MISSING_EXPECTED_RUNS")
    if unexpected:
        blockers.append(f"{prefix}_UNEXPECTED_RUNS")
    if revision_inits:
        blockers.append(f"{prefix}_REVISION_ANOMALIES")
    if duplicate_payload_inits:
        blockers.append(f"{prefix}_DUPLICATE_PAYLOADS")
    if critical_gaps:
        blockers.append(f"{prefix}_CRITICAL_PROVENANCE_GAPS")
    if model_version_missing:
        warnings.append(f"{prefix}_MODEL_VERSION_MISSING")
    horizon_hours = MODEL_REGISTRY[provider].forecast_days * 24
    expected_lead_buckets = tuple(label for lower, _upper, label in LEAD_BUCKETS if lower < horizon_hours)
    lead_bucket_coverage: dict[str, object] = {}
    lead_bucket_gaps = False
    for bucket in expected_lead_buckets:
        present_inits = set(lead_run_inits.get(bucket, set())) & expected
        missing_inits = expected - present_inits
        lead_bucket_coverage[bucket] = {
            "expected_runs": len(expected),
            "present_runs": len(present_inits),
            "missing_runs": _examples(missing_inits),
            "value_count": int(lead_counts.get(bucket, 0)),
        }
        lead_bucket_gaps = lead_bucket_gaps or bool(missing_inits)
    if lead_bucket_gaps:
        blockers.append(f"{prefix}_LEAD_BUCKET_COVERAGE_GAPS")
    summary = {
        "provider": provider,
        "expected_runs": len(expected),
        "present_runs": len(present & expected),
        "snapshot_count": snapshot_count,
        "missing_runs": _examples(missing),
        "unexpected_runs": _examples(unexpected),
        "revision_anomalies": _examples(revision_inits),
        "duplicate_payloads": _examples(duplicate_payload_inits),
        "by_run_hour_utc": by_run_hour,
        "valid_window": value_window,
        "expected_lead_buckets": list(expected_lead_buckets),
        "lead_bucket_coverage": lead_bucket_coverage,
        "lead_bucket_value_counts": dict(sorted(lead_counts.items())),
        "provenance": {
            "critical_gap_count": len(critical_gaps),
            "critical_gap_examples": sorted(critical_gaps)[:MAX_EXAMPLES],
            "critical_gap_examples_truncated": len(critical_gaps) > MAX_EXAMPLES,
            "model_version_missing_snapshots": model_version_missing,
        },
    }
    return summary, blockers, warnings


def public_corpus_report(
    database: Database,
    *,
    start: date,
    end: date,
    models: tuple[str, ...] = DEFAULT_MODELS,
    run_hours: tuple[int, ...] = DEFAULT_RUN_HOURS,
) -> dict[str, object]:
    if end < start:
        raise ValueError("report end date must not be before start date")
    if tuple(models) != DEFAULT_MODELS:
        raise ValueError("public corpus report requires exact icon_d2/ecmwf_ifs/ecmwf_aifs scope")
    if tuple(run_hours) != DEFAULT_RUN_HOURS:
        raise ValueError("public corpus report requires exact 00/06/12/18 UTC run-hour scope")
    common_start = max(start, COMMON_BENCHMARK_START)
    if end < common_start:
        raise ValueError(f"report must include common comparison window from {COMMON_BENCHMARK_START.isoformat()}")
    start_iso, end_iso = _window(common_start, end)
    placeholders = ",".join("?" for _ in models)
    with _readonly_connection(database) as connection:
        runs = connection.execute(
            f"""SELECT provider,model_provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,
                       init_time_quality,source_surface,raw_payload_hash,revision
                FROM forecast_runs
                WHERE location_id=? AND provider IN ({placeholders}) AND init_time_utc>=? AND init_time_utc<?
                ORDER BY provider,init_time_utc,revision""",
            (DWD_10416.id, *models, start_iso, end_iso),
        ).fetchall()
        value_bounds = connection.execute(
            f"""SELECT r.provider,COUNT(*) AS value_count,MIN(v.valid_time_utc) AS first_valid_time_utc,
                       MAX(v.valid_time_utc) AS last_valid_time_utc,MIN(v.lead_hours) AS min_lead_hours,MAX(v.lead_hours) AS max_lead_hours
                FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id
                WHERE r.location_id=? AND r.provider IN ({placeholders}) AND r.init_time_utc>=? AND r.init_time_utc<?
                GROUP BY r.provider ORDER BY r.provider""",
            (DWD_10416.id, *models, start_iso, end_iso),
        ).fetchall()
        lead_rows = connection.execute(
            f"""SELECT r.provider,r.init_time_utc,v.lead_hours,COUNT(*) AS n
                FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id
                WHERE r.location_id=? AND r.provider IN ({placeholders}) AND r.init_time_utc>=? AND r.init_time_utc<?
                GROUP BY r.provider,r.init_time_utc,v.lead_hours ORDER BY r.provider,r.init_time_utc,v.lead_hours""",
            (DWD_10416.id, *models, start_iso, end_iso),
        ).fetchall()
        forecast_valid = {
            str(row[0])
            for row in connection.execute(
                f"""SELECT DISTINCT v.valid_time_utc
                    FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id
                    WHERE r.location_id=? AND r.provider IN ({placeholders})
                      AND r.init_time_utc>=? AND r.init_time_utc<?
                      AND v.valid_time_utc>=? AND v.valid_time_utc<?
                      AND v.variable='temperature_2m' AND v.statistic IN ('deterministic','mean')""",
                (DWD_10416.id, *models, start_iso, end_iso, start_iso, end_iso),
            ).fetchall()
        }
        observed_valid = {
            str(row[0])
            for row in connection.execute(
                """SELECT DISTINCT observed_at_utc FROM observations
                   WHERE source_provider='DWD' AND station_id='10416' AND location_id=?
                     AND variable='temperature_2m' AND observed_at_utc>=? AND observed_at_utc<?""",
                (DWD_10416.id, start_iso, end_iso),
            ).fetchall()
        }
        observation_gaps = int(
            connection.execute(
                """WITH ordered AS (
                     SELECT observed_at_utc,LAG(observed_at_utc) OVER (ORDER BY observed_at_utc) AS prev
                     FROM observations
                     WHERE source_provider='DWD' AND station_id='10416' AND location_id=?
                       AND variable='temperature_2m' AND observed_at_utc>=? AND observed_at_utc<?
                   ) SELECT COUNT(*) FROM ordered
                     WHERE prev IS NOT NULL AND (julianday(observed_at_utc)-julianday(prev))*24.0>2.01""",
                (DWD_10416.id, start_iso, end_iso),
            ).fetchone()[0]
        )
        ifs_history_start = utc_iso(datetime.combine(ARCHIVE_START["ecmwf_ifs"], time.min, tzinfo=timezone.utc))
        historical_ifs = connection.execute(
            """SELECT COUNT(DISTINCT init_time_utc) AS init_count,COUNT(*) AS snapshot_count,
                      MIN(init_time_utc) AS first_init_time_utc,MAX(init_time_utc) AS last_init_time_utc
               FROM forecast_runs WHERE location_id=? AND provider='ecmwf_ifs'
                 AND init_time_utc>=? AND init_time_utc<?""",
            (DWD_10416.id, ifs_history_start, utc_iso(datetime.combine(COMMON_BENCHMARK_START, time.min, tzinfo=timezone.utc))),
        ).fetchone()
    rows_by_provider: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in runs:
        rows_by_provider[str(row["provider"])].append(row)
    bounds_by_provider = {
        str(row["provider"]): {
            "value_count": int(row["value_count"]),
            "first_valid_time_utc": row["first_valid_time_utc"],
            "last_valid_time_utc": row["last_valid_time_utc"],
            "min_lead_hours": row["min_lead_hours"],
            "max_lead_hours": row["max_lead_hours"],
        }
        for row in value_bounds
    }
    leads_by_provider: dict[str, Counter[str]] = defaultdict(Counter)
    lead_inits_by_provider: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in lead_rows:
        provider = str(row["provider"])
        bucket = lead_bucket(float(row["lead_hours"]))
        leads_by_provider[provider][bucket] += int(row["n"])
        lead_inits_by_provider[provider][bucket].add(str(row["init_time_utc"]))
    expected_init_times = tuple(utc_iso(value) for value in iter_run_times(common_start, end, run_hours))
    model_summaries: list[dict[str, object]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    for provider in models:
        summary, model_blockers, model_warnings = _model_summary(
            provider=provider,
            expected_init_times=expected_init_times,
            rows=rows_by_provider.get(provider, []),
            value_window=bounds_by_provider.get(
                provider,
                {"value_count": 0, "first_valid_time_utc": None, "last_valid_time_utc": None, "min_lead_hours": None, "max_lead_hours": None},
            ),
            lead_counts=dict(leads_by_provider.get(provider, {})),
            lead_run_inits=dict(lead_inits_by_provider.get(provider, {})),
        )
        model_summaries.append(summary)
        blockers.extend(model_blockers)
        warnings.extend(model_warnings)
    missing_truth = forecast_valid - observed_valid
    if missing_truth:
        blockers.append("DWD_OBSERVATION_COVERAGE_GAPS")
    blockers = list(dict.fromkeys(blockers))
    warnings = list(dict.fromkeys(warnings))
    state = "BLOCKED" if blockers else "WARN" if warnings else "PASS"
    return {
        "schema_version": 1,
        "state": state,
        "block_reasons": blockers,
        "warn_reasons": warnings,
        "read_only": True,
        "common_window": {
            "requested_start": start.isoformat(),
            "effective_start": common_start.isoformat(),
            "end": end.isoformat(),
            "common_archive_start": COMMON_BENCHMARK_START.isoformat(),
            "location_id": DWD_10416.id,
            "models": list(models),
            "run_hours_utc": list(run_hours),
        },
        "models": model_summaries,
        "observations": {
            "source_provider": "DWD",
            "station_id": "10416",
            "variable": "temperature_2m",
            "forecast_valid_times_in_window": len(forecast_valid),
            "matched_truth_times": len(forecast_valid & observed_valid),
            "missing_truth_times": _examples(missing_truth),
            "continuity_gaps_over_2h": observation_gaps,
        },
        "historical_ifs_only": {
            "archive_start": ARCHIVE_START["ecmwf_ifs"].isoformat(),
            "end_before_common_window": (COMMON_BENCHMARK_START - timedelta(days=1)).isoformat(),
            "present_init_times": int(historical_ifs["init_count"] or 0),
            "snapshot_count": int(historical_ifs["snapshot_count"] or 0),
            "first_init_time_utc": historical_ifs["first_init_time_utc"],
            "last_init_time_utc": historical_ifs["last_init_time_utc"],
            "excluded_from_common_readiness": True,
        },
        "authority": {
            "production_data_authority_granted": False,
            "runtime_live_authority_granted": False,
        },
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
            "raw_logs_exposed": False,
        },
    }
