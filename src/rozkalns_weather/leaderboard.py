from __future__ import annotations

from dataclasses import dataclass
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


def _metric_row(items: Sequence[SkillSample]) -> dict[str, object]:
    errors = [item.forecast - item.observed for item in items]
    absolute = [abs(error) for error in errors]
    ci = bootstrap_mean_ci(absolute)
    return {
        "n": len(items),
        "mae": mean(absolute) if items else None,
        "bias": mean(errors) if items else None,
        "sample_confidence": sample_confidence(len(items)),
        "mae_bootstrap_95_ci": None if ci is None else {"lower": ci.lower, "upper": ci.upper, "samples": ci.samples},
    }


def common_sample_leaderboard(samples: Iterable[SkillSample]) -> list[dict[str, object]]:
    items = list(samples)
    grouped: dict[tuple[str, str], list[SkillSample]] = {}
    for item in items:
        grouped.setdefault((item.mode, lead_bucket(item.lead_hours)), []).append(item)
    output: list[dict[str, object]] = []
    for (mode, bucket), bucket_items in sorted(grouped.items()):
        providers = sorted({item.provider for item in bucket_items})
        if len(providers) < 2:
            continue
        ids_by_provider = {
            provider: {item.sample_id for item in bucket_items if item.provider == provider}
            for provider in providers
        }
        common_ids = set.intersection(*(ids_by_provider[provider] for provider in providers))
        if not common_ids:
            continue
        for provider in providers:
            provider_items = [
                item for item in bucket_items
                if item.provider == provider and item.sample_id in common_ids
            ]
            versions = sorted({item.model_version or "unknown" for item in provider_items})
            if len(versions) > 1:
                for version in versions:
                    version_items = [item for item in provider_items if (item.model_version or "unknown") == version]
                    version_common = {
                        item.sample_id for item in version_items
                    }
                    peer_ids = set.intersection(
                        version_common,
                        *(ids_by_provider[peer] for peer in providers if peer != provider),
                    )
                    fair_items = [item for item in version_items if item.sample_id in peer_ids]
                    if fair_items:
                        output.append({
                            "mode": mode,
                            "lead_bucket": bucket,
                            "provider": provider,
                            "model_version": version,
                            "common_sample_ids": sorted(peer_ids),
                            **_metric_row(fair_items),
                        })
            else:
                output.append({
                    "mode": mode,
                    "lead_bucket": bucket,
                    "provider": provider,
                    "model_version": versions[0],
                    "common_sample_ids": sorted(common_ids),
                    **_metric_row(provider_items),
                })
    output.sort(key=lambda row: (str(row["mode"]), str(row["lead_bucket"]), str(row["provider"]), str(row["model_version"])))
    return output
