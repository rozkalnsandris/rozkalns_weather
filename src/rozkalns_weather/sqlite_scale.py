from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import sqlite3
from typing import Iterable, Sequence

from .db import SCHEMA_SQL

CONTRACT = "sqlite-scale-index-readiness-v1"
SCHEMA_VERSION = 1
LOCATION_ID = "station_10416"
PROVIDERS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
MODEL_NAMES = {
    "icon_d2": "ICON-D2",
    "ecmwf_ifs": "IFS",
    "ecmwf_aifs": "AIFS",
}
SCALE_RUNS_PER_PROVIDER = {"small": 8, "medium": 64, "large": 256}
LEADS_HOURS = tuple(range(0, 73, 6))
VARIABLES = ("temperature_2m", "precipitation_1h")
QUERY_CLASSES = (
    "readiness",
    "corpus_report",
    "provider_health",
    "common_sample_verification",
    "monthly_reporting",
    "api_slice",
)
LARGE_TABLE_ALIASES = {
    "corpus_report": {"forecast_runs"},
    "provider_health": {"forecast_runs", "r", "v"},
    "common_sample_verification": {"r", "v", "o"},
    "monthly_reporting": {"r", "v", "o"},
    "api_slice": {"forecast_runs", "r", "v"},
}
WARN_SCORE = 4
BLOCK_SCORE = 9

INDEX_PROPOSAL = (
    {
        "name": "idx_proposed_forecast_runs_location_provider_retrieved",
        "sql": (
            "CREATE INDEX idx_proposed_forecast_runs_location_provider_retrieved "
            "ON forecast_runs(location_id, provider, retrieved_at_utc DESC)"
        ),
        "rollback_sql": "DROP INDEX IF EXISTS idx_proposed_forecast_runs_location_provider_retrieved",
        "query_classes": ["provider_health", "api_slice"],
        "expected_benefit": "replace corpus-wide latest-run scans with location/provider retrieval searches",
    },
    {
        "name": "idx_proposed_forecast_runs_location_provider_init",
        "sql": (
            "CREATE INDEX idx_proposed_forecast_runs_location_provider_init "
            "ON forecast_runs(location_id, provider, init_time_utc, revision)"
        ),
        "rollback_sql": "DROP INDEX IF EXISTS idx_proposed_forecast_runs_location_provider_init",
        "query_classes": ["corpus_report"],
        "expected_benefit": "bind bounded corpus windows to location/provider/init range searches",
    },
    {
        "name": "idx_proposed_forecast_values_variable_valid_run",
        "sql": (
            "CREATE INDEX idx_proposed_forecast_values_variable_valid_run "
            "ON forecast_values(variable, valid_time_utc, run_id, lead_hours)"
        ),
        "rollback_sql": "DROP INDEX IF EXISTS idx_proposed_forecast_values_variable_valid_run",
        "query_classes": ["common_sample_verification", "monthly_reporting", "api_slice"],
        "expected_benefit": "replace broad forecast-value scans with variable/time range searches",
    },
)


@dataclass(frozen=True)
class QuerySpec:
    name: str
    sql: str
    params: tuple[object, ...]


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _fixture_checksum(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for table, columns in (
        ("forecast_runs", "provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,raw_payload_hash,revision"),
        ("forecast_values", "run_id,location_id,valid_time_utc,lead_hours,variable,statistic,value,unit,accumulation_window_minutes"),
        ("observations", "source_provider,station_id,location_id,observed_at_utc,variable,value,unit,quality_status"),
        ("provider_ingest_status", "provider,model_name,last_attempt_at_utc,last_success_at_utc,last_init_time_utc,state"),
    ):
        for row in connection.execute(f"SELECT {columns} FROM {table} ORDER BY 1,2,3,4"):
            digest.update(_canonical_json(list(row)).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def _query_specs() -> tuple[QuerySpec, ...]:
    start = "2026-04-02T00:00:00Z"
    end = "2026-08-01T00:00:00Z"
    month_end = "2026-05-02T00:00:00Z"
    return (
        QuerySpec(
            "readiness",
            """SELECT provider,state,last_attempt_at_utc,last_success_at_utc,last_init_time_utc
               FROM provider_ingest_status ORDER BY provider""",
            (),
        ),
        QuerySpec(
            "corpus_report",
            """SELECT provider,model_provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,revision
               FROM forecast_runs
               WHERE location_id=? AND provider IN (?,?,?) AND init_time_utc>=? AND init_time_utc<?
               ORDER BY provider,init_time_utc,revision""",
            (LOCATION_ID, *PROVIDERS, start, end),
        ),
        QuerySpec(
            "provider_health",
            """WITH latest AS (
                 SELECT provider,MAX(retrieved_at_utc) AS retrieved_at_utc
                 FROM forecast_runs WHERE location_id=? GROUP BY provider
               )
               SELECT r.provider,r.init_time_utc,r.retrieved_at_utc,MAX(v.valid_time_utc) AS latest_valid_time_utc
               FROM latest l
               JOIN forecast_runs r ON r.provider=l.provider AND r.retrieved_at_utc=l.retrieved_at_utc
               JOIN forecast_values v ON v.run_id=r.id
               WHERE r.location_id=?
               GROUP BY r.id,r.provider,r.init_time_utc,r.retrieved_at_utc
               ORDER BY r.provider""",
            (LOCATION_ID, LOCATION_ID),
        ),
        QuerySpec(
            "common_sample_verification",
            """SELECT r.provider,r.model_version,r.init_time_utc,v.valid_time_utc,v.lead_hours,
                      v.value AS forecast_value,o.value AS observed_value
               FROM forecast_runs r
               JOIN forecast_values v ON v.run_id=r.id
               JOIN observations o ON o.variable='temperature_2m'
                 AND o.observed_at_utc=v.valid_time_utc
                 AND o.location_id=r.location_id
                 AND o.source_provider='DWD'
               WHERE r.location_id=? AND v.variable='temperature_2m'
                 AND v.statistic='deterministic'
                 AND v.valid_time_utc>=? AND v.valid_time_utc<?
               ORDER BY r.provider,r.init_time_utc,v.valid_time_utc""",
            (LOCATION_ID, start, end),
        ),
        QuerySpec(
            "monthly_reporting",
            """SELECT r.provider,r.model_version,
                      CASE WHEN v.lead_hours<24 THEN '0-24h'
                           WHEN v.lead_hours<72 THEN '24-72h'
                           ELSE '72h+' END AS lead_bucket,
                      COUNT(*) AS n,AVG(ABS(v.value-o.value)) AS mae
               FROM forecast_runs r
               JOIN forecast_values v ON v.run_id=r.id
               JOIN observations o ON o.location_id=r.location_id
                 AND o.observed_at_utc=v.valid_time_utc
                 AND o.variable='temperature_2m'
                 AND o.source_provider='DWD'
               WHERE r.location_id=? AND v.variable='temperature_2m'
                 AND v.statistic='deterministic'
                 AND v.valid_time_utc>=? AND v.valid_time_utc<?
               GROUP BY r.provider,r.model_version,lead_bucket
               ORDER BY r.provider,lead_bucket""",
            (LOCATION_ID, start, month_end),
        ),
        QuerySpec(
            "api_slice",
            """WITH latest AS (
                 SELECT provider,location_id,MAX(retrieved_at_utc) AS retrieved_at_utc
                 FROM forecast_runs WHERE location_id=? GROUP BY provider,location_id
               )
               SELECT r.provider,r.model_name,r.model_version,v.valid_time_utc,v.lead_hours,
                      v.variable,v.value,v.unit
               FROM latest l
               JOIN forecast_runs r ON r.provider=l.provider
                 AND r.location_id=l.location_id
                 AND r.retrieved_at_utc=l.retrieved_at_utc
               JOIN forecast_values v ON v.run_id=r.id
               WHERE v.variable=? AND v.lead_hours<=?
               ORDER BY v.valid_time_utc,r.provider,v.statistic""",
            (LOCATION_ID, "temperature_2m", 48),
        ),
    )


def build_synthetic_corpus(scale: str, *, candidate_indexes: bool = False) -> sqlite3.Connection:
    if scale not in SCALE_RUNS_PER_PROVIDER:
        raise ValueError(f"unknown scale: {scale}")
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "INSERT INTO locations(id,label,lat,lon,timezone) VALUES(?,?,?,?,?)",
        (LOCATION_ID, "DWD public benchmark fixture", 51.5, 7.6, "Europe/Berlin"),
    )
    start = datetime(2026, 4, 2, tzinfo=timezone.utc)
    observed_times: set[datetime] = set()
    runs_per_provider = SCALE_RUNS_PER_PROVIDER[scale]
    for provider_index, provider in enumerate(PROVIDERS):
        for run_index in range(runs_per_provider):
            init_time = start + timedelta(hours=6 * run_index)
            retrieved_at = init_time + timedelta(hours=2)
            raw_hash = hashlib.sha256(f"{scale}:{provider}:{run_index}".encode("utf-8")).hexdigest()
            cursor = connection.execute(
                """INSERT INTO forecast_runs(
                       provider,model_provider,model_name,model_version,location_id,
                       init_time_utc,retrieved_at_utc,init_time_quality,source_surface,
                       raw_payload_hash,revision,status
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    provider,
                    provider,
                    MODEL_NAMES[provider],
                    "fixture-v1",
                    LOCATION_ID,
                    _utc_iso(init_time),
                    _utc_iso(retrieved_at),
                    "exact",
                    "synthetic-fixture",
                    raw_hash,
                    1,
                    "ok",
                ),
            )
            run_id = int(cursor.lastrowid)
            values: list[tuple[object, ...]] = []
            for lead in LEADS_HOURS:
                valid_time = init_time + timedelta(hours=lead)
                observed_times.add(valid_time)
                values.append(
                    (
                        run_id,
                        LOCATION_ID,
                        _utc_iso(valid_time),
                        float(lead),
                        "temperature_2m",
                        "deterministic",
                        8.0 + provider_index + run_index / 100.0 + lead / 1000.0,
                        "C",
                        None,
                    )
                )
                values.append(
                    (
                        run_id,
                        LOCATION_ID,
                        _utc_iso(valid_time),
                        float(lead),
                        "precipitation_1h",
                        "deterministic",
                        float((provider_index + run_index + lead) % 5) / 10.0,
                        "mm",
                        60,
                    )
                )
            connection.executemany(
                """INSERT INTO forecast_values(
                       run_id,location_id,valid_time_utc,lead_hours,variable,statistic,
                       value,unit,accumulation_window_minutes
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                values,
            )
    for observed_index, observed_at in enumerate(sorted(observed_times)):
        connection.execute(
            """INSERT INTO observations(
                   source_provider,station_id,location_id,observed_at_utc,variable,
                   value,unit,quality_status
               ) VALUES('DWD','10416',?,?,'temperature_2m',?,'C','ok')""",
            (LOCATION_ID, _utc_iso(observed_at), 9.0 + observed_index / 1000.0),
        )
        connection.execute(
            """INSERT INTO observations(
                   source_provider,station_id,location_id,observed_at_utc,variable,
                   value,unit,quality_status
               ) VALUES('DWD','10416',?,?,'precipitation_1h',?,'mm','ok')""",
            (LOCATION_ID, _utc_iso(observed_at), float(observed_index % 3) / 10.0),
        )
    latest_init = start + timedelta(hours=6 * (runs_per_provider - 1))
    for provider in PROVIDERS:
        connection.execute(
            """INSERT INTO provider_ingest_status(
                   provider,model_name,last_attempt_at_utc,last_success_at_utc,last_init_time_utc,state
               ) VALUES(?,?,?,?,?,?)""",
            (
                provider,
                MODEL_NAMES[provider],
                _utc_iso(latest_init + timedelta(hours=2)),
                _utc_iso(latest_init + timedelta(hours=2)),
                _utc_iso(latest_init),
                "ok",
            ),
        )
    if candidate_indexes:
        for proposal in INDEX_PROPOSAL:
            connection.execute(str(proposal["sql"]))
    connection.commit()
    return connection


def fixture_summary(connection: sqlite3.Connection, scale: str) -> dict[str, object]:
    return {
        "scale": scale,
        "runs_per_provider": SCALE_RUNS_PER_PROVIDER[scale],
        "forecast_runs": int(connection.execute("SELECT COUNT(*) FROM forecast_runs").fetchone()[0]),
        "forecast_values": int(connection.execute("SELECT COUNT(*) FROM forecast_values").fetchone()[0]),
        "observations": int(connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]),
        "providers": len(PROVIDERS),
        "fixture_checksum": _fixture_checksum(connection),
    }


def _plan_details(connection: sqlite3.Connection, spec: QuerySpec) -> list[str]:
    rows = connection.execute("EXPLAIN QUERY PLAN " + spec.sql, spec.params).fetchall()
    return [str(row[3]) for row in rows]


def classify_plan(query_class: str, details: Sequence[str]) -> dict[str, object]:
    aliases = LARGE_TABLE_ALIASES.get(query_class, set())
    score = 0
    large_scans: list[str] = []
    temp_btrees = 0
    other_scans = 0
    for detail in details:
        normalized = detail.strip()
        if normalized.startswith("USE TEMP B-TREE"):
            temp_btrees += 1
            score += 1
            continue
        if normalized.startswith("SCAN "):
            token = normalized.split()[1]
            if token in aliases:
                large_scans.append(token)
                score += 4
            elif token != "provider_ingest_status":
                other_scans += 1
                score += 1
    state = "BLOCKED" if score >= BLOCK_SCORE else "WARN" if score >= WARN_SCORE else "PASS"
    reasons: list[str] = []
    if large_scans:
        reasons.append("LARGE_TABLE_SCAN")
    if temp_btrees >= 2:
        reasons.append("MULTIPLE_TEMP_BTREE")
    if score >= BLOCK_SCORE:
        reasons.append("PLAN_SCORE_BLOCKED")
    elif score >= WARN_SCORE:
        reasons.append("PLAN_SCORE_WARN")
    return {
        "state": state,
        "plan_score": score,
        "large_table_scans": large_scans,
        "other_scans": other_scans,
        "temp_btrees": temp_btrees,
        "reason_codes": reasons,
        "plan": list(details),
    }


def benchmark_connection(connection: sqlite3.Connection) -> dict[str, object]:
    results: dict[str, object] = {}
    for spec in _query_specs():
        details = _plan_details(connection, spec)
        classification = classify_plan(spec.name, details)
        row_count = sum(1 for _ in connection.execute(spec.sql, spec.params))
        results[spec.name] = {**classification, "result_rows": row_count}
    return results


def _aggregate_state(query_results: Iterable[dict[str, object]]) -> str:
    states = {str(item["state"]) for item in query_results}
    if "BLOCKED" in states:
        return "BLOCKED"
    if "WARN" in states:
        return "WARN"
    return "PASS"


def benchmark_scale(scale: str) -> dict[str, object]:
    baseline = build_synthetic_corpus(scale, candidate_indexes=False)
    candidate = build_synthetic_corpus(scale, candidate_indexes=True)
    try:
        baseline_fixture = fixture_summary(baseline, scale)
        candidate_fixture = fixture_summary(candidate, scale)
        baseline_results = benchmark_connection(baseline)
        candidate_results = benchmark_connection(candidate)
    finally:
        baseline.close()
        candidate.close()
    if baseline_fixture["fixture_checksum"] != candidate_fixture["fixture_checksum"]:
        raise RuntimeError("candidate index application changed synthetic corpus identity")
    improvements = {
        name: {
            "baseline_score": int(baseline_results[name]["plan_score"]),
            "candidate_score": int(candidate_results[name]["plan_score"]),
            "score_delta": int(baseline_results[name]["plan_score"]) - int(candidate_results[name]["plan_score"]),
        }
        for name in QUERY_CLASSES
    }
    candidate_regressions = [name for name, item in improvements.items() if int(item["score_delta"]) < 0]
    state = _aggregate_state(baseline_results.values())
    block_reasons: list[str] = []
    warn_reasons: list[str] = []
    if state == "BLOCKED":
        block_reasons.append("BASELINE_PLAN_THRESHOLD_EXCEEDED")
    elif state == "WARN":
        warn_reasons.append("BASELINE_INDEX_OPPORTUNITIES")
    if candidate_regressions:
        block_reasons.append("CANDIDATE_INDEX_PLAN_REGRESSION")
        state = "BLOCKED"
    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "block_reasons": block_reasons,
        "warn_reasons": warn_reasons,
        "synthetic_only": True,
        "fixture": baseline_fixture,
        "thresholds": {"warn_plan_score": WARN_SCORE, "blocked_plan_score": BLOCK_SCORE},
        "baseline": baseline_results,
        "candidate": candidate_results,
        "candidate_improvements": improvements,
        "candidate_regressions": candidate_regressions,
        "authority": {
            "production_data_authority_granted": False,
            "production_schema_or_index_mutation_authority_granted": False,
            "runtime_live_authority_granted": False,
        },
        "privacy": {
            "production_paths_read": False,
            "credentials_read": False,
            "private_coordinates_used": False,
            "raw_logs_used": False,
        },
    }


def index_proposal() -> dict[str, object]:
    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "status": "PROPOSAL_ONLY",
        "apply_to_production": False,
        "indexes": [dict(item) for item in INDEX_PROPOSAL],
        "preconditions": [
            "separate explicit production SQLite migration authority",
            "fresh production backup/readiness evidence",
            "exact reviewed schema identity",
            "bounded maintenance and rollback plan",
            "post-change EXPLAIN QUERY PLAN and integrity verification",
        ],
        "rollback_semantics": "DROP only the exact newly authorized index names after separate rollback authority; no implicit VACUUM or data rewrite",
    }


def run_benchmark(scales: Sequence[str] = ("small", "medium", "large")) -> dict[str, object]:
    unknown = [scale for scale in scales if scale not in SCALE_RUNS_PER_PROVIDER]
    if unknown:
        raise ValueError(f"unknown scales: {','.join(unknown)}")
    scale_results = [benchmark_scale(scale) for scale in scales]
    state = _aggregate_state(scale_results)
    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "scales": scale_results,
        "query_classes": list(QUERY_CLASSES),
        "index_proposal": index_proposal(),
        "source_only": True,
        "production_mutation_performed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic SQLite scale/index readiness benchmark")
    parser.add_argument(
        "--scales",
        default="small,medium,large",
        help="comma-separated subset of small,medium,large",
    )
    args = parser.parse_args(argv)
    scales = tuple(part.strip() for part in args.scales.split(",") if part.strip())
    try:
        payload = run_benchmark(scales)
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        payload = {
            "contract": CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "state": "BLOCKED",
            "block_reasons": ["BENCHMARK_EXECUTION_ERROR"],
            "detail": type(exc).__name__,
            "source_only": True,
            "production_mutation_performed": False,
        }
        print(json.dumps(payload, sort_keys=True))
        return 3
    print(json.dumps(payload, sort_keys=True))
    return 3 if payload["state"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
