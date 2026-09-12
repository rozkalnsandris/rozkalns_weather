from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
import sqlite3
from statistics import mean
from typing import Iterable, Mapping, Sequence

from .backfill import COMMON_BENCHMARK_START
from .config import Settings
from .db import Database, SCHEMA_SQL
from .locations import DWD_10416
from .probabilistic import brier_from_members, ensemble_crps, interval_score, weighted_interval_score
from .verification import ErrorPair, LEAD_BUCKETS, lead_bucket, sample_evidence, summarize

EXPORT_CONTRACT = "public-benchmark-export-v1"
EXPORT_SCHEMA_VERSION = 1
DETERMINISTIC_PROVIDERS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
ENSEMBLE_PROVIDERS = ("icon_d2_eps", "ecmwf_ifs_ens", "ecmwf_aifs_ens")
EXPORT_PROVIDERS = DETERMINISTIC_PROVIDERS + ENSEMBLE_PROVIDERS
EXPORT_VARIABLES = ("temperature_2m", "precipitation_1h", "wind_gust_10m")
DETERMINISTIC_STATISTICS = {"deterministic", "mean"}
PRECIP_EVENT_THRESHOLD_MM = 0.1
TEMPERATURE_INTERVAL_ALPHA = 0.2
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_HASH64_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEYS = {
    "lat",
    "latitude",
    "lon",
    "lng",
    "longitude",
    "home_lat",
    "home_lon",
    "credential",
    "credentials",
    "secret",
    "token",
    "password",
    "api_key",
    "google_cloud_project",
    "database_path",
    "runtime_path",
    "private_path",
    "raw_log",
    "raw_logs",
    "source_metadata_json",
}
_FORECAST_REQUIRED = (
    "provider",
    "model_provider",
    "model_name",
    "model_version",
    "location_id",
    "init_time_utc",
    "retrieved_at_utc",
    "init_time_quality",
    "source_surface",
    "raw_payload_hash",
    "revision",
    "valid_time_utc",
    "lead_hours",
    "variable",
    "statistic",
    "value",
    "unit",
)
_OBSERVATION_REQUIRED = (
    "source_provider",
    "station_id",
    "location_id",
    "observed_at_utc",
    "variable",
    "value",
    "unit",
)


class BenchmarkExportError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _ndjson(rows: Iterable[Mapping[str, object]]) -> bytes:
    return b"".join(_canonical_json(dict(row)) for row in rows)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_utc(value: object, *, field: str) -> datetime:
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BenchmarkExportError("INVALID_TIMESTAMP", f"{field} must be ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise BenchmarkExportError("INVALID_TIMESTAMP", f"{field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _window(start: date, end: date) -> tuple[str, str]:
    if end < start:
        raise BenchmarkExportError("INVALID_WINDOW", "end must not be before start")
    if start < COMMON_BENCHMARK_START:
        raise BenchmarkExportError(
            "NON_COMMON_WINDOW",
            f"export start must be on or after {COMMON_BENCHMARK_START.isoformat()}",
        )
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start_dt.isoformat().replace("+00:00", "Z"), end_dt.isoformat().replace("+00:00", "Z")


def _assert_no_private_fields(row: Mapping[str, object]) -> None:
    forbidden = sorted(key for key in row if key.lower() in _FORBIDDEN_KEYS)
    if forbidden:
        raise BenchmarkExportError("PRIVATE_FIELD_PRESENT", f"private/export-forbidden fields present: {','.join(forbidden)}")


def _validate_forecast_row(row: Mapping[str, object]) -> None:
    _assert_no_private_fields(row)
    missing = [field for field in _FORECAST_REQUIRED if row.get(field) in (None, "")]
    if missing:
        raise BenchmarkExportError("INCOMPLETE_PROVENANCE", f"forecast provenance missing: {','.join(missing)}")
    if row["location_id"] != DWD_10416.id:
        raise BenchmarkExportError("NON_STATION_LOCATION", "only station_10416 may be exported")
    provider = str(row["provider"])
    if provider not in EXPORT_PROVIDERS:
        raise BenchmarkExportError("UNSUPPORTED_PROVIDER", f"provider {provider} is outside public benchmark export scope")
    variable = str(row["variable"])
    if variable not in EXPORT_VARIABLES:
        raise BenchmarkExportError("UNSUPPORTED_VARIABLE", f"variable {variable} is outside benchmark export scope")
    statistic = str(row["statistic"])
    if provider in DETERMINISTIC_PROVIDERS and statistic not in DETERMINISTIC_STATISTICS:
        raise BenchmarkExportError("UNSUPPORTED_STATISTIC", f"{provider} requires deterministic/mean statistics")
    if provider in ENSEMBLE_PROVIDERS and not re.fullmatch(r"member_\d+", statistic):
        raise BenchmarkExportError("UNSUPPORTED_STATISTIC", f"{provider} requires genuine member_N statistics")
    raw_hash = str(row["raw_payload_hash"])
    if not _HASH64_RE.fullmatch(raw_hash):
        raise BenchmarkExportError("INVALID_PROVENANCE_HASH", "raw_payload_hash must be 64 lowercase hex characters")
    revision = int(row["revision"])
    if revision < 1:
        raise BenchmarkExportError("INVALID_REVISION", "revision must be >= 1")
    init_time = _parse_utc(row["init_time_utc"], field="init_time_utc")
    _parse_utc(row["retrieved_at_utc"], field="retrieved_at_utc")
    if row.get("upstream_available_at_utc") not in (None, ""):
        _parse_utc(row["upstream_available_at_utc"], field="upstream_available_at_utc")
    valid_time = _parse_utc(row["valid_time_utc"], field="valid_time_utc")
    lead_hours = float(row["lead_hours"])
    if not isfinite(lead_hours) or lead_hours < 0:
        raise BenchmarkExportError("INVALID_LEAD", "lead_hours must be finite and non-negative")
    expected_lead = (valid_time - init_time).total_seconds() / 3600.0
    if abs(expected_lead - lead_hours) > 1e-6:
        raise BenchmarkExportError("LEAD_TIME_MISMATCH", "lead_hours must equal valid_time_utc - init_time_utc")
    if not isfinite(float(row["value"])):
        raise BenchmarkExportError("NON_FINITE_VALUE", "forecast value must be finite")


def _validate_observation_row(row: Mapping[str, object]) -> None:
    _assert_no_private_fields(row)
    missing = [field for field in _OBSERVATION_REQUIRED if row.get(field) in (None, "")]
    if missing:
        raise BenchmarkExportError("INCOMPLETE_TRUTH_PROVENANCE", f"observation provenance missing: {','.join(missing)}")
    if row["source_provider"] != "DWD" or str(row["station_id"]) != "10416":
        raise BenchmarkExportError("NON_DWD_TRUTH", "truth export requires DWD WMO 10416")
    if row["location_id"] != DWD_10416.id:
        raise BenchmarkExportError("NON_STATION_LOCATION", "truth export requires station_10416")
    if str(row["variable"]) not in EXPORT_VARIABLES:
        raise BenchmarkExportError("UNSUPPORTED_VARIABLE", "truth variable is outside benchmark export scope")
    _parse_utc(row["observed_at_utc"], field="observed_at_utc")
    if not isfinite(float(row["value"])):
        raise BenchmarkExportError("NON_FINITE_VALUE", "observation value must be finite")


def _forecast_identity(row: Mapping[str, object]) -> tuple[object, ...]:
    window = row.get("accumulation_window_minutes")
    return (
        str(row["provider"]), str(row["model_name"]), str(row["model_version"]), str(row["init_time_utc"]),
        str(row["retrieved_at_utc"]), int(row["revision"]), str(row["valid_time_utc"]), str(row["variable"]),
        str(row["statistic"]), -1 if window is None else int(window),
    )


def _observation_identity(row: Mapping[str, object]) -> tuple[object, ...]:
    return (row["source_provider"], row["station_id"], row["observed_at_utc"], row["variable"])


def _validate_rows(
    forecast_rows: Sequence[Mapping[str, object]], observation_rows: Sequence[Mapping[str, object]]
) -> dict[str, str]:
    if not forecast_rows:
        raise BenchmarkExportError("NO_FORECAST_ROWS", "benchmark export requires forecast rows")
    if not observation_rows:
        raise BenchmarkExportError("NO_OBSERVATION_ROWS", "benchmark export requires DWD truth rows")
    forecast_seen: set[tuple[object, ...]] = set()
    versions: dict[str, set[str]] = defaultdict(set)
    for row in forecast_rows:
        _validate_forecast_row(row)
        identity = _forecast_identity(row)
        if identity in forecast_seen:
            raise BenchmarkExportError("DUPLICATE_FORECAST_IDENTITY", "duplicate forecast export identity")
        forecast_seen.add(identity)
        versions[str(row["provider"])].add(str(row["model_version"]))
    missing_deterministic = sorted(set(DETERMINISTIC_PROVIDERS) - set(versions))
    if missing_deterministic:
        raise BenchmarkExportError(
            "MISSING_DETERMINISTIC_PROVIDER",
            f"public benchmark export requires all deterministic providers: {','.join(missing_deterministic)}",
        )
    mixed = {provider: sorted(values) for provider, values in versions.items() if len(values) > 1}
    if mixed:
        raise BenchmarkExportError("MIXED_MODEL_VERSIONS", f"split export at model-version boundaries: {mixed}")
    observation_seen: set[tuple[object, ...]] = set()
    for row in observation_rows:
        _validate_observation_row(row)
        identity = _observation_identity(row)
        if identity in observation_seen:
            raise BenchmarkExportError("DUPLICATE_TRUTH_IDENTITY", "duplicate observation export identity")
        observation_seen.add(identity)
    return {provider: next(iter(values)) for provider, values in sorted(versions.items())}


def _latest_revision_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    latest: dict[tuple[str, str, str, str], int] = {}
    for row in rows:
        key = (str(row["provider"]), str(row["model_name"]), str(row["model_version"]), str(row["init_time_utc"]))
        latest[key] = max(latest.get(key, 0), int(row["revision"]))
    output = [
        dict(row)
        for row in rows
        if int(row["revision"]) == latest[(str(row["provider"]), str(row["model_name"]), str(row["model_version"]), str(row["init_time_utc"]))]
    ]
    return output


def _selected_deterministic_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    selected: dict[tuple[str, str, str], dict[str, object]] = {}
    candidates = [row for row in _latest_revision_rows(rows) if str(row["provider"]) in DETERMINISTIC_PROVIDERS]
    candidates.sort(key=lambda row: str(row["retrieved_at_utc"]), reverse=True)
    candidates.sort(key=lambda row: float(row["lead_hours"]))
    for row in candidates:
        if str(row["statistic"]) not in DETERMINISTIC_STATISTICS:
            continue
        bucket = lead_bucket(float(row["lead_hours"]))
        key = (str(row["provider"]), str(row["variable"]), str(row["valid_time_utc"]), bucket)
        if key not in selected:
            selected[key] = dict(row)
    return sorted(selected.values(), key=lambda row: (str(row["variable"]), lead_bucket(float(row["lead_hours"])), str(row["valid_time_utc"]), str(row["provider"])))


def _truth_map(observations: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], float]:
    return {(str(row["observed_at_utc"]), str(row["variable"])): float(row["value"]) for row in observations}


def _deterministic_metrics(
    rows: Sequence[Mapping[str, object]], observations: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    selected = _selected_deterministic_rows(rows)
    truth = _truth_map(observations)
    grouped: dict[tuple[str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in selected:
        bucket = lead_bucket(float(row["lead_hours"]))
        grouped[(str(row["variable"]), bucket)][f"{row['provider']}|{row['valid_time_utc']}"] = row
    output: list[dict[str, object]] = []
    versions_by_provider = {
        str(row["provider"]): str(row["model_version"])
        for row in selected
        if str(row["provider"]) in DETERMINISTIC_PROVIDERS
    }
    for variable in EXPORT_VARIABLES:
        for _lower, _upper, bucket in LEAD_BUCKETS:
            bucket_rows = grouped.get((variable, bucket), {})
            if not bucket_rows:
                continue
            providers = list(DETERMINISTIC_PROVIDERS)
            times_by_provider = {
                provider: {
                    key.split("|", 1)[1]
                    for key in bucket_rows
                    if key.startswith(provider + "|")
                }
                for provider in providers
            }
            common_times = set.intersection(*(times_by_provider[provider] for provider in providers))
            common_times = {valid for valid in common_times if (valid, variable) in truth}
            provider_metrics: list[dict[str, object]] = []
            for provider in providers:
                pairs = []
                model_version = versions_by_provider.get(provider)
                for valid in sorted(common_times):
                    row = grouped[(variable, bucket)][f"{provider}|{valid}"]
                    model_version = str(row["model_version"])
                    pairs.append(
                        ErrorPair(
                            provider=provider,
                            model_version=model_version,
                            lead_hours=float(row["lead_hours"]),
                            forecast=float(row["value"]),
                            observed=truth[(valid, variable)],
                        )
                    )
                provider_metrics.append(
                    {
                        "provider": provider,
                        "model_version": model_version,
                        **summarize(pairs, expected_n=len(common_times)),
                    }
                )
            output.append(
                {
                    "variable": variable,
                    "lead_bucket": bucket,
                    "providers": providers,
                    "common_valid_times": sorted(common_times),
                    "n_common": len(common_times),
                    "metrics": provider_metrics,
                }
            )
    return output


def _ensemble_metrics(
    rows: Sequence[Mapping[str, object]], observations: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    truth = _truth_map(observations)
    latest = _latest_revision_rows(rows)
    grouped: dict[tuple[str, str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in latest:
        provider = str(row["provider"])
        if provider not in ENSEMBLE_PROVIDERS:
            continue
        key = (provider, str(row["model_version"]), str(row["init_time_utc"]), str(row["valid_time_utc"]), str(row["variable"]))
        grouped[key].append(row)
    buckets: dict[tuple[str, str, str], list[tuple[list[float], float]]] = defaultdict(list)
    for (provider, version, _init, valid, variable), member_rows in sorted(grouped.items()):
        if (valid, variable) not in truth:
            continue
        members = [float(row["value"]) for row in sorted(member_rows, key=lambda row: str(row["statistic"]))]
        lead_values = {float(row["lead_hours"]) for row in member_rows}
        if len(lead_values) != 1:
            raise BenchmarkExportError("ENSEMBLE_LEAD_MISMATCH", "ensemble members must share lead_hours")
        bucket = lead_bucket(next(iter(lead_values)))
        buckets[(provider, version, variable + "|" + bucket)].append((members, truth[(valid, variable)]))
    output: list[dict[str, object]] = []
    for (provider, version, variable_bucket), pairs in sorted(buckets.items()):
        variable, bucket = variable_bucket.split("|", 1)
        crps_values = [ensemble_crps(members, observed) for members, observed in pairs]
        row: dict[str, object] = {
            "provider": provider,
            "model_version": version,
            "variable": variable,
            "lead_bucket": bucket,
            **sample_evidence(len(pairs)),
            "mean_crps": mean(crps_values) if crps_values else None,
        }
        if variable == "temperature_2m":
            intervals = [interval_score(members, observed, alpha=TEMPERATURE_INTERVAL_ALPHA) for members, observed in pairs]
            row.update(
                {
                    "interval_alpha": TEMPERATURE_INTERVAL_ALPHA,
                    "coverage": mean(float(item["covered"]) for item in intervals) if intervals else None,
                    "mean_interval_width": mean(float(item["width"]) for item in intervals) if intervals else None,
                    "mean_wis": mean(weighted_interval_score(members, observed) for members, observed in pairs) if pairs else None,
                }
            )
        if variable == "precipitation_1h":
            brier = brier_from_members(
                [members for members, _observed in pairs],
                [observed for _members, observed in pairs],
                threshold=PRECIP_EVENT_THRESHOLD_MM,
            )
            row.update({"precipitation_event_threshold_mm": PRECIP_EVENT_THRESHOLD_MM, **brier})
        output.append(row)
    return output


def build_benchmark_export_files(
    *,
    source_sha: str,
    start: date,
    end: date,
    forecast_rows: Sequence[Mapping[str, object]],
    observation_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, bytes], dict[str, object]]:
    if not _SHA40_RE.fullmatch(source_sha):
        raise BenchmarkExportError("INVALID_SOURCE_SHA", "source_sha must be an exact 40-character lowercase commit SHA")
    start_iso, end_iso = _window(start, end)
    model_versions = _validate_rows(forecast_rows, observation_rows)
    forecasts = sorted((dict(row) for row in forecast_rows), key=_forecast_identity)
    observations = sorted((dict(row) for row in observation_rows), key=_observation_identity)
    metrics = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "contract": EXPORT_CONTRACT,
        "deterministic_common_sample": _deterministic_metrics(forecasts, observations),
        "ensemble": _ensemble_metrics(forecasts, observations),
    }
    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "contract": EXPORT_CONTRACT,
        "source_sha": source_sha,
        "corpus_schema": {
            "version": 1,
            "ddl_sha256": _sha256(SCHEMA_SQL.encode("utf-8")),
        },
        "common_window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "start_inclusive_utc": start_iso,
            "end_exclusive_utc": end_iso,
            "common_archive_start": COMMON_BENCHMARK_START.isoformat(),
            "location_id": DWD_10416.id,
            "truth_source": "DWD WMO 10416",
        },
        "providers": {
            "deterministic": list(DETERMINISTIC_PROVIDERS),
            "ensemble": list(ENSEMBLE_PROVIDERS),
            "model_versions": model_versions,
        },
        "verification_configuration": {
            "variables": list(EXPORT_VARIABLES),
            "lead_buckets": [label for _lower, _upper, label in LEAD_BUCKETS],
            "common_sample_policy": "intersection across present deterministic providers by variable/lead bucket; DWD truth required",
            "forecast_selection": "latest immutable revision, then smallest lead within provider/variable/lead-bucket/valid-time, latest retrieval tie-break",
            "sample_sufficiency_contract": "common-sample-sufficiency-v1",
            "deterministic_statistics": sorted(DETERMINISTIC_STATISTICS),
            "ensemble_member_prefix": "member_",
            "temperature_interval_alpha": TEMPERATURE_INTERVAL_ALPHA,
            "precipitation_event_threshold_mm": PRECIP_EVENT_THRESHOLD_MM,
        },
        "privacy": {
            "station_only": True,
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
            "raw_private_logs_exposed": False,
            "source_metadata_exported": False,
        },
        "files": ["forecasts.ndjson", "observations.ndjson", "metrics.json", "manifest.json", "checksums.json"],
    }
    files: dict[str, bytes] = {
        "forecasts.ndjson": _ndjson(forecasts),
        "observations.ndjson": _ndjson(observations),
        "metrics.json": _canonical_json(metrics),
        "manifest.json": _canonical_json(manifest),
    }
    checksums = {name: _sha256(data) for name, data in sorted(files.items())}
    files["checksums.json"] = _canonical_json(checksums)
    bundle_fingerprint = _sha256(files["checksums.json"])
    summary = {
        "state": "PASS",
        "contract": EXPORT_CONTRACT,
        "source_sha": source_sha,
        "forecast_rows": len(forecasts),
        "observation_rows": len(observations),
        "file_count": len(files),
        "bundle_fingerprint_sha256": bundle_fingerprint,
        "read_only_corpus": True,
        "privacy": manifest["privacy"],
    }
    return files, summary


def _readonly_connection(database: Database) -> sqlite3.Connection:
    if database.path == ":memory:":
        raise BenchmarkExportError("PERSISTENT_DB_REQUIRED", "benchmark export requires a persistent SQLite file")
    path = Path(database.path)
    if not path.is_file():
        raise BenchmarkExportError("DATABASE_NOT_FOUND", "corpus database does not exist")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def load_benchmark_rows(database: Database, *, start: date, end: date) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    start_iso, end_iso = _window(start, end)
    placeholders = ",".join("?" for _ in EXPORT_PROVIDERS)
    variables = ",".join("?" for _ in EXPORT_VARIABLES)
    with _readonly_connection(database) as connection:
        forecast_rows = [
            dict(row)
            for row in connection.execute(
                f"""SELECT r.provider,r.model_provider,r.model_name,r.model_version,r.location_id,
                           r.init_time_utc,r.retrieved_at_utc,r.upstream_available_at_utc,r.init_time_quality,
                           r.source_surface,r.transport_provider,r.raw_payload_hash,r.revision,
                           v.valid_time_utc,v.lead_hours,v.variable,v.statistic,v.value,v.unit,
                           v.accumulation_window_minutes,v.quality_status
                    FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id
                    WHERE r.location_id=? AND r.provider IN ({placeholders})
                      AND v.variable IN ({variables})
                      AND v.valid_time_utc>=? AND v.valid_time_utc<?
                    ORDER BY r.provider,r.model_version,r.init_time_utc,r.retrieved_at_utc,r.revision,
                             v.valid_time_utc,v.variable,v.statistic,v.accumulation_window_minutes""",
                (DWD_10416.id, *EXPORT_PROVIDERS, *EXPORT_VARIABLES, start_iso, end_iso),
            ).fetchall()
        ]
        observation_rows = [
            dict(row)
            for row in connection.execute(
                f"""SELECT source_provider,station_id,location_id,observed_at_utc,variable,value,unit,quality_status
                    FROM observations
                    WHERE source_provider='DWD' AND station_id='10416' AND location_id=?
                      AND variable IN ({variables})
                      AND observed_at_utc>=? AND observed_at_utc<?
                    ORDER BY observed_at_utc,variable""",
                (DWD_10416.id, *EXPORT_VARIABLES, start_iso, end_iso),
            ).fetchall()
        ]
    return forecast_rows, observation_rows


def write_benchmark_export_bundle(
    database: Database, *, source_sha: str, start: date, end: date, output_dir: Path
) -> dict[str, object]:
    if output_dir.exists():
        raise BenchmarkExportError("OUTPUT_EXISTS", "output directory must not already exist")
    forecast_rows, observation_rows = load_benchmark_rows(database, start=start, end=end)
    files, summary = build_benchmark_export_files(
        source_sha=source_sha,
        start=start,
        end=end,
        forecast_rows=forecast_rows,
        observation_rows=observation_rows,
    )
    output_dir.mkdir(parents=True)
    for name, content in sorted(files.items()):
        (output_dir / name).write_bytes(content)
    return summary


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m rozkalns_weather.benchmark_export")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--start", required=True, help="common-window start YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="common-window end YYYY-MM-DD")
    parser.add_argument("--output", required=True, help="new output directory for deterministic export files")
    args = parser.parse_args()
    settings = Settings.from_env()
    database = Database(settings.database_url)
    try:
        summary = write_benchmark_export_bundle(
            database,
            source_sha=args.source_sha,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            output_dir=Path(args.output),
        )
    except (BenchmarkExportError, ValueError) as exc:
        payload = {
            "state": "BLOCKED",
            "reason_code": getattr(exc, "reason_code", "INVALID_ARGUMENT"),
            "detail": str(exc),
            "production_data_authority_granted": False,
            "runtime_live_authority_granted": False,
        }
        print(json.dumps(payload, sort_keys=True, indent=2))
        raise SystemExit(3)
    print(json.dumps(summary, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
