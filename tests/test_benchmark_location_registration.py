from __future__ import annotations

from pathlib import Path

import pytest

from rozkalns_weather.benchmark_location_registration import register_benchmark_location
from rozkalns_weather.db import Database
from rozkalns_weather.locations import BENCHMARK_LOCATION, BENCHMARK_TRUTH_STATION_ID


def test_registration_requires_preexisting_ready_schema(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'weather.db'}")
    with pytest.raises(RuntimeError, match="schema must already be ready"):
        register_benchmark_location(database)


def test_registration_is_explicit_idempotent_and_pins_public_station(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'weather.db'}")
    database.initialize()
    first = register_benchmark_location(database)
    second = register_benchmark_location(database)
    assert first == second
    assert first == {
        "state": "registered",
        "location_id": BENCHMARK_LOCATION.id,
        "truth_station_id": BENCHMARK_TRUTH_STATION_ID,
        "coordinates_exposed": False,
        "schema_initialized": False,
        "schema_migrated": False,
        "production_data_authority_granted": False,
    }
    with database.connect() as connection:
        row = connection.execute("SELECT * FROM locations WHERE id=?", (BENCHMARK_LOCATION.id,)).fetchone()
    assert row is not None
    assert row["label"] == BENCHMARK_LOCATION.label
    assert float(row["lat"]) == pytest.approx(BENCHMARK_LOCATION.lat)
    assert float(row["lon"]) == pytest.approx(BENCHMARK_LOCATION.lon)
