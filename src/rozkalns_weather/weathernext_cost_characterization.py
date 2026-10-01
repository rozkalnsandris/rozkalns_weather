from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable, Mapping

from .config import Settings
from .locations import BENCHMARK_LOCATION
from .providers.weathernext import build_point_query, validate_query_contract

MAX_CHARACTERIZATION_HOURS = 24


class WeatherNextCostCharacterizationError(RuntimeError):
    """Sanitized fail-closed error for dry-run-only BigQuery characterization."""


@dataclass(frozen=True, slots=True)
class ClusteredDryRunEstimate:
    resolution: str
    estimated_bytes: int
    estimate_accuracy: str

    def as_dict(self) -> dict[str, object]:
        return {
            "resolution": self.resolution,
            "estimated_bytes": self.estimated_bytes,
            "estimate_accuracy": self.estimate_accuracy,
        }


def _default_job_config() -> Any:
    try:
        from google.cloud import bigquery  # type: ignore
    except ImportError as exc:
        raise WeatherNextCostCharacterizationError(
            "WeatherNext BigQuery characterization requires the optional 'weathernext' dependency"
        ) from exc
    return bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)


def _estimate_accuracy(job: Any) -> str:
    raw = getattr(job, "_properties", None)
    if not isinstance(raw, Mapping):
        return "UNKNOWN"
    statistics = raw.get("statistics")
    if not isinstance(statistics, Mapping):
        return "UNKNOWN"
    query = statistics.get("query")
    if not isinstance(query, Mapping):
        return "UNKNOWN"
    value = query.get("totalBytesProcessedAccuracy")
    if value in {"UNKNOWN", "PRECISE", "LOWER_BOUND", "UPPER_BOUND"}:
        return str(value)
    return "UNKNOWN"


def characterize_clustered_query_costs(
    *,
    client: Any,
    project: str,
    dataset: str,
    init_time: datetime,
    hours_limit: int = 6,
    job_config_factory: Callable[[], Any] | None = None,
) -> dict[str, object]:
    """Return sanitized uncapped dry-run estimates for the two exact #122 queries.

    BigQuery geospatial clustering can make pre-execution estimates conservative.
    This helper intentionally does not set ``maximum_bytes_billed`` because a dry
    run is uncharged and the purpose of this stage is to learn the provider's
    pre-execution upper bound before any owner decision about a real-query cap.

    It never executes a non-dry-run query, never writes SQLite, and never emits
    project/dataset identity, coordinates, SQL, or private-derived query hashes.
    """

    if init_time.tzinfo is None:
        raise ValueError("init_time must be timezone-aware")
    if type(hours_limit) is not int or not 1 <= hours_limit <= MAX_CHARACTERIZATION_HOURS:
        raise ValueError(f"hours_limit must be between 1 and {MAX_CHARACTERIZATION_HOURS}")

    init_time = init_time.astimezone(timezone.utc)
    queries = (
        build_point_query(
            project=project,
            dataset=dataset,
            lat=BENCHMARK_LOCATION.lat,
            lon=BENCHMARK_LOCATION.lon,
            init_time=init_time,
            resolution="0p05",
            hours_limit=hours_limit,
        ),
        build_point_query(
            project=project,
            dataset=dataset,
            lat=BENCHMARK_LOCATION.lat,
            lon=BENCHMARK_LOCATION.lon,
            init_time=init_time,
            resolution="0p1",
            hours_limit=hours_limit,
        ),
    )

    factory = job_config_factory or _default_job_config
    estimates: list[ClusteredDryRunEstimate] = []
    for query in queries:
        errors = validate_query_contract(query)
        if errors:
            raise WeatherNextCostCharacterizationError(
                "exact WeatherNext query contract is invalid before cost characterization"
            )
        config = factory()
        if getattr(config, "dry_run", None) is not True:
            raise WeatherNextCostCharacterizationError("cost characterization must be dry-run only")
        if getattr(config, "maximum_bytes_billed", None) is not None:
            raise WeatherNextCostCharacterizationError(
                "cost characterization must not set maximum_bytes_billed"
            )
        job = client.query(
            query.sql,
            job_config=config,
            retry=None,
            job_retry=None,
            timeout=60,
        )
        estimated = getattr(job, "total_bytes_processed", None)
        if type(estimated) is not int or estimated < 0:
            raise WeatherNextCostCharacterizationError(
                "dry-run estimate is absent or invalid"
            )
        estimates.append(
            ClusteredDryRunEstimate(
                resolution=query.resolution,
                estimated_bytes=estimated,
                estimate_accuracy=_estimate_accuracy(job),
            )
        )

    return {
        "schema_version": 1,
        "state": "clustered_cost_characterized",
        "provider": "weathernext3",
        "model_version_contract": "3.0.0",
        "location_id": BENCHMARK_LOCATION.id,
        "selected_init_time_utc": init_time.isoformat().replace("+00:00", "Z"),
        "hours_limit": hours_limit,
        "dry_run": [item.as_dict() for item in estimates],
        "maximum_bytes_billed_applied": False,
        "actual_query_performed": False,
        "cost_incurred": False,
        "coordinates_exposed": False,
        "private_identifiers_exposed": False,
        "production_write_performed": False,
        "requires_owner_real_query_cost_decision": True,
    }


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m rozkalns_weather.weathernext_cost_characterization"
    )
    parser.add_argument("--init", required=True, help="one explicit UTC WeatherNext init")
    parser.add_argument("--hours-limit", type=int, default=6)
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.weathernext_cloud_configured:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "state": "access_pending",
                    "actual_query_performed": False,
                    "cost_incurred": False,
                    "private_identifiers_exposed": False,
                },
                sort_keys=True,
                indent=2,
            )
        )
        raise SystemExit(2)

    assert settings.google_cloud_project and settings.weathernext_bigquery_dataset
    try:
        from google.cloud import bigquery  # type: ignore

        client = bigquery.Client(project=settings.google_cloud_project)
        payload = characterize_clustered_query_costs(
            client=client,
            project=settings.google_cloud_project,
            dataset=settings.weathernext_bigquery_dataset,
            init_time=_parse_utc(args.init),
            hours_limit=args.hours_limit,
        )
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "state": "cost_characterization_failed",
            "error_class": type(exc).__name__,
            "actual_query_performed": False,
            "cost_incurred": False,
            "coordinates_exposed": False,
            "private_identifiers_exposed": False,
            "production_write_performed": False,
        }
        print(json.dumps(payload, sort_keys=True, indent=2))
        raise SystemExit(2) from None

    print(json.dumps(payload, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
