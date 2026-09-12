from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import io
import json

from rozkalns_weather.map_validation import main, validate_map_evidence

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def _alert() -> dict[str, object]:
    return {
        "identifier": "fixture-warning-1",
        "sent": "2026-09-12T09:00:00Z",
        "effective": "2026-09-12T09:00:00Z",
        "expires": "2026-09-12T12:00:00Z",
        "lifecycle": "active",
        "polygon": "49.5,7.5 49.5,8.5 50.5,8.5 50.5,7.5 49.5,7.5",
    }


def _evidence() -> dict[str, object]:
    return {
        "location": {"lat": 50.0, "lon": 8.0},
        "map_bounds": {"south": 49.0, "west": 7.0, "north": 51.0, "east": 9.0},
        "warnings": {
            "authority": "DWD",
            "official": True,
            "kind": "official_warning",
            "alerts": [_alert()],
        },
        "radar": {
            "not_model_forecast": True,
            "frames": [
                {"timestamp": "2026-09-12T09:50:00Z", "kind": "radar_observed"},
                {"timestamp": "2026-09-12T10:30:00Z", "kind": "radar_nowcast"},
            ],
        },
    }


def test_valid_fixture_passes_without_coordinate_or_geometry_output() -> None:
    result = validate_map_evidence(_evidence(), now=NOW)
    assert result["state"] == "PASS"
    assert result["reason_codes"] == []
    assert result["warning_summary"]["applies_to_location"] == 1
    assert result["presentation"]["warnings"]["authority"] == "DWD"
    assert result["presentation"]["warnings"]["official"] is True
    assert result["presentation"]["warnings"]["model_warning_substitution"] is False
    assert result["presentation"]["ui_separation_ok"] is True
    rendered = json.dumps(result, sort_keys=True)
    assert '"lat"' not in rendered
    assert '"lon"' not in rendered
    assert "49.5" not in rendered
    assert result["privacy"] == {
        "coordinates_exposed": False,
        "geometry_exposed": False,
        "credentials_exposed": False,
        "raw_payload_exposed": False,
    }


def test_absent_private_coordinates_fail_closed() -> None:
    evidence = _evidence()
    evidence.pop("location")
    result = validate_map_evidence(evidence, now=NOW)
    assert result["state"] == "BLOCKED"
    assert "PRIVATE_COORDINATES_REQUIRED" in result["blocking_reason_codes"]


def test_map_bounds_drift_blocks_validation() -> None:
    evidence = _evidence()
    evidence["map_bounds"] = {"south": 40.0, "west": 1.0, "north": 41.0, "east": 2.0}
    result = validate_map_evidence(evidence, now=NOW)
    assert result["state"] == "BLOCKED"
    assert "MAP_CENTER_OUTSIDE_BOUNDS" in result["blocking_reason_codes"]


def test_stale_observed_and_missing_nowcast_are_warn_states() -> None:
    evidence = _evidence()
    evidence["radar"] = {
        "not_model_forecast": True,
        "frames": [{"timestamp": "2026-09-12T09:30:00Z", "kind": "radar_observed"}],
    }
    result = validate_map_evidence(evidence, now=NOW)
    assert result["state"] == "WARN"
    assert result["warning_reason_codes"] == ["RADAR_NOWCAST_MISSING", "RADAR_OBSERVED_STALE"]


def test_latest_warning_revision_can_expire_previous_active_revision() -> None:
    evidence = _evidence()
    latest = deepcopy(_alert())
    latest.update(
        {
            "sent": "2026-09-12T09:30:00Z",
            "expires": "2026-09-12T09:45:00Z",
            "lifecycle": "expired",
        }
    )
    evidence["warnings"]["alerts"] = [_alert(), latest]  # type: ignore[index]
    result = validate_map_evidence(evidence, now=NOW)
    assert result["state"] == "PASS"
    assert result["warning_summary"]["received"] == 2
    assert result["warning_summary"]["latest"] == 1
    assert result["warning_summary"]["expired"] == 1
    assert result["warning_summary"]["active"] == 0


def test_geojson_geometry_supported_but_non_dwd_authority_is_blocked() -> None:
    evidence = _evidence()
    evidence["warnings"]["authority"] = "WeatherNext"  # type: ignore[index]
    alert = deepcopy(_alert())
    alert.pop("polygon")
    alert["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[7.5, 49.5], [8.5, 49.5], [8.5, 50.5], [7.5, 50.5], [7.5, 49.5]]],
    }
    evidence["warnings"]["alerts"] = [alert]  # type: ignore[index]
    result = validate_map_evidence(evidence, now=NOW)
    assert result["state"] == "BLOCKED"
    assert "DWD_WARNING_AUTHORITY_CONTRACT_INVALID" in result["blocking_reason_codes"]
    assert result["warning_summary"]["applies_to_location"] == 1


def test_nowcast_beyond_two_hours_is_blocked() -> None:
    evidence = _evidence()
    evidence["radar"] = {
        "not_model_forecast": True,
        "frames": [
            {"timestamp": "2026-09-12T09:50:00Z", "kind": "radar_observed"},
            {"timestamp": "2026-09-12T12:05:00Z", "kind": "radar_nowcast"},
        ],
    }
    result = validate_map_evidence(evidence, now=NOW)
    assert result["state"] == "BLOCKED"
    assert "RADAR_NOWCAST_HORIZON_EXCEEDED" in result["blocking_reason_codes"]


def test_cli_reads_injected_coordinates_from_stdin_and_redacts_output() -> None:
    input_stream = io.StringIO(json.dumps(_evidence()))
    output_stream = io.StringIO()
    rc = main(["--now", "2026-09-12T10:00:00Z"], input_stream, output_stream)
    assert rc == 0
    payload = json.loads(output_stream.getvalue())
    assert payload["state"] == "PASS"
    assert payload["network_access_performed"] is False
    assert payload["runtime_mutation_performed"] is False
    rendered = output_stream.getvalue()
    assert '"lat"' not in rendered
    assert '"lon"' not in rendered
    assert "49.5" not in rendered
