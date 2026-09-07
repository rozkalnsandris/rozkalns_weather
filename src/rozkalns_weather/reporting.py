from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from .db import Database
from .locations import DWD_10416
from .verification import ErrorPair, lead_bucket, sample_confidence, summarize

WEATHERNEXT_RELEASE_NOTES_URL = "https://developers.google.com/weathernext/release-notes"

def _month_bounds(month: str) -> tuple[str, str]:
    start = datetime.strptime(month + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc); end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1); return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")

def monthly_weather_next_report(database: Database, *, month: str) -> dict[str, Any]:
    start, end = _month_bounds(month)
    with database.connect() as connection:
        rows = [dict(row) for row in connection.execute("""WITH forecast AS (SELECT r.provider,r.model_version,r.location_id,r.init_time_quality,r.init_time_utc,v.valid_time_utc,v.lead_hours,v.value AS forecast_value,MAX(CASE WHEN v.statistic='p10' THEN v.value END) OVER (PARTITION BY r.id,v.valid_time_utc,v.variable) AS p10,MAX(CASE WHEN v.statistic='p90' THEN v.value END) OVER (PARTITION BY r.id,v.valid_time_utc,v.variable) AS p90,v.statistic FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id WHERE r.location_id=? AND v.variable='temperature_2m' AND v.statistic IN ('deterministic','mean','p10','p90') AND v.valid_time_utc>=? AND v.valid_time_utc<?) SELECT f.*,o.value AS observed_value FROM forecast f JOIN observations o ON o.variable='temperature_2m' AND o.observed_at_utc=f.valid_time_utc AND o.location_id=f.location_id AND o.source_provider='DWD' WHERE f.statistic IN ('deterministic','mean') ORDER BY f.valid_time_utc,f.provider""", (DWD_10416.id, start, end)).fetchall()]
    rows_by_bucket: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows: rows_by_bucket[lead_bucket(float(row["lead_hours"]))].append(row)
    metrics: list[dict[str, object]] = []; common_counts: dict[str, int] = {}; notable: list[dict[str, object]] = []
    for bucket, bucket_rows in sorted(rows_by_bucket.items()):
        provider_times: dict[str, set[str]] = defaultdict(set)
        for row in bucket_rows: provider_times[str(row["provider"])].add(str(row["valid_time_utc"]))
        common_times: set[str] | None = None
        for times in provider_times.values(): common_times = set(times) if common_times is None else common_times & times
        common_times = common_times or set(); common_counts[bucket] = len(common_times); grouped: dict[tuple[str, str], list[ErrorPair]] = defaultdict(list)
        for row in bucket_rows:
            if common_times and str(row["valid_time_utc"]) not in common_times: continue
            pair = ErrorPair(provider=str(row["provider"]), model_version=row.get("model_version"), lead_hours=float(row["lead_hours"]), forecast=float(row["forecast_value"]), observed=float(row["observed_value"]), p10=float(row["p10"]) if row.get("p10") is not None else None, p90=float(row["p90"]) if row.get("p90") is not None else None); grouped[(pair.provider, pair.model_version or "unknown")].append(pair)
            if pair.provider == "weathernext3": notable.append({"valid_time_utc": row["valid_time_utc"], "lead_bucket": bucket, "error_abs_degC": abs(pair.forecast - pair.observed), "model_version": pair.model_version})
        for (provider, version), items in sorted(grouped.items()): metrics.append({"provider": provider, "model_version": version, "lead_bucket": bucket, **summarize(items)})
    notable.sort(key=lambda item: float(item["error_abs_degC"]), reverse=True); wn_n = sum(int(item["n"]) for item in metrics if item["provider"] == "weathernext3")
    return {"report_type": "weathernext_station_skill_monthly_v2", "month": month, "comparison_location": {"id": DWD_10416.id, "station_id": "10416"}, "truth_source": "DWD WMO 10416", "common_comparison_timestamps_by_lead_bucket": common_counts, "weather_next_sample_confidence": sample_confidence(wn_n), "small_sample_warning": wn_n < 30, "metrics": metrics, "notable_weather_next_misses": notable[:10], "release_notes_source": WEATHERNEXT_RELEASE_NOTES_URL, "release_note_events": [], "note": "Home-point forecasts are excluded from measured skill until a home observation source exists. Rankings use common valid timestamps within each lead bucket."}
