from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import Mapping, Sequence

from .semantics import SUMMARY_QUANTILES, statistic_family

CONTRACT_VERSION = "forecast-quantile-admissibility-v1"
DEFAULT_QUANTILE_STATISTICS = ("p10", "p25", "p50", "p75", "p90")
IDENTITY_FIELDS = (
    "provider",
    "model_name",
    "model_version",
    "init_time_utc",
    "retrieved_at_utc",
    "valid_time_utc",
    "lead_hours",
    "variable",
    "unit",
    "location_id",
    "source_surface",
    "resolution",
)
_REASON_BY_IDENTITY_FIELD = {
    "provider": "MIXED_PROVIDER",
    "model_name": "MIXED_MODEL",
    "model_version": "MIXED_MODEL_VERSION",
    "init_time_utc": "MIXED_INIT_TIME",
    "retrieved_at_utc": "MIXED_RETRIEVAL_TIME",
    "valid_time_utc": "MIXED_VALID_TIME",
    "lead_hours": "MIXED_LEAD",
    "variable": "MIXED_VARIABLE",
    "unit": "MIXED_UNIT",
    "location_id": "MIXED_LOCATION",
    "source_surface": "MIXED_SOURCE_SURFACE",
    "resolution": "MIXED_RESOLUTION",
}


def _stable_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _identity_snapshot(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if not records:
        return {field: None for field in IDENTITY_FIELDS}
    first = records[0]
    snapshot: dict[str, object] = {}
    for field in IDENTITY_FIELDS:
        values = {_stable_value(record.get(field)) for record in records}
        snapshot[field] = first.get(field) if len(values) == 1 else None
    return snapshot


def evaluate_quantile_set(
    records: Sequence[Mapping[str, object]],
    *,
    expected_statistics: Sequence[str] = DEFAULT_QUANTILE_STATISTICS,
) -> dict[str, object]:
    """Evaluate one summary-quantile slice without inventing missing values.

    Records are expected to represent one provider/model/run/valid-time/variable/location
    slice. Summary quantiles remain summary quantiles: this gate never converts them to
    ensemble members or event probabilities.
    """

    items = tuple(records)
    expected = tuple(str(value) for value in expected_statistics)
    reasons: list[str] = []

    if not items:
        reasons.append("EMPTY_QUANTILE_SET")

    if not expected or len(set(expected)) != len(expected) or any(
        statistic not in SUMMARY_QUANTILES for statistic in expected
    ):
        reasons.append("INVALID_EXPECTED_QUANTILE_SET")

    statistics = tuple(str(record.get("statistic", "")) for record in items)
    counts = Counter(statistics)
    duplicate_statistics = tuple(sorted(key for key, count in counts.items() if count > 1))
    unsupported_statistics = tuple(
        sorted(
            {
                statistic
                for statistic in statistics
                if statistic not in SUMMARY_QUANTILES or statistic_family(statistic) != "summary_quantile"
            }
        )
    )

    if duplicate_statistics:
        reasons.append("DUPLICATE_QUANTILE_STATISTIC")
    if unsupported_statistics:
        reasons.append("NON_SUMMARY_QUANTILE")

    observed_statistics = set(statistics)
    missing_statistics = tuple(sorted(set(expected) - observed_statistics))
    unexpected_statistics = tuple(sorted(observed_statistics - set(expected)))
    if missing_statistics:
        reasons.append("INCOMPLETE_QUANTILE_SET")
    if unexpected_statistics:
        reasons.append("UNEXPECTED_QUANTILE_STATISTIC")

    for field in IDENTITY_FIELDS:
        values = {_stable_value(record.get(field)) for record in items}
        if len(values) > 1:
            reasons.append(_REASON_BY_IDENTITY_FIELD[field])

    quantile_values: dict[str, float] = {}
    invalid_value_statistics: list[str] = []
    if not duplicate_statistics:
        for record in items:
            statistic = str(record.get("statistic", ""))
            raw_value = record.get("value")
            try:
                value = float(raw_value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                invalid_value_statistics.append(statistic)
                continue
            if not isfinite(value):
                invalid_value_statistics.append(statistic)
                continue
            quantile_values[statistic] = value
    if invalid_value_statistics:
        reasons.append("INVALID_QUANTILE_VALUE")

    crossing_pairs: list[dict[str, object]] = []
    if not any(
        reason in reasons
        for reason in (
            "INVALID_EXPECTED_QUANTILE_SET",
            "DUPLICATE_QUANTILE_STATISTIC",
            "NON_SUMMARY_QUANTILE",
            "INCOMPLETE_QUANTILE_SET",
            "UNEXPECTED_QUANTILE_STATISTIC",
            "INVALID_QUANTILE_VALUE",
        )
    ):
        for lower_statistic, upper_statistic in zip(expected, expected[1:]):
            lower_value = quantile_values[lower_statistic]
            upper_value = quantile_values[upper_statistic]
            if lower_value > upper_value:
                crossing_pairs.append(
                    {
                        "lower_statistic": lower_statistic,
                        "lower_value": lower_value,
                        "upper_statistic": upper_statistic,
                        "upper_value": upper_value,
                    }
                )
        if crossing_pairs:
            reasons.append("QUANTILE_CROSSING")

    blocking_reasons = sorted(set(reasons))
    state = "PASS" if not blocking_reasons else "BLOCKED"
    interval_eligible = state == "PASS"

    return {
        "contract_version": CONTRACT_VERSION,
        "state": state,
        "reason_codes": blocking_reasons,
        "expected_statistics": list(expected),
        "observed_statistics": sorted(observed_statistics),
        "missing_statistics": list(missing_statistics),
        "unexpected_statistics": list(unexpected_statistics),
        "duplicate_statistics": list(duplicate_statistics),
        "invalid_value_statistics": sorted(set(invalid_value_statistics)),
        "crossing_pairs": crossing_pairs,
        "identity": _identity_snapshot(items),
        "quantile_values": {
            statistic: quantile_values[statistic]
            for statistic in expected
            if statistic in quantile_values
        },
        "metric_eligibility": {
            "interval_coverage": interval_eligible,
            "summary_interval": interval_eligible,
            "crps": False,
            "brier": False,
            "reliability": False,
        },
        "representation": "summary_quantiles",
        "ensemble_members": False,
        "event_probability": False,
        "fabricated_statistics": [],
    }


def interval_bounds(
    evidence: Mapping[str, object],
    *,
    lower_statistic: str = "p10",
    upper_statistic: str = "p90",
) -> tuple[float, float]:
    """Return validated summary-quantile bounds or fail closed."""

    if evidence.get("contract_version") != CONTRACT_VERSION or evidence.get("state") != "PASS":
        raise ValueError("quantile_set_not_admissible")
    eligibility = evidence.get("metric_eligibility")
    if not isinstance(eligibility, Mapping) or eligibility.get("interval_coverage") is not True:
        raise ValueError("quantile_interval_ineligible")
    values = evidence.get("quantile_values")
    if not isinstance(values, Mapping):
        raise ValueError("quantile_values_missing")
    if lower_statistic not in values or upper_statistic not in values:
        raise ValueError("quantile_interval_bounds_missing")
    lower = float(values[lower_statistic])
    upper = float(values[upper_statistic])
    if lower > upper:
        raise ValueError("quantile_interval_crossing")
    return lower, upper
