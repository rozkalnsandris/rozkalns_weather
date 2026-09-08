from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import sqrt
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from .locations import DWD_10416
from .verification import lead_bucket, sample_confidence

REPORT_TYPE = "weathernext3_version_evolution_v1"
PROVIDER = "weathernext3"
MIN_MEANINGFUL_N = 30
MAX_WINDOW_DAYS = 92
ALLOWED_RUN_CLASSES = {"interim_48h", "synoptic_360h"}
QUANTILES = ("p10", "p25", "p50", "p75", "p90")
FORBIDDEN_EVIDENCE_KEYS = {
    "home_lat",
    "home_lon",
    "latitude",
    "longitude",
    "google_cloud_project",
    "bigquery_dataset",
    "credentials",
    "credential",
    "token",
    "access_token",
    "sql",
    "database_path",
    "host_path",
    "raw_payload",
    "raw_log",
    "environment",
}
FORBIDDEN_PATH_FRAGMENTS = ("/home/", "/root/", "/opt/")

EVENT_RULES: dict[str, tuple[tuple[str, float, str], ...]] = {
    "temperature_2m": (
        ("temperature_high_30c", 30.0, "at_or_above"),
        ("temperature_freeze_0c", 0.0, "at_or_below"),
    ),
    "precipitation_1h": (("precipitation_0p1mm_h", 0.1, "at_or_above"),),
    "wind_gust_10m": (("wind_gust_15ms", 15.0, "at_or_above"),),
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _fingerprint(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("schema fingerprint must be a 64-character sha256 hex string")
    return normalized


@dataclass(frozen=True, slots=True)
class VersionBoundary:
    before_model_version: str
    after_model_version: str
    before_schema_fingerprint: str
    after_schema_fingerprint: str
    effective_at_utc: datetime
    release_source_url: str
    release_metadata_verified: bool
    provider: str = PROVIDER

    def __post_init__(self) -> None:
        if self.provider != PROVIDER:
            raise ValueError("only WeatherNext 3 boundaries are supported")
        before = self.before_model_version.strip()
        after = self.after_model_version.strip()
        if not before or not after or before == after:
            raise ValueError("before/after model versions must be distinct and non-empty")
        if not before.startswith("3.") or not after.startswith("3."):
            raise ValueError("unknown/non-WeatherNext-3 product fails closed")
        object.__setattr__(self, "before_model_version", before)
        object.__setattr__(self, "after_model_version", after)
        object.__setattr__(self, "before_schema_fingerprint", _fingerprint(self.before_schema_fingerprint))
        object.__setattr__(self, "after_schema_fingerprint", _fingerprint(self.after_schema_fingerprint))
        object.__setattr__(self, "effective_at_utc", _utc(self.effective_at_utc))
        if not self.release_source_url.startswith("https://"):
            raise ValueError("release source must be https")
        if not self.release_metadata_verified:
            raise ValueError("version boundary requires verified release metadata")

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "before_model_version": self.before_model_version,
            "after_model_version": self.after_model_version,
            "before_schema_fingerprint": self.before_schema_fingerprint,
            "after_schema_fingerprint": self.after_schema_fingerprint,
            "effective_at_utc": _iso(self.effective_at_utc),
            "release_source_url": self.release_source_url,
            "release_metadata_verified": self.release_metadata_verified,
        }


@dataclass(frozen=True, slots=True)
class ComparisonWindows:
    before_start_utc: datetime
    before_end_utc: datetime
    after_start_utc: datetime
    after_end_utc: datetime
    requested_days_per_side: int
    before_days: float
    after_days: float
    comparable_duration: bool
    limitation: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "before": {"start_utc": _iso(self.before_start_utc), "end_utc": _iso(self.before_end_utc)},
            "after": {"start_utc": _iso(self.after_start_utc), "end_utc": _iso(self.after_end_utc)},
            "requested_days_per_side": self.requested_days_per_side,
            "before_days": self.before_days,
            "after_days": self.after_days,
            "comparable_duration": self.comparable_duration,
            "selection": "symmetric_calendar_windows_around_effective_boundary",
            "performance_based_selection": False,
            "seasonality_limitation": "before/after calendar periods are different; interpret changes with seasonal context",
            "limitation": self.limitation,
        }


def plan_comparison_windows(
    boundary: VersionBoundary,
    *,
    days_per_side: int = 30,
    corpus_start_utc: datetime | None = None,
    corpus_end_utc: datetime | None = None,
) -> ComparisonWindows:
    if not 1 <= days_per_side <= MAX_WINDOW_DAYS:
        raise ValueError(f"days_per_side must be between 1 and {MAX_WINDOW_DAYS}")
    effective = boundary.effective_at_utc
    before_start = effective - timedelta(days=days_per_side)
    before_end = effective
    after_start = effective
    after_end = effective + timedelta(days=days_per_side)
    limitations: list[str] = []
    if corpus_start_utc is not None:
        corpus_start = _utc(corpus_start_utc)
        if corpus_start > before_start:
            before_start = min(corpus_start, before_end)
            limitations.append("before_window_clipped_by_corpus_start")
    if corpus_end_utc is not None:
        corpus_end = _utc(corpus_end_utc)
        if corpus_end < after_end:
            after_end = max(corpus_end, after_start)
            limitations.append("after_window_clipped_by_corpus_end")
    before_days = max(0.0, (before_end - before_start).total_seconds() / 86400.0)
    after_days = max(0.0, (after_end - after_start).total_seconds() / 86400.0)
    comparable = before_days > 0 and after_days > 0 and abs(before_days - after_days) < 1e-9
    if not comparable:
        limitations.append("unequal_or_empty_windows")
    return ComparisonWindows(
        before_start,
        before_end,
        after_start,
        after_end,
        days_per_side,
        before_days,
        after_days,
        comparable,
        ";".join(limitations) if limitations else None,
    )


@dataclass(frozen=True, slots=True)
class EvolutionSample:
    model_version: str
    valid_time_utc: datetime
    variable: str
    lead_hours: float
    run_class: str
    forecast: float
    observed: float
    statistic: str = "mean"
    unit: str = "degC"
    accumulation_window_minutes: int | None = None
    location_id: str = DWD_10416.id

    def __post_init__(self) -> None:
        object.__setattr__(self, "valid_time_utc", _utc(self.valid_time_utc))
        if self.location_id != DWD_10416.id:
            raise ValueError("measured version evolution is station_10416 only")
        if self.run_class not in ALLOWED_RUN_CLASSES:
            raise ValueError("unknown WeatherNext run class")
        if self.lead_hours < 0:
            raise ValueError("lead_hours must be >= 0")
        if self.variable == "precipitation_1h" and self.accumulation_window_minutes != 60:
            raise ValueError("WeatherNext precipitation_1h requires 60-minute accumulation semantics")

    @property
    def semantic_key(self) -> tuple[str, str, str, str, str, str, int | None]:
        return (
            _iso(self.valid_time_utc),
            self.variable,
            lead_bucket(self.lead_hours),
            self.run_class,
            self.statistic,
            self.unit,
            self.accumulation_window_minutes,
        )


@dataclass(frozen=True, slots=True)
class CommonSamplePair:
    before: EvolutionSample
    after: EvolutionSample

    def __post_init__(self) -> None:
        if self.before.semantic_key != self.after.semantic_key:
            raise ValueError("cross-version pair semantics must match exactly")


def common_version_samples(
    samples: Iterable[EvolutionSample],
    *,
    before_version: str,
    after_version: str,
) -> dict[str, object]:
    before_rows = [row for row in samples if row.model_version == before_version]
    after_rows = [row for row in samples if row.model_version == after_version]
    before_map = {row.semantic_key: row for row in before_rows}
    after_map = {row.semantic_key: row for row in after_rows}
    common_keys = sorted(set(before_map) & set(after_map))
    pairs = tuple(CommonSamplePair(before_map[key], after_map[key]) for key in common_keys)
    return {
        "before_n": len(before_map),
        "after_n": len(after_map),
        "common_n": len(pairs),
        "pairs": pairs,
        "location_id": DWD_10416.id,
        "private_home_excluded": True,
    }


def _metrics(samples: Sequence[EvolutionSample]) -> dict[str, float | int | str | None]:
    if not samples:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "sample_confidence": sample_confidence(0)}
    errors = [item.forecast - item.observed for item in samples]
    return {
        "n": len(samples),
        "mae": mean(abs(error) for error in errors),
        "rmse": sqrt(mean(error * error for error in errors)),
        "bias": mean(errors),
        "sample_confidence": sample_confidence(len(samples)),
    }


def _delta(after: float | None, before: float | None) -> tuple[float | None, float | None]:
    if after is None or before is None:
        return None, None
    absolute = after - before
    relative = None if before == 0 else absolute / abs(before)
    return absolute, relative


def skill_delta_summary(pairs: Sequence[CommonSamplePair]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[CommonSamplePair]] = defaultdict(list)
    for pair in pairs:
        key = (pair.before.variable, lead_bucket(pair.before.lead_hours), pair.before.run_class)
        grouped[key].append(pair)
    result: list[dict[str, object]] = []
    for (variable, bucket, run_class), items in sorted(grouped.items()):
        before = _metrics([item.before for item in items])
        after = _metrics([item.after for item in items])
        deltas: dict[str, dict[str, float | None]] = {}
        for metric in ("mae", "rmse", "bias"):
            absolute, relative = _delta(
                float(after[metric]) if after[metric] is not None else None,
                float(before[metric]) if before[metric] is not None else None,
            )
            deltas[metric] = {"absolute": absolute, "relative": relative}
        result.append(
            {
                "variable": variable,
                "lead_bucket": bucket,
                "run_class": run_class,
                "common_n": len(items),
                "before": before,
                "after": after,
                "delta_after_minus_before": deltas,
                "uncertainty_eligible": len(items) >= MIN_MEANINGFUL_N,
                "global_winner_label": None,
            }
        )
    return result


@dataclass(frozen=True, slots=True)
class QuantileEvolutionSample:
    model_version: str
    valid_time_utc: datetime
    variable: str
    lead_hours: float
    run_class: str
    observed: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    location_id: str = DWD_10416.id
    accumulation_window_minutes: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "valid_time_utc", _utc(self.valid_time_utc))
        if self.location_id != DWD_10416.id:
            raise ValueError("quantile evolution is station_10416 only")
        if self.run_class not in ALLOWED_RUN_CLASSES:
            raise ValueError("unknown WeatherNext run class")
        if not self.p10 <= self.p25 <= self.p50 <= self.p75 <= self.p90:
            raise ValueError("WeatherNext quantiles must be monotonic")
        if self.variable == "precipitation_1h" and self.accumulation_window_minutes != 60:
            raise ValueError("WeatherNext precipitation_1h requires 60-minute accumulation semantics")

    @property
    def semantic_key(self) -> tuple[str, str, str, str, int | None]:
        return (
            _iso(self.valid_time_utc),
            self.variable,
            lead_bucket(self.lead_hours),
            self.run_class,
            self.accumulation_window_minutes,
        )


def _quantile_metrics(rows: Sequence[QuantileEvolutionSample]) -> dict[str, float | int | str | None]:
    if not rows:
        return {
            "n": 0,
            "p10_p90_coverage": None,
            "p10_p90_mean_width": None,
            "p25_p75_coverage": None,
            "p25_p75_mean_width": None,
            "p50_mae": None,
            "sample_confidence": sample_confidence(0),
        }
    return {
        "n": len(rows),
        "p10_p90_coverage": mean(1.0 if row.p10 <= row.observed <= row.p90 else 0.0 for row in rows),
        "p10_p90_mean_width": mean(row.p90 - row.p10 for row in rows),
        "p25_p75_coverage": mean(1.0 if row.p25 <= row.observed <= row.p75 else 0.0 for row in rows),
        "p25_p75_mean_width": mean(row.p75 - row.p25 for row in rows),
        "p50_mae": mean(abs(row.p50 - row.observed) for row in rows),
        "sample_confidence": sample_confidence(len(rows)),
    }


def quantile_calibration_delta(
    samples: Iterable[QuantileEvolutionSample],
    *,
    before_version: str,
    after_version: str,
) -> list[dict[str, object]]:
    before_map = {row.semantic_key: row for row in samples if row.model_version == before_version}
    rows = list(samples) if not isinstance(samples, list) else samples
    before_map = {row.semantic_key: row for row in rows if row.model_version == before_version}
    after_map = {row.semantic_key: row for row in rows if row.model_version == after_version}
    common = sorted(set(before_map) & set(after_map))
    grouped: dict[tuple[str, str, str], list[tuple[QuantileEvolutionSample, QuantileEvolutionSample]]] = defaultdict(list)
    for key in common:
        before = before_map[key]
        after = after_map[key]
        grouped[(before.variable, lead_bucket(before.lead_hours), before.run_class)].append((before, after))
    result: list[dict[str, object]] = []
    metric_names = (
        "p10_p90_coverage",
        "p10_p90_mean_width",
        "p25_p75_coverage",
        "p25_p75_mean_width",
        "p50_mae",
    )
    for (variable, bucket, run_class), items in sorted(grouped.items()):
        before = _quantile_metrics([item[0] for item in items])
        after = _quantile_metrics([item[1] for item in items])
        deltas = {
            metric: _delta(
                float(after[metric]) if after[metric] is not None else None,
                float(before[metric]) if before[metric] is not None else None,
            )[0]
            for metric in metric_names
        }
        result.append(
            {
                "variable": variable,
                "lead_bucket": bucket,
                "run_class": run_class,
                "common_n": len(items),
                "before": before,
                "after": after,
                "delta_after_minus_before": deltas,
                "synthetic_crps": None,
                "synthetic_brier": None,
                "synthetic_precipitation_probability": None,
            }
        )
    return result


def _event(value: float, threshold: float, direction: str) -> bool:
    if direction == "at_or_above":
        return value >= threshold
    if direction == "at_or_below":
        return value <= threshold
    raise ValueError("unknown event direction")


def event_evolution_summary(pairs: Sequence[CommonSamplePair]) -> dict[str, object]:
    counters: dict[str, dict[str, int]] = {}
    cases: list[dict[str, object]] = []
    for pair in pairs:
        for event_id, threshold, direction in EVENT_RULES.get(pair.before.variable, ()):
            observed_event = _event(pair.before.observed, threshold, direction)
            before_correct = _event(pair.before.forecast, threshold, direction) == observed_event
            after_correct = _event(pair.after.forecast, threshold, direction) == observed_event
            counter = counters.setdefault(event_id, {"n": 0, "improved": 0, "regressed": 0, "unchanged": 0})
            counter["n"] += 1
            if after_correct and not before_correct:
                change = "improved"
            elif before_correct and not after_correct:
                change = "regressed"
            else:
                change = "unchanged"
            counter[change] += 1
            cases.append(
                {
                    "event_id": event_id,
                    "valid_time_utc": _iso(pair.before.valid_time_utc),
                    "variable": pair.before.variable,
                    "lead_bucket": lead_bucket(pair.before.lead_hours),
                    "run_class": pair.before.run_class,
                    "change": change,
                }
            )
    return {
        "summaries": [{"event_id": key, **value} for key, value in sorted(counters.items())],
        "cases": sorted(cases, key=lambda item: (str(item["event_id"]), str(item["valid_time_utc"]), str(item["lead_bucket"]))),
    }


def notable_error_delta_cases(pairs: Sequence[CommonSamplePair], *, limit: int = 10) -> list[dict[str, object]]:
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    cases: list[dict[str, object]] = []
    for pair in pairs:
        before_error = abs(pair.before.forecast - pair.before.observed)
        after_error = abs(pair.after.forecast - pair.after.observed)
        delta = after_error - before_error
        cases.append(
            {
                "valid_time_utc": _iso(pair.before.valid_time_utc),
                "variable": pair.before.variable,
                "lead_bucket": lead_bucket(pair.before.lead_hours),
                "run_class": pair.before.run_class,
                "before_abs_error": before_error,
                "after_abs_error": after_error,
                "abs_error_delta_after_minus_before": delta,
                "classification": "regression" if delta > 0 else "improvement" if delta < 0 else "unchanged",
            }
        )
    return sorted(
        cases,
        key=lambda item: (
            -abs(float(item["abs_error_delta_after_minus_before"])),
            str(item["valid_time_utc"]),
            str(item["variable"]),
            str(item["lead_bucket"]),
        ),
    )[:limit]


@dataclass(frozen=True, slots=True)
class FreshnessSample:
    model_version: str
    init_time_utc: datetime
    expected_available_at_utc: datetime
    retrieved_at_utc: datetime | None
    upstream_available_at_utc: datetime | None = None
    state: str = "retrieved"

    def __post_init__(self) -> None:
        object.__setattr__(self, "init_time_utc", _utc(self.init_time_utc))
        object.__setattr__(self, "expected_available_at_utc", _utc(self.expected_available_at_utc))
        if self.retrieved_at_utc is not None:
            object.__setattr__(self, "retrieved_at_utc", _utc(self.retrieved_at_utc))
        if self.upstream_available_at_utc is not None:
            object.__setattr__(self, "upstream_available_at_utc", _utc(self.upstream_available_at_utc))
        if self.state not in {"retrieved", "delayed", "missing"}:
            raise ValueError("freshness state must be retrieved, delayed or missing")


def _freshness_version(rows: Sequence[FreshnessSample]) -> dict[str, object]:
    retrieval_lags = [
        (row.retrieved_at_utc - row.expected_available_at_utc).total_seconds() / 60.0
        for row in rows
        if row.retrieved_at_utc is not None
    ]
    observed_lags = [
        (row.upstream_available_at_utc - row.expected_available_at_utc).total_seconds() / 60.0
        for row in rows
        if row.upstream_available_at_utc is not None
    ]
    return {
        "n_expected": len(rows),
        "n_retrieved": sum(row.retrieved_at_utc is not None for row in rows),
        "missing_runs": sum(row.state == "missing" for row in rows),
        "delayed_runs": sum(row.state == "delayed" for row in rows),
        "mean_retrieval_lag_from_expected_minutes": mean(retrieval_lags) if retrieval_lags else None,
        "mean_observed_upstream_lag_from_expected_minutes": mean(observed_lags) if observed_lags else None,
        "expected_observed_retrieved_timestamps_kept_distinct": True,
    }


def freshness_evolution(
    samples: Iterable[FreshnessSample],
    *,
    before_version: str,
    after_version: str,
) -> dict[str, object]:
    rows = list(samples)
    return {
        "before": _freshness_version([row for row in rows if row.model_version == before_version]),
        "after": _freshness_version([row for row in rows if row.model_version == after_version]),
        "private_provider_identity_exposed": False,
    }


def _find_private_key(value: object, *, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_EVIDENCE_KEYS:
                return child_path
            found = _find_private_key(child, path=child_path)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_private_key(child, path=f"{path}[{index}]")
            if found:
                return found
    elif isinstance(value, str):
        if any(fragment in value for fragment in FORBIDDEN_PATH_FRAGMENTS):
            return path or "value"
    return None


def validate_release_provenance(value: Mapping[str, Any]) -> dict[str, object]:
    source_url = str(value.get("source_url") or "")
    effective_at = str(value.get("effective_at_utc") or "")
    if value.get("verified") is not True:
        raise ValueError("release provenance must be verified")
    if not source_url.startswith("https://"):
        raise ValueError("release provenance source_url must be https")
    if not effective_at.endswith("Z"):
        raise ValueError("release provenance effective_at_utc must be explicit UTC")
    if value.get("locally_first_observed_at_utc") == effective_at:
        raise ValueError("provider effective time must not be inferred from local first observation")
    return {
        "source_url": source_url,
        "effective_at_utc": effective_at,
        "verified": True,
        "locally_first_observed_at_utc": value.get("locally_first_observed_at_utc"),
        "provider_release_time_distinct_from_local_observation": True,
    }


def build_version_evolution_report(
    *,
    boundary: VersionBoundary,
    windows: ComparisonWindows,
    deterministic_samples: Iterable[EvolutionSample],
    quantile_samples: Iterable[QuantileEvolutionSample] = (),
    freshness_samples: Iterable[FreshnessSample] = (),
    release_provenance: Mapping[str, Any],
    notable_limit: int = 10,
) -> dict[str, object]:
    deterministic_rows = list(deterministic_samples)
    common = common_version_samples(
        deterministic_rows,
        before_version=boundary.before_model_version,
        after_version=boundary.after_model_version,
    )
    pairs = common["pairs"]
    assert isinstance(pairs, tuple)
    report = {
        "report_type": REPORT_TYPE,
        "research_role": "primary_research",
        "warning_authority": "DWD",
        "research_verification_only": True,
        "boundary": boundary.as_dict(),
        "windows": windows.as_dict(),
        "common_sample_counts": {
            "before_n": common["before_n"],
            "after_n": common["after_n"],
            "common_n": common["common_n"],
            "location_id": DWD_10416.id,
        },
        "skill_deltas": skill_delta_summary(pairs),
        "quantile_calibration_deltas": quantile_calibration_delta(
            list(quantile_samples),
            before_version=boundary.before_model_version,
            after_version=boundary.after_model_version,
        ),
        "freshness_latency": freshness_evolution(
            list(freshness_samples),
            before_version=boundary.before_model_version,
            after_version=boundary.after_model_version,
        ),
        "event_summary": event_evolution_summary(pairs),
        "notable_cases": notable_error_delta_cases(pairs, limit=notable_limit),
        "release_provenance": validate_release_provenance(release_provenance),
        "limitations": [
            "before/after calendar periods may differ seasonally",
            "metrics use only common station_10416 samples with matching forecast semantics",
            "sample uncertainty is considered meaningful only when n>=30 per slice",
            "WeatherNext summary quantiles are not converted into synthetic CRPS, Brier score or event probability",
            "no global version winner is emitted by this contract",
        ],
        "private_home_in_measured_skill": False,
        "real_provider_payload_included": False,
        "corpus_mutation_performed": False,
    }
    private_key = _find_private_key(report)
    if private_key:
        raise ValueError(f"private report field forbidden: {private_key}")
    return report


def validate_report_payload(report: Mapping[str, Any]) -> dict[str, object]:
    private_key = _find_private_key(report)
    if private_key:
        raise ValueError(f"private report field forbidden: {private_key}")
    if report.get("report_type") != REPORT_TYPE:
        raise ValueError("unexpected version evolution report type")
    if report.get("warning_authority") != "DWD":
        raise ValueError("DWD warning authority must be preserved")
    if report.get("research_verification_only") is not True:
        raise ValueError("version evolution output must be labeled research verification")
    if report.get("corpus_mutation_performed") is not False:
        raise ValueError("version evolution report contract is read-only")
    release = report.get("release_provenance")
    if not isinstance(release, Mapping) or release.get("verified") is not True:
        raise ValueError("verified release provenance is required")
    counts = report.get("common_sample_counts")
    if not isinstance(counts, Mapping) or counts.get("location_id") != DWD_10416.id:
        raise ValueError("version evolution measured skill must remain station_10416")
    return {
        "schema_version": 1,
        "state": "version_evolution_report_valid",
        "report_type": REPORT_TYPE,
        "location_id": DWD_10416.id,
        "warning_authority": "DWD",
        "private_fields_exposed": False,
        "corpus_mutation_performed": False,
    }
