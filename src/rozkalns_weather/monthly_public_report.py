from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

from .backfill import COMMON_BENCHMARK_START
from .benchmark_export import (
    BenchmarkExportError,
    DETERMINISTIC_PROVIDERS,
    ENSEMBLE_PROVIDERS,
    PRECIP_EVENT_THRESHOLD_MM,
    _latest_revision_rows,
    _readonly_connection,
    _selected_deterministic_rows,
    _truth_map,
    build_benchmark_export_files,
    load_benchmark_rows,
)
from .config import Settings
from .db import Database
from .locations import DWD_10416
from .probabilistic import reliability_from_members
from .verification import lead_bucket, sample_confidence

REPORT_CONTRACT = "public-monthly-benchmark-report-v1"
REPORT_SCHEMA_VERSION = 1
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_NOTABLE_PER_SLICE = 3


class MonthlyBenchmarkReportError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _month_bounds(month: str) -> tuple[date, date]:
    try:
        start = datetime.strptime(month + "-01", "%Y-%m-%d").date()
    except ValueError as exc:
        raise MonthlyBenchmarkReportError("INVALID_MONTH", "month must be YYYY-MM") from exc
    if start.month == 12:
        next_month = date(start.year + 1, 1, 1)
    else:
        next_month = date(start.year, start.month + 1, 1)
    return start, next_month - timedelta(days=1)


def _window_classification(month: str) -> dict[str, object]:
    requested_start, requested_end = _month_bounds(month)
    if requested_end < COMMON_BENCHMARK_START:
        return {
            "classification": "historical_ifs_only",
            "requested_start": requested_start.isoformat(),
            "requested_end": requested_end.isoformat(),
            "common_start": None,
            "common_end": None,
            "common_archive_start": COMMON_BENCHMARK_START.isoformat(),
        }
    common_start = max(requested_start, COMMON_BENCHMARK_START)
    return {
        "classification": "common_clipped" if common_start != requested_start else "common_full_month",
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "common_start": common_start.isoformat(),
        "common_end": requested_end.isoformat(),
        "common_archive_start": COMMON_BENCHMARK_START.isoformat(),
    }


def _assert_rows_inside_common_window(
    forecast_rows: Sequence[Mapping[str, object]],
    observation_rows: Sequence[Mapping[str, object]],
    *,
    start: date,
    end: date,
) -> None:
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)

    def parse_utc(value: object, field: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise MonthlyBenchmarkReportError(
                "INVALID_TIMESTAMP",
                f"{field} must be ISO-8601",
            ) from exc
        if parsed.tzinfo is None:
            raise MonthlyBenchmarkReportError(
                "INVALID_TIMESTAMP",
                f"{field} must be timezone-aware",
            )
        return parsed.astimezone(timezone.utc)

    for row in forecast_rows:
        valid = parse_utc(row.get("valid_time_utc"), "valid_time_utc")
        if not start_dt <= valid < end_dt:
            raise MonthlyBenchmarkReportError(
                "ROW_OUTSIDE_REPORT_WINDOW",
                "forecast row falls outside the requested common report window",
            )
    for row in observation_rows:
        observed = parse_utc(row.get("observed_at_utc"), "observed_at_utc")
        if not start_dt <= observed < end_dt:
            raise MonthlyBenchmarkReportError(
                "ROW_OUTSIDE_REPORT_WINDOW",
                "observation row falls outside the requested common report window",
            )


def _historical_context_default(window: Mapping[str, object]) -> dict[str, object]:
    requested_start = str(window["requested_start"])
    requested_end = str(window["requested_end"])
    if window["classification"] == "common_full_month":
        return {
            "provider": "ecmwf_ifs",
            "start": None,
            "end": None,
            "run_count": 0,
            "forecast_value_rows": 0,
            "included_in_common_metrics": False,
        }
    historical_end = min(
        date.fromisoformat(requested_end),
        COMMON_BENCHMARK_START - timedelta(days=1),
    )
    return {
        "provider": "ecmwf_ifs",
        "start": requested_start,
        "end": historical_end.isoformat(),
        "run_count": 0,
        "forecast_value_rows": 0,
        "included_in_common_metrics": False,
    }


def _precip_reliability(
    forecast_rows: Sequence[Mapping[str, object]],
    observation_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    truth = _truth_map(observation_rows)
    latest = _latest_revision_rows(forecast_rows)
    member_groups: dict[tuple[str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in latest:
        provider = str(row["provider"])
        if provider not in ENSEMBLE_PROVIDERS or str(row["variable"]) != "precipitation_1h":
            continue
        member_groups[
            (
                provider,
                str(row["model_version"]),
                str(row["init_time_utc"]),
                str(row["valid_time_utc"]),
            )
        ].append(row)

    buckets: dict[tuple[str, str, str], list[tuple[list[float], float]]] = defaultdict(list)
    for (provider, version, _init, valid), rows in sorted(member_groups.items()):
        truth_key = (valid, "precipitation_1h")
        if truth_key not in truth:
            continue
        leads = {float(row["lead_hours"]) for row in rows}
        if len(leads) != 1:
            raise MonthlyBenchmarkReportError(
                "ENSEMBLE_LEAD_MISMATCH",
                "precipitation ensemble members must share one lead_hours value",
            )
        members = [float(row["value"]) for row in sorted(rows, key=lambda item: str(item["statistic"]))]
        buckets[(provider, version, lead_bucket(next(iter(leads))))].append(
            (members, truth[truth_key])
        )

    output: list[dict[str, object]] = []
    for (provider, version, bucket), pairs in sorted(buckets.items()):
        output.append(
            {
                "provider": provider,
                "model_version": version,
                "variable": "precipitation_1h",
                "lead_bucket": bucket,
                "n": len(pairs),
                "sample_sufficiency_state": sample_confidence(len(pairs)),
                "threshold_mm": PRECIP_EVENT_THRESHOLD_MM,
                "bins": reliability_from_members(
                    [members for members, _observed in pairs],
                    [observed for _members, observed in pairs],
                    threshold=PRECIP_EVENT_THRESHOLD_MM,
                ),
            }
        )
    return output


def _notable_cases(
    forecast_rows: Sequence[Mapping[str, object]],
    observation_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    selected = _selected_deterministic_rows(forecast_rows)
    truth = _truth_map(observation_rows)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in selected:
        grouped[(str(row["variable"]), lead_bucket(float(row["lead_hours"])))].append(row)

    candidates: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for (variable, bucket), rows in sorted(grouped.items()):
        times_by_provider = {
            provider: {
                str(row["valid_time_utc"])
                for row in rows
                if str(row["provider"]) == provider
            }
            for provider in DETERMINISTIC_PROVIDERS
        }
        common_times = set.intersection(
            *(times_by_provider[provider] for provider in DETERMINISTIC_PROVIDERS)
        )
        common_times = {
            valid for valid in common_times if (valid, variable) in truth
        }
        for row in rows:
            valid = str(row["valid_time_utc"])
            if valid not in common_times:
                continue
            provider = str(row["provider"])
            version = str(row["model_version"])
            observed = truth[(valid, variable)]
            forecast = float(row["value"])
            candidates[(provider, version, variable, bucket)].append(
                {
                    "provider": provider,
                    "model_version": version,
                    "variable": variable,
                    "lead_bucket": bucket,
                    "valid_time_utc": valid,
                    "forecast": forecast,
                    "observed": observed,
                    "signed_error": forecast - observed,
                    "absolute_error": abs(forecast - observed),
                }
            )

    output: list[dict[str, object]] = []
    for _key, items in sorted(candidates.items()):
        ranked = sorted(
            items,
            key=lambda item: (
                -float(item["absolute_error"]),
                str(item["valid_time_utc"]),
            ),
        )
        output.extend(ranked[:_NOTABLE_PER_SLICE])
    return output


def _sample_summary(deterministic: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts = {
        "insufficient_sample": 0,
        "limited_sample": 0,
        "usable_sample": 0,
    }
    for section in deterministic:
        for metric in section.get("metrics", []):
            state = str(metric.get("sample_sufficiency_state", "insufficient_sample"))
            if state in counts:
                counts[state] += 1
    return counts


def _blocked_report(
    *,
    source_sha: str,
    month: str,
    window: Mapping[str, object],
    historical_ifs_only: Mapping[str, object],
    reason_code: str,
    detail: str,
) -> dict[str, object]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "contract": REPORT_CONTRACT,
        "state": "BLOCKED",
        "reason_code": reason_code,
        "detail": detail,
        "source_sha": source_sha,
        "month": month,
        "window": dict(window),
        "truth_source": "DWD WMO 10416",
        "comparison_location": {"id": DWD_10416.id, "station_id": "10416"},
        "deterministic_common_sample": [],
        "ensemble": [],
        "precipitation_reliability": [],
        "notable_cases": [],
        "notable_case_selection": (
            "up to 3 largest absolute errors per provider/model-version/variable/lead-bucket "
            "on the exact common matched sample; deterministic tie-break by valid_time_utc"
        ),
        "historical_ifs_only": dict(historical_ifs_only),
        "weathernext": {
            "state": "pending",
            "reason_code": "DEFENSIBLE_REAL_CORPUS_REQUIRED",
            "fabricated_values": False,
            "included_in_public_metrics": False,
        },
        "privacy": {
            "station_only": True,
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
            "raw_private_logs_exposed": False,
        },
    }


def build_monthly_public_report(
    *,
    source_sha: str,
    month: str,
    forecast_rows: Sequence[Mapping[str, object]],
    observation_rows: Sequence[Mapping[str, object]],
    historical_ifs_only: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if not _SHA40_RE.fullmatch(source_sha):
        raise MonthlyBenchmarkReportError(
            "INVALID_SOURCE_SHA",
            "source_sha must be an exact 40-character lowercase commit SHA",
        )
    window = _window_classification(month)
    historical = dict(historical_ifs_only or _historical_context_default(window))

    if window["classification"] == "historical_ifs_only":
        return {
            **_blocked_report(
                source_sha=source_sha,
                month=month,
                window=window,
                historical_ifs_only=historical,
                reason_code="HISTORICAL_IFS_ONLY",
                detail="requested month predates the 2026-04-02 common public benchmark window",
            ),
            "state": "WARN",
        }

    common_start = date.fromisoformat(str(window["common_start"]))
    common_end = date.fromisoformat(str(window["common_end"]))
    try:
        _assert_rows_inside_common_window(
            forecast_rows,
            observation_rows,
            start=common_start,
            end=common_end,
        )
        export_files, export_summary = build_benchmark_export_files(
            source_sha=source_sha,
            start=common_start,
            end=common_end,
            forecast_rows=forecast_rows,
            observation_rows=observation_rows,
        )
        metrics = json.loads(export_files["metrics.json"].decode("utf-8"))
        manifest = json.loads(export_files["manifest.json"].decode("utf-8"))
        reliability = _precip_reliability(forecast_rows, observation_rows)
        notable = _notable_cases(forecast_rows, observation_rows)
    except (BenchmarkExportError, MonthlyBenchmarkReportError, ValueError) as exc:
        return _blocked_report(
            source_sha=source_sha,
            month=month,
            window=window,
            historical_ifs_only=historical,
            reason_code=getattr(exc, "reason_code", "INVALID_REPORT_INPUT"),
            detail=str(exc),
        )

    deterministic = list(metrics["deterministic_common_sample"])
    ensemble = list(metrics["ensemble"])
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "contract": REPORT_CONTRACT,
        "state": "PASS",
        "reason_code": "OK",
        "source_sha": source_sha,
        "month": month,
        "window": window,
        "truth_source": "DWD WMO 10416",
        "comparison_location": {"id": DWD_10416.id, "station_id": "10416"},
        "verification_configuration": manifest["verification_configuration"],
        "model_versions": manifest["providers"]["model_versions"],
        "sample_state_summary": _sample_summary(deterministic),
        "deterministic_common_sample": deterministic,
        "ensemble": ensemble,
        "precipitation_reliability": reliability,
        "notable_cases": notable,
        "notable_case_selection": (
            "up to 3 largest absolute errors per provider/model-version/variable/lead-bucket "
            "on the exact common matched sample; deterministic tie-break by valid_time_utc"
        ),
        "historical_ifs_only": historical,
        "weathernext": {
            "state": "pending",
            "reason_code": "DEFENSIBLE_REAL_CORPUS_REQUIRED",
            "fabricated_values": False,
            "included_in_public_metrics": False,
        },
        "reproducibility": {
            "benchmark_export_contract": export_summary["contract"],
            "benchmark_export_fingerprint_sha256": export_summary[
                "bundle_fingerprint_sha256"
            ],
            "read_only_corpus": export_summary["read_only_corpus"],
        },
        "privacy": export_summary["privacy"],
    }


def render_monthly_public_report_markdown(report: Mapping[str, object]) -> str:
    lines = [
        f"# Public monthly benchmark — {report['month']}",
        "",
        f"- State: `{report['state']}`",
        f"- Source SHA: `{report['source_sha']}`",
        f"- Truth: {report['truth_source']}",
        f"- Window: `{report['window']['classification']}`",
        "- WeatherNext 3: `pending` until defensible real corpus exists; no values are fabricated.",
        "",
    ]
    if report["state"] == "BLOCKED":
        lines.extend(
            [
                "## Blocker",
                "",
                f"- `{report['reason_code']}` — {report.get('detail', '')}",
                "",
            ]
        )
    elif report["state"] == "WARN":
        lines.extend(
            [
                "## Historical context only",
                "",
                "This month predates the common 2026-04-02+ comparison window. "
                "IFS-only history is kept separate and is not presented as a common benchmark.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Deterministic common-sample metrics",
                "",
                "| Variable | Lead | Provider | Model version | n | Confidence | MAE | RMSE | Bias |",
                "|---|---|---|---|---:|---|---:|---:|---:|",
            ]
        )
        for section in report["deterministic_common_sample"]:
            for metric in section["metrics"]:
                def fmt(value: object) -> str:
                    return "—" if value is None else f"{float(value):.4f}"
                lines.append(
                    "| {variable} | {lead} | {provider} | {version} | {n} | {confidence} | {mae} | {rmse} | {bias} |".format(
                        variable=section["variable"],
                        lead=section["lead_bucket"],
                        provider=metric["provider"],
                        version=metric["model_version"],
                        n=metric["n"],
                        confidence=metric["sample_sufficiency_state"],
                        mae=fmt(metric["mae"]),
                        rmse=fmt(metric["rmse"]),
                        bias=fmt(metric["bias"]),
                    )
                )
        lines.extend(["", "## Ensemble metrics", ""])
        if not report["ensemble"]:
            lines.append("No genuine ensemble member groups are available for this month.")
        else:
            lines.extend(
                [
                    "| Variable | Lead | Provider | Model version | n | Confidence | CRPS | Coverage | Width | WIS | Brier |",
                    "|---|---|---|---|---:|---|---:|---:|---:|---:|---:|",
                ]
            )
            for row in report["ensemble"]:
                def fmt(value: object) -> str:
                    return "—" if value is None else f"{float(value):.4f}"
                lines.append(
                    "| {variable} | {lead} | {provider} | {version} | {n} | {confidence} | {crps} | {coverage} | {width} | {wis} | {brier} |".format(
                        variable=row["variable"],
                        lead=row["lead_bucket"],
                        provider=row["provider"],
                        version=row["model_version"],
                        n=row["n"],
                        confidence=row["sample_sufficiency_state"],
                        crps=fmt(row.get("mean_crps")),
                        coverage=fmt(row.get("coverage")),
                        width=fmt(row.get("mean_interval_width")),
                        wis=fmt(row.get("mean_wis")),
                        brier=fmt(row.get("brier_score")),
                    )
                )
        lines.extend(["", "## Notable cases", ""])
        if not report["notable_cases"]:
            lines.append("No common-sample notable cases are available.")
        else:
            lines.append(
                "Selection is deterministic and symmetric: up to three largest absolute errors "
                "per provider/model-version/variable/lead bucket from the exact common matched sample."
            )
            lines.append("")
            lines.append("| Provider | Model version | Variable | Lead | Valid time | Abs. error | Signed error |")
            lines.append("|---|---|---|---|---|---:|---:|")
            for case in report["notable_cases"]:
                lines.append(
                    "| {provider} | {version} | {variable} | {lead} | {valid} | {absolute:.4f} | {signed:.4f} |".format(
                        provider=case["provider"],
                        version=case["model_version"],
                        variable=case["variable"],
                        lead=case["lead_bucket"],
                        valid=case["valid_time_utc"],
                        absolute=float(case["absolute_error"]),
                        signed=float(case["signed_error"]),
                    )
                )

    historical = report["historical_ifs_only"]
    lines.extend(["", "## Older IFS-only context", ""])
    if historical.get("start") is None:
        lines.append("No pre-common-window days fall inside this month.")
    else:
        lines.append(
            f"`{historical['start']}` through `{historical['end']}` remains IFS-only historical context "
            f"({historical.get('run_count', 0)} runs / {historical.get('forecast_value_rows', 0)} values) "
            "and is excluded from common metrics."
        )
    lines.append("")
    return "\n".join(lines)


def build_monthly_public_report_files(report: Mapping[str, object]) -> dict[str, bytes]:
    report_json = _canonical_json(dict(report))
    report_md = render_monthly_public_report_markdown(report).encode("utf-8")
    files = {
        "report.json": report_json,
        "report.md": report_md,
    }
    checksums = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in sorted(files.items())
    }
    files["checksums.json"] = _canonical_json(checksums)
    return files


def _load_historical_ifs_context(
    database: Database,
    *,
    month: str,
) -> dict[str, object]:
    window = _window_classification(month)
    default = _historical_context_default(window)
    if default["start"] is None:
        return default
    start = datetime.combine(
        date.fromisoformat(str(default["start"])),
        time.min,
        tzinfo=timezone.utc,
    ).isoformat().replace("+00:00", "Z")
    end_exclusive = datetime.combine(
        date.fromisoformat(str(default["end"])) + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    ).isoformat().replace("+00:00", "Z")
    with _readonly_connection(database) as connection:
        row = connection.execute(
            """SELECT COUNT(DISTINCT r.id) AS run_count, COUNT(v.id) AS forecast_value_rows
               FROM forecast_runs r
               JOIN forecast_values v ON v.run_id=r.id
               WHERE r.location_id=? AND r.provider='ecmwf_ifs'
                 AND v.valid_time_utc>=? AND v.valid_time_utc<?""",
            (DWD_10416.id, start, end_exclusive),
        ).fetchone()
    return {
        **default,
        "run_count": int(row["run_count"]),
        "forecast_value_rows": int(row["forecast_value_rows"]),
    }


def load_monthly_public_report(
    database: Database,
    *,
    source_sha: str,
    month: str,
) -> dict[str, object]:
    window = _window_classification(month)
    historical = _load_historical_ifs_context(database, month=month)
    if window["classification"] == "historical_ifs_only":
        return build_monthly_public_report(
            source_sha=source_sha,
            month=month,
            forecast_rows=[],
            observation_rows=[],
            historical_ifs_only=historical,
        )
    start = date.fromisoformat(str(window["common_start"]))
    end = date.fromisoformat(str(window["common_end"]))
    forecasts, observations = load_benchmark_rows(database, start=start, end=end)
    return build_monthly_public_report(
        source_sha=source_sha,
        month=month,
        forecast_rows=forecasts,
        observation_rows=observations,
        historical_ifs_only=historical,
    )


def write_monthly_public_report(
    database: Database,
    *,
    source_sha: str,
    month: str,
    output_dir: Path,
) -> dict[str, object]:
    if output_dir.exists():
        raise MonthlyBenchmarkReportError(
            "OUTPUT_EXISTS",
            "output directory must not already exist",
        )
    report = load_monthly_public_report(database, source_sha=source_sha, month=month)
    files = build_monthly_public_report_files(report)
    output_dir.mkdir(parents=True)
    for name, content in sorted(files.items()):
        (output_dir / name).write_bytes(content)
    return {
        "state": report["state"],
        "contract": REPORT_CONTRACT,
        "source_sha": source_sha,
        "month": month,
        "file_count": len(files),
        "report_sha256": hashlib.sha256(files["report.json"]).hexdigest(),
        "read_only_corpus": True,
        "privacy": report["privacy"],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m rozkalns_weather.monthly_public_report"
    )
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--output", required=True, help="new output directory")
    args = parser.parse_args()

    settings = Settings.from_env()
    database = Database(settings.database_url)
    try:
        summary = write_monthly_public_report(
            database,
            source_sha=args.source_sha,
            month=args.month,
            output_dir=Path(args.output),
        )
    except (MonthlyBenchmarkReportError, BenchmarkExportError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "state": "BLOCKED",
                    "reason_code": getattr(
                        exc, "reason_code", "INVALID_REPORT_ARGUMENT"
                    ),
                    "detail": str(exc),
                    "runtime_live_authority_granted": False,
                    "production_data_authority_granted": False,
                },
                sort_keys=True,
                indent=2,
            )
        )
        raise SystemExit(3)
    print(json.dumps(summary, sort_keys=True, indent=2))
    if summary["state"] == "BLOCKED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
