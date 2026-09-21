from __future__ import annotations

import json

from .config import Settings
from .db import Database
from .locations import BENCHMARK_LOCATION, BENCHMARK_TRUTH_STATION_ID
from .runtime import database_schema_state


def register_benchmark_location(database: Database) -> dict[str, object]:
    state = database_schema_state(database)
    if state.get("state") != "ready":
        raise RuntimeError("database schema must already be ready; benchmark registration never initializes or migrates schema")
    database.ensure_location(
        location_id=BENCHMARK_LOCATION.id,
        label=BENCHMARK_LOCATION.label,
        lat=BENCHMARK_LOCATION.lat,
        lon=BENCHMARK_LOCATION.lon,
        elevation_m=BENCHMARK_LOCATION.elevation_m,
        timezone=BENCHMARK_LOCATION.timezone,
    )
    return {
        "state": "registered",
        "location_id": BENCHMARK_LOCATION.id,
        "truth_station_id": BENCHMARK_TRUTH_STATION_ID,
        "coordinates_exposed": False,
        "schema_initialized": False,
        "schema_migrated": False,
        "production_data_authority_granted": False,
    }


def main() -> None:
    settings = Settings.from_env()
    database = Database(settings.database_url)
    print(json.dumps(register_benchmark_location(database), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
