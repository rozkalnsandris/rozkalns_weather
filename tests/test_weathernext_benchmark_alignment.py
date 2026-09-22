from datetime import datetime, timezone
import json
from pathlib import Path

from rozkalns_weather.locations import BENCHMARK_LOCATION, DWD_10416, DWD_CDC_05480
from rozkalns_weather.weathernext_access import (
    build_canary_plan,
    build_first_snapshot_write_envelope,
    expected_required_schema_fingerprint,
    validate_first_access_evidence,
)
from rozkalns_weather.weathernext_final_live_plan import build_final_live_plan


def _first_access_evidence() -> dict[str, object]:
    return {
        "state": "canary_ready_for_snapshot",
        "selected_init_time_utc": "2026-09-08T06:00:00Z",
        "schema": {
            "state": "linked_dataset_ready",
            "observed_required_fingerprint": expected_required_schema_fingerprint(),
        },
        "dry_run": [
            {"resolution": "0p05", "within_cap": True, "estimated_bytes": 100, "maximum_bytes_billed": 1000},
            {"resolution": "0p1", "within_cap": True, "estimated_bytes": 100, "maximum_bytes_billed": 1000},
        ],
        "canary": {"product_surfaces_complete": True},
        "provenance": {"complete": True},
    }


def test_weather_next_first_access_contracts_share_canonical_benchmark() -> None:
    assert BENCHMARK_LOCATION is DWD_CDC_05480
    assert BENCHMARK_LOCATION.id == "station_05480"
    assert DWD_10416.id == "station_10416"
    assert DWD_10416.id != BENCHMARK_LOCATION.id

    first_access = json.loads(Path("deploy/weathernext-first-access.json").read_text())
    sustained = json.loads(Path("deploy/weathernext-sustained-collection.json").read_text())
    snapshot = json.loads(Path("deploy/weathernext-first-snapshot-admission.json").read_text())
    final_live = json.loads(Path("deploy/weathernext-final-live-plan.json").read_text())

    assert first_access["query_guardrails"]["initial_location_id"] == BENCHMARK_LOCATION.id
    assert sustained["first_month_verification"]["location_id"] == BENCHMARK_LOCATION.id
    assert sustained["first_month_verification"]["truth_source"] == BENCHMARK_LOCATION.label
    assert snapshot["provider"]["location_id"] == BENCHMARK_LOCATION.id
    assert BENCHMARK_LOCATION.id in snapshot["identity"]["includes"]
    assert final_live["target"]["location_id"] == BENCHMARK_LOCATION.id


def test_planner_evidence_write_envelope_and_live_plan_cannot_diverge() -> None:
    plan = build_canary_plan(
        now=datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc),
        init_time=datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc),
        hours_limit=6,
        maximum_bytes_billed=1000,
    )
    validated = validate_first_access_evidence(_first_access_evidence())
    write_envelope = build_first_snapshot_write_envelope(_first_access_evidence())
    final_live = build_final_live_plan()

    assert plan["location_id"] == BENCHMARK_LOCATION.id
    assert validated["location_id"] == BENCHMARK_LOCATION.id
    assert write_envelope["location_id"] == BENCHMARK_LOCATION.id
    assert final_live["target"]["location_id"] == BENCHMARK_LOCATION.id


def test_first_access_docs_do_not_restore_legacy_query_scope() -> None:
    first_access_doc = Path("docs/WEATHERNEXT_FIRST_ACCESS.md").read_text()
    sustained_doc = Path("docs/WEATHERNEXT_SUSTAINED_COLLECTION.md").read_text()
    final_live_doc = Path("docs/WEATHERNEXT_FINAL_LIVE_PLAN.md").read_text()

    assert "query_scope=station_05480" in first_access_doc
    assert "query_scope=station_10416" not in first_access_doc
    assert "location_scope=station_05480" in sustained_doc
    assert "location_scope=station_10416" not in sustained_doc
    assert "access has one init, `station_05480`" in final_live_doc
