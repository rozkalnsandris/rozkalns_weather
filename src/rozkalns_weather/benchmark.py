from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Any

from .models import parse_time
from .probabilistic import bootstrap_mean_ci
from .verification import ErrorPair, forecast_was_available, lead_bucket, summarize


def common_sample_leaderboard(rows: Iterable[Mapping[str, Any]], *, mode: str = "run_to_run", min_ci_samples: int = 30) -> dict[str, object]:
    if mode not in {"run_to_run", "user_available"}:
        raise ValueError("mode must be run_to_run or user_available")
    prepared: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if row.get("provider") == "weathernext2":
            continue
        if mode == "user_available":
            valid = parse_time(str(row["valid_time_utc"]))
            retrieved = parse_time(str(row["retrieved_at_utc"]))
            upstream = parse_time(str(row["upstream_available_at_utc"])) if row.get("upstream_available_at_utc") else None
            if not forecast_was_available(upstream_available_at_utc=upstream, retrieved_at_utc=retrieved, decision_time_utc=valid):
                continue
        row["lead_bucket"] = lead_bucket(float(row["lead_hours"]))
        prepared.append(row)
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prepared:
        by_bucket[str(row["lead_bucket"])].append(row)
    output: list[dict[str, object]] = []
    common_counts: dict[str, int] = {}
    for bucket, bucket_rows in sorted(by_bucket.items()):
        provider_times: dict[str, set[str]] = defaultdict(set)
        for row in bucket_rows:
            provider_times[str(row["provider"])].add(str(row["valid_time_utc"]))
        if len(provider_times) < 2:
            common_counts[bucket] = 0
            continue
        common_times = set.intersection(*(set(times) for times in provider_times.values()))
        common_counts[bucket] = len(common_times)
        grouped: dict[tuple[str, str], list[ErrorPair]] = defaultdict(list)
        for row in bucket_rows:
            if str(row["valid_time_utc"]) not in common_times:
                continue
            grouped[(str(row["provider"]), str(row.get("model_version") or "unknown"))].append(ErrorPair(provider=str(row["provider"]), model_version=row.get("model_version"), lead_hours=float(row["lead_hours"]), forecast=float(row["forecast_value"]), observed=float(row["observed_value"]), p10=float(row["p10"]) if row.get("p10") is not None else None, p90=float(row["p90"]) if row.get("p90") is not None else None))
        for (provider, version), pairs in sorted(grouped.items()):
            metrics = summarize(pairs)
            ci = bootstrap_mean_ci([abs(pair.forecast - pair.observed) for pair in pairs], min_samples=min_ci_samples)
            output.append({"provider": provider, "model_version": version, "lead_bucket": bucket, **metrics, "mae_ci95_lower": ci["lower"], "mae_ci95_upper": ci["upper"], "ci_state": ci["state"]})
    return {"mode": mode, "common_sample_counts": common_counts, "rows": output}


def event_summary(rows: Iterable[Mapping[str, Any]], *, temperature_extreme_c: float = 30.0, precipitation_event_mm: float = 0.1, gust_event_ms: float = 15.0) -> dict[str, object]:
    counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for raw in rows:
        row = dict(raw)
        provider = str(row.get("provider") or "unknown")
        variable = str(row.get("variable") or "")
        forecast = float(row.get("forecast_value") or 0.0)
        observed = float(row.get("observed_value") or 0.0)
        if variable == "temperature_2m" and max(forecast, observed) >= temperature_extreme_c:
            counters[provider]["temperature_extreme_cases"] += 1
        elif variable == "precipitation_1h" and max(forecast, observed) >= precipitation_event_mm:
            counters[provider]["precipitation_event_cases"] += 1
        elif variable == "wind_gust_10m" and max(forecast, observed) >= gust_event_ms:
            counters[provider]["gust_event_cases"] += 1
    return {"thresholds": {"temperature_extreme_c": temperature_extreme_c, "precipitation_event_mm": precipitation_event_mm, "gust_event_ms": gust_event_ms}, "providers": {provider: dict(values) for provider, values in sorted(counters.items())}}
