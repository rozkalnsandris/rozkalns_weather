from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
import sqlite3
from typing import Iterable, Mapping

from .backfill import ARCHIVE_START, COMMON_BENCHMARK_START
from .db import Database
from .locations import DWD_10416
from .models import utc_iso
from .providers import PROVIDERS

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_CONTRACT = "corpus-provenance-manifest-v1"
MAX_WINDOW_DAYS = 180
_HASH64_RE = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_SCHEMA_COLUMNS: dict[str, dict[str, str]] = {
    "locations": {
        "id": "TEXT",
        "label": "TEXT",
        "lat": "REAL",
        "lon": "REAL",
        "elevation_m": "REAL",
        "timezone": "TEXT",
    },
    "forecast_runs": {
        "id": "INTEGER",
        "provider": "TEXT",
        "model_provider": "TEXT",
        "model_name": "TEXT",
        "model_version": "TEXT",
        "location_id": "TEXT",
        "init_time_utc": "TEXT",
        "retrieved_at_utc": "TEXT",
        "upstream_available_at_utc": "TEXT",
        "init_time_quality": "TEXT",
        "source_surface": "TEXT",
        "transport_provider": "TEXT",
        "raw_payload_hash": "TEXT",
        "revision": "INTEGER",
        "source_metadata_json": "TEXT",
        "status": "TEXT",
    },
    "forecast_values": {
        "id": "INTEGER",
        "run_id": "INTEGER",
        "location_id": "TEXT",
        "valid_time_utc": "TEXT",
        "lead_hours": "REAL",
        "variable": "TEXT",
        "statistic": "TEXT",
        "value": "REAL",
        "unit": "TEXT",
        "native_value": "REAL",
        "native_unit": "TEXT",
        "accumulation_window_minutes": "INTEGER",
        "quality_status": "TEXT",
    },
    "observations": {
        "id": "INTEGER",
        "source_provider": "TEXT",
        "station_id": "TEXT",
        "location_id": "TEXT",
        "observed_at_utc": "TEXT",
        "variable": "TEXT",
        "value": "REAL",
        "unit": "TEXT",
        "quality_status": "TEXT",
        "source_metadata_json": "TEXT",
    },
    "provider_ingest_status": {
        "provider": "TEXT",
        "model_name": "TEXT",
        "last_attempt_at_utc": "TEXT",
        "last_success_at_utc": "TEXT",
        "last_init_time_utc": "TEXT",
        "state": "TEXT",
        "detail": "TEXT",
    },
    "model_events": {
        "id": "INTEGER",
        "provider": "TEXT",
        "model_version": "TEXT",
        "effective_at_utc": "TEXT",
        "event_type": "TEXT",
        "source_url": "TEXT",
        "note": "TEXT",
    },
}

EXPECTED_PROVIDER_IDENTITIES = {
    descriptor.id: (descriptor.model_provider, descriptor.model_name)
    for descriptor in PROVIDERS
    if descriptor.id != "dwd_observations"
}

CRITICAL_FORECAST_FIELDS = (
    "provider",
    "model_provider",
    "model_name",
    "location_id",
    "init_time_utc",
    "retrieved_at_utc",
    "init_time_quality",
    "source_surface",
    "raw_payload_hash",
    "revision",
)


class CorpusManifestError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _readonly_connection(database: Database) -> sqlite3.Connection:
    if database.path == ":memory:":
        raise CorpusManifestError("PERSISTENT_DB_REQUIRED", "corpus manifest requires a persistent SQLite file")
    path = Path(database.path)
    if not path.is_file():
        raise CorpusManifestError("DATABASE_NOT_FOUND", "corpus database does not exist")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _window(start: date, end: date) -> tuple[str, str]:
    if end < start:
        raise CorpusManifestError("INVALID_WINDOW", "end must not be before start")
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        raise CorpusManifestError("WINDOW_TOO_LARGE", f"window must be <= {MAX_WINDOW_DAYS} inclusive days")
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return utc_iso(start_dt), utc_iso(end_dt)


def _parse_utc(value: object, *, field: str) -> datetime:
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CorpusManifestError("INVALID_TIMESTAMP", f"{field} must be ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise CorpusManifestError("INVALID_TIMESTAMP", f"{field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _schema_identity(connection: sqlite3.Connection) -> tuple[dict[str, object], list[str]]:
    actual_tables = sorted(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    )
    issues: list[str] = []
    expected_tables = sorted(EXPECTED_SCHEMA_COLUMNS)
    if actual_tables != expected_tables:
        issues.append("SCHEMA_TABLE_SET_MISMATCH")
    actual: dict[str, dict[str, str]] = {}
    for table in actual_tables:
        columns = {
            str(row["name"]): str(row["type"]).upper()
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        actual[table] = dict(sorted(columns.items()))
        expected = EXPECTED_SCHEMA_COLUMNS.get(table)
        if expected is None or actual[table] != dict(sorted(expected.items())):
            issues.append(f"SCHEMA_COLUMNS_MISMATCH:{table}")
    normalized = {"schema_version": 1, "tables": actual}
    return {
        "version": 1,
        "identity_sha256": _sha256(normalized),
        "expected_identity_sha256": _sha256(
            {"schema_version": 1, "tables": {name: dict(sorted(columns.items())) for name, columns in sorted(EXPECTED_SCHEMA_COLUMNS.items())}}
        ),
        "tables": actual_tables,
    }, issues


def _forecast_entry(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "provider": str(row["provider"]),
        "model_provider": str(row["model_provider"]),
        "model_name": str(row["model_name"]),
        "model_version": row["model_version"],
        "location_id": str(row["location_id"]),
        "init_time_utc": str(row["init_time_utc"]),
        "retrieved_at_utc": str(row["retrieved_at_utc"]),
        "init_time_quality": str(row["init_time_quality"]),
        "source_surface": str(row["source_surface"]),
        "raw_payload_hash": str(row["raw_payload_hash"]),
        "revision": int(row["revision"]),
    }


def _forecast_sort_key(row: Mapping[str, object]) -> tuple[object, ...]:
    return (
        str(row["provider"]),
        str(row["model_name"]),
        str(row["location_id"]),
        str(row["init_time_utc"]),
        int(row["revision"]),
        str(row["retrieved_at_utc"]),
        str(row["raw_payload_hash"]),
    )


def _validate_forecasts(rows: Iterable[Mapping[str, object]]) -> tuple[list[dict[str, object]], list[str], list[str]]:
    entries: list[dict[str, object]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    groups: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        missing = [field for field in CRITICAL_FORECAST_FIELDS if row[field] in (None, "")]
        if missing:
            blockers.append("MISSING_FORECAST_PROVENANCE")
            continue
        entry = _forecast_entry(row)
        provider = str(entry["provider"])
        expected_identity = EXPECTED_PROVIDER_IDENTITIES.get(provider)
        if expected_identity is None:
            blockers.append("UNEXPECTED_PROVIDER_IDENTITY")
        elif (entry["model_provider"], entry["model_name"]) != expected_identity:
            blockers.append("PROVIDER_IDENTITY_MISMATCH")
        if not _HASH64_RE.fullmatch(str(entry["raw_payload_hash"])):
            blockers.append("INVALID_RAW_PAYLOAD_HASH")
        try:
            _parse_utc(entry["init_time_utc"], field="init_time_utc")
            _parse_utc(entry["retrieved_at_utc"], field="retrieved_at_utc")
        except CorpusManifestError:
            blockers.append("INVALID_FORECAST_TIMESTAMP")
        if int(entry["revision"]) < 1:
            blockers.append("INVALID_REVISION")
        if entry["model_version"] in (None, ""):
            warnings.append("MODEL_VERSION_MISSING")
        entries.append(entry)
        groups[(provider, str(entry["model_name"]), str(entry["location_id"]), str(entry["init_time_utc"]))].append(entry)
    for snapshots in groups.values():
        ordered = sorted(snapshots, key=lambda item: (int(item["revision"]), str(item["retrieved_at_utc"])))
        revisions = [int(item["revision"]) for item in ordered]
        if len(set(revisions)) != len(revisions):
            blockers.append("DUPLICATE_SNAPSHOT_IDENTITY")
        if revisions and revisions != list(range(1, max(revisions) + 1)):
            blockers.append("BROKEN_REVISION_CHAIN")
        hashes = [str(item["raw_payload_hash"]) for item in ordered]
        if len(set(hashes)) != len(hashes):
            blockers.append("DUPLICATE_SNAPSHOT_PAYLOAD")
        retrievals = [str(item["retrieved_at_utc"]) for item in ordered]
        if retrievals != sorted(retrievals):
            blockers.append("BROKEN_REVISION_RETRIEVAL_ORDER")
    entries.sort(key=_forecast_sort_key)
    return entries, blockers, warnings


def _observation_entry(row: Mapping[str, object]) -> dict[str, object]:
    value = float(row["value"])
    if not isfinite(value):
        raise CorpusManifestError("NON_FINITE_OBSERVATION", "observation value must be finite")
    identity = {
        "source_provider": str(row["source_provider"]),
        "station_id": row["station_id"],
        "location_id": row["location_id"],
        "observed_at_utc": str(row["observed_at_utc"]),
        "variable": str(row["variable"]),
        "value": value,
        "unit": str(row["unit"]),
        "quality_status": row["quality_status"],
    }
    return {
        "source_provider": identity["source_provider"],
        "station_id": identity["station_id"],
        "location_id": identity["location_id"],
        "observed_at_utc": identity["observed_at_utc"],
        "variable": identity["variable"],
        "unit": identity["unit"],
        "quality_status": identity["quality_status"],
        "record_sha256": _sha256(identity),
    }


def _validate_observations(rows: Iterable[Mapping[str, object]]) -> tuple[list[dict[str, object]], list[str]]:
    entries: list[dict[str, object]] = []
    blockers: list[str] = []
    seen: set[tuple[object, ...]] = set()
    for row in rows:
        required = ("source_provider", "observed_at_utc", "variable", "value", "unit")
        if any(row[field] in (None, "") for field in required):
            blockers.append("MISSING_OBSERVATION_PROVENANCE")
            continue
        try:
            _parse_utc(row["observed_at_utc"], field="observed_at_utc")
            entry = _observation_entry(row)
        except CorpusManifestError:
            blockers.append("INVALID_OBSERVATION_PROVENANCE")
            continue
        identity = (entry["source_provider"], entry["station_id"], entry["observed_at_utc"], entry["variable"])
        if identity in seen:
            blockers.append("DUPLICATE_OBSERVATION_IDENTITY")
        seen.add(identity)
        if entry["location_id"] == DWD_10416.id and (
            entry["source_provider"] != "DWD" or str(entry["station_id"]) != "10416"
        ):
            blockers.append("UNEXPECTED_OBSERVATION_SOURCE_IDENTITY")
        entries.append(entry)
    entries.sort(
        key=lambda item: (
            str(item["source_provider"]),
            str(item["station_id"] or ""),
            str(item["location_id"] or ""),
            str(item["observed_at_utc"]),
            str(item["variable"]),
        )
    )
    return entries, blockers


def _section(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "count": len(entries),
        "entries": entries,
        "checksum_sha256": _sha256(entries),
    }


def build_corpus_provenance_manifest(database: Database, *, start: date, end: date) -> dict[str, object]:
    start_iso, end_iso = _window(start, end)
    common_boundary = utc_iso(datetime.combine(COMMON_BENCHMARK_START, time.min, tzinfo=timezone.utc))
    with _readonly_connection(database) as connection:
        schema, schema_issues = _schema_identity(connection)
        forecast_rows = [
            dict(row)
            for row in connection.execute(
                """SELECT provider,model_provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,
                          init_time_quality,source_surface,raw_payload_hash,revision
                   FROM forecast_runs WHERE init_time_utc>=? AND init_time_utc<?
                   ORDER BY provider,model_name,location_id,init_time_utc,revision,retrieved_at_utc""",
                (start_iso, end_iso),
            ).fetchall()
        ]
        observation_rows = [
            dict(row)
            for row in connection.execute(
                """SELECT source_provider,station_id,location_id,observed_at_utc,variable,value,unit,quality_status
                   FROM observations WHERE observed_at_utc>=? AND observed_at_utc<?
                   ORDER BY source_provider,station_id,location_id,observed_at_utc,variable""",
                (start_iso, end_iso),
            ).fetchall()
        ]

    forecast_entries, forecast_blockers, forecast_warnings = _validate_forecasts(forecast_rows)
    observation_entries, observation_blockers = _validate_observations(observation_rows)

    historical_forecasts = [entry for entry in forecast_entries if str(entry["init_time_utc"]) < common_boundary]
    common_forecasts = [entry for entry in forecast_entries if str(entry["init_time_utc"]) >= common_boundary]
    historical_observations = [entry for entry in observation_entries if str(entry["observed_at_utc"]) < common_boundary]
    common_observations = [entry for entry in observation_entries if str(entry["observed_at_utc"]) >= common_boundary]

    blockers = list(schema_issues) + forecast_blockers + observation_blockers
    if any(entry["provider"] != "ecmwf_ifs" for entry in historical_forecasts):
        blockers.append("NON_IFS_PRE_COMMON_PROVIDER")

    blockers = sorted(set(blockers))
    warnings = sorted(set(forecast_warnings))
    state = "BLOCKED" if blockers else "WARN" if warnings else "PASS"

    common_section = {
        "forecast_snapshots": _section(common_forecasts),
        "observations": _section(common_observations),
    }
    historical_section = {
        "archive_start": ARCHIVE_START["ecmwf_ifs"].isoformat(),
        "end_before_common_window": (COMMON_BENCHMARK_START - timedelta(days=1)).isoformat(),
        "excluded_from_common_readiness": True,
        "forecast_snapshots": _section(historical_forecasts),
        "observations": _section(historical_observations),
    }
    aggregate_input = {
        "schema_identity_sha256": schema["identity_sha256"],
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "common": common_section,
        "historical_ifs_only": historical_section,
    }
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "contract": MANIFEST_CONTRACT,
        "state": state,
        "block_reasons": blockers,
        "warn_reasons": warnings,
        "read_only": True,
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "start_inclusive_utc": start_iso,
            "end_exclusive_utc": end_iso,
            "max_inclusive_days": MAX_WINDOW_DAYS,
            "common_archive_start": COMMON_BENCHMARK_START.isoformat(),
        },
        "corpus_schema": schema,
        "common_window": common_section,
        "historical_ifs_only": historical_section,
        "aggregate_checksum_sha256": _sha256(aggregate_input),
        "authority": {
            "production_data_authority_granted": False,
            "runtime_live_authority_granted": False,
        },
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
            "raw_logs_exposed": False,
            "source_metadata_exported": False,
        },
    }


def main() -> None:
    import argparse

    from .config import Settings

    parser = argparse.ArgumentParser(prog="python -m rozkalns_weather.corpus_manifest")
    parser.add_argument("--start", required=True, help="manifest start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="manifest end date YYYY-MM-DD")
    args = parser.parse_args()
    settings = Settings.from_env()
    database = Database(settings.database_url)
    try:
        payload = build_corpus_provenance_manifest(
            database,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
        )
    except (CorpusManifestError, ValueError) as exc:
        payload = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "contract": MANIFEST_CONTRACT,
            "state": "BLOCKED",
            "block_reasons": [getattr(exc, "reason_code", "INVALID_ARGUMENT")],
            "detail": str(exc),
            "read_only": True,
            "authority": {
                "production_data_authority_granted": False,
                "runtime_live_authority_granted": False,
            },
            "privacy": {
                "coordinates_exposed": False,
                "credentials_exposed": False,
                "database_path_exposed": False,
                "raw_logs_exposed": False,
                "source_metadata_exported": False,
            },
        }
        print(json.dumps(payload, sort_keys=True, indent=2))
        raise SystemExit(3)
    print(json.dumps(payload, sort_keys=True, indent=2))
    if payload["state"] == "BLOCKED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
