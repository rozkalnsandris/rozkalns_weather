from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
import random
from statistics import mean
from typing import Iterable, Sequence

from .verification import lead_bucket, sample_confidence


@dataclass(frozen=True, slots=True)
class SkillSample:
    sample_id: str
    provider: str
    model_version: str | None
    lead_hours: float
    forecast: float
    observed: float
    mode: str = "run_to_run"
    variable: str = "temperature_2m"
    p10: float | None = None
    p90: float | None = None


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    lower: float
    upper: float
    samples: int


def bootstrap_mean_ci(
    values: Sequence[float],
    *,
    confidence: float = 0.95,
    samples: int = 2000,
    seed: int = 0,
    minimum_n: int = 30,
) -> BootstrapInterval | None:
    values = tuple(float(value) for value in values)
    if len(values) < minimum_n:
        return None
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0,1)")
    if samples < 100:
        raise ValueError("samples must be >= 100")
    rng = random.Random(seed)
    estimates = sorted(
        mean(values[rng.randrange(len(values))] for _ in range(len(values)))
        for _ in range(samples)
    )
    tail = (1 - confidence) / 2
    lower_index = max(0, min(samples - 1, int(tail * samples)))
    upper_index = max(0, min(samples - 1, int((1 - tail) * samples) - 1))
    return BootstrapInterval(estimates[lower_index], estimates[upper_index], samples)


def _metric_row(
    items: Sequence[SkillSample],
    *,
    missingness: dict[str, int | float],
) -> dict[str, object]:
    errors = [item.forecast - item.observed for item in items]
    absolute = [abs(error) for error in errors]
    intervals = [item for item in items if item.p10 is not None and item.p90 is not None]
    ci = bootstrap_mean_ci(absolute)
    sufficiency = sample_confidence(len(items))
    coverage = (
        mean(1.0 if float(item.p10) <= item.observed <= float(item.p90) else 0.0 for item in intervals)
        if intervals
        else None
    )
    return {
        "n": len(items),
        "mae": mean(absolute) if items else None,
        "rmse": sqrt(mean(error * error for error in errors)) if items else None,
        "bias": mean(errors) if items else None,
        "p10_p90_coverage": coverage,
        "coverage_n": len(intervals),
        "sample_confidence": sufficiency,
        "sample_sufficiency_state": sufficiency,
        "missingness": missingness,
        "mae_bootstrap_95_ci": None
        if ci is None
        else {"lower": ci.lower, "upper": ci.upper, "samples": ci.samples},
    }


def common_sample_leaderboard(samples: Iterable[SkillSample]) -> list[dict[str, object]]:
    """Return strictly common, version-cohort metrics for comparable forecast samples.

    Comparison is bounded by mode, variable and lead bucket. A valid timestamp is then
    assigned to one cohort containing the exact model version for every compared
    provider. This prevents a row from silently pooling peer model-version periods.
    Missingness is reported against the union of timestamps seen in the comparison
    slice; metrics themselves use only the intersection.
    """

    items = list(samples)
    grouped: dict[tuple[str, str, str], list[SkillSample]] = {}
    for item in items:
        grouped.setdefault((item.mode, item.variable, lead_bucket(item.lead_hours)), []).append(item)

    output: list[dict[str, object]] = []
    for (mode, variable, bucket), bucket_items in sorted(grouped.items()):
        providers = sorted({item.provider for item in bucket_items})
        if len(providers) < 2:
            continue

        by_provider_sample: dict[tuple[str, str], SkillSample] = {}
        for item in bucket_items:
            key = (item.provider, item.sample_id)
            if key in by_provider_sample:
                raise ValueError(
                    f"duplicate sample identity in common comparison: {item.provider}:{item.sample_id}"
                )
            by_provider_sample[key] = item

        ids_by_provider = {
            provider: {item.sample_id for item in bucket_items if item.provider == provider}
            for provider in providers
        }
        expected_ids = set.union(*(ids_by_provider[provider] for provider in providers))
        common_ids = set.intersection(*(ids_by_provider[provider] for provider in providers))
        if not common_ids:
            continue

        cohorts: dict[tuple[tuple[str, str], ...], list[str]] = {}
        for sample_id in sorted(common_ids):
            version_vector = tuple(
                (
                    provider,
                    by_provider_sample[(provider, sample_id)].model_version or "unknown",
                )
                for provider in providers
            )
            cohorts.setdefault(version_vector, []).append(sample_id)

        for version_vector, cohort_ids in sorted(cohorts.items()):
            cohort_versions = dict(version_vector)
            for provider in providers:
                provider_ids = ids_by_provider[provider]
                expected_n = len(expected_ids)
                available_n = len(provider_ids)
                common_n = len(common_ids)
                missing_n = expected_n - available_n
                missingness: dict[str, int | float] = {
                    "expected_n": expected_n,
                    "available_n": available_n,
                    "missing_n": missing_n,
                    "common_n": common_n,
                    "excluded_non_common_n": available_n - common_n,
                    "missing_fraction": (missing_n / expected_n) if expected_n else 0.0,
                }
                provider_items = [
                    by_provider_sample[(provider, sample_id)]
                    for sample_id in cohort_ids
                ]
                output.append(
                    {
                        "mode": mode,
                        "variable": variable,
                        "lead_bucket": bucket,
                        "provider": provider,
                        "model_version": cohort_versions[provider],
                        "comparison_cohort": cohort_versions,
                        "common_sample_ids": list(cohort_ids),
                        **_metric_row(provider_items, missingness=missingness),
                    }
                )

    output.sort(
        key=lambda row: (
            str(row["mode"]),
            str(row["variable"]),
            str(row["lead_bucket"]),
            str(sorted(dict(row["comparison_cohort"]).items())),
            str(row["provider"]),
        )
    )
    return output
