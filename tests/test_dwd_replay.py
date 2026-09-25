from __future__ import annotations

import io
import json
from pathlib import Path

from rozkalns_weather.dwd_replay import CONTRACT_VERSION, main, replay_scenario

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "dwd_warning_radar_replay.json"
CONTRACT = ROOT / "contracts" / "dwd-warning-radar-replay-v1.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _fresh_frames() -> list[dict[str, str]]:
    return [
        {"timestamp": "2026-09-12T09:55:00Z", "kind": "radar_observed"},
        {"timestamp": "2026-09-12T10:30:00Z", "kind": "radar_nowcast"},
    ]


def test_machine_readable_contract_matches_python_contract() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema"] == CONTRACT_VERSION
    assert contract["warning_authority"] == "DWD"
    assert contract["model_warning_substitution_allowed"] is False
    assert contract["network_access_performed"] is False
    assert contract["runtime_mutation_performed"] is False
    assert contract["privacy"]["input_coordinates"] == "synthetic-only"
    assert contract["privacy"]["coordinates_in_output"] is False


def test_full_lifecycle_replay_is_deterministic_and_privacy_safe() -> None:
    scenario = _fixture()
    first = replay_scenario(scenario)
    second = replay_scenario(scenario)

    assert first == second
    assert first["contract_version"] == CONTRACT_VERSION
    assert first["state"] == "WARN"
    assert first["warning_event_summary"] == {"issue": 2, "update": 2, "cancel": 2, "expire": 1}
    assert first["network_access_performed"] is False
    assert first["runtime_mutation_performed"] is False
    assert first["live_authority_granted"] is False
    assert first["privacy"] == {
        "synthetic_coordinates_used": True,
        "coordinates_exposed": False,
        "geometry_exposed": False,
        "credentials_exposed": False,
        "raw_payload_exposed": False,
    }

    rendered = json.dumps(first, sort_keys=True)
    assert '"lat"' not in rendered
    assert '"lon"' not in rendered
    assert "49.5" not in rendered
    assert "52.0" not in rendered
    assert "Synthetic warning" not in rendered


def test_replay_covers_overlap_geometry_update_expiry_missing_radar_and_recovery() -> None:
    result = replay_scenario(_fixture())
    steps = result["steps"]

    assert [step["state"] for step in steps] == ["PASS", "PASS", "WARN", "WARN", "PASS", "PASS"]

    assert steps[0]["warning_summary"]["active"] == 1
    assert steps[0]["warning_summary"]["applies_to_location"] == 1
    assert steps[0]["api_state"]["warnings"] == "official_warning_active"
    assert steps[0]["pwa_state"]["warning_authority"] == "DWD"

    assert steps[1]["warning_summary"]["active"] == 2
    assert steps[1]["warning_summary"]["applies_to_location"] == 2

    assert steps[2]["warning_summary"]["applies_to_location"] == 1
    assert "WARNING_GEOMETRY_OUTSIDE_MAP" in steps[2]["warning_reason_codes"]
    assert "RADAR_OBSERVED_STALE" in steps[2]["warning_reason_codes"]
    assert "RADAR_NOWCAST_MISSING" in steps[2]["warning_reason_codes"]
    assert steps[2]["api_state"]["radar"] == "stale"

    assert steps[3]["warning_summary"]["expired"] == 1
    assert "RADAR_OBSERVED_MISSING" in steps[3]["warning_reason_codes"]
    assert "RADAR_NOWCAST_MISSING" in steps[3]["warning_reason_codes"]
    assert steps[3]["api_state"]["radar"] == "missing"

    assert steps[4]["warning_summary"]["active"] == 0
    assert steps[4]["api_state"]["warnings"] == "no_active_official_warning"
    assert steps[4]["api_state"]["radar"] == "fresh"

    assert steps[5]["warning_summary"]["received"] == 0
    assert steps[5]["pwa_state"]["degraded"] is False


def test_dwd_authority_and_model_separation_are_invariant_for_every_step() -> None:
    result = replay_scenario(_fixture())
    for step in result["steps"]:
        assert step["presentation"]["warnings"]["authority"] == "DWD"
        assert step["presentation"]["warnings"]["official"] is True
        assert step["presentation"]["warnings"]["model_warning_substitution"] is False
        assert step["presentation"]["radar"]["not_model_forecast"] is True
        assert step["api_state"]["model_forecast_is_separate"] is True
        assert step["pwa_state"]["model_warning_substitution"] is False
        assert step["pwa_state"]["radar_not_model_forecast"] is True
    assert "WeatherNext" not in json.dumps(result, sort_keys=True)


def test_invalid_warning_event_order_fails_closed_with_stable_reason_codes() -> None:
    base = {
        "scenario_id": "invalid-event-order",
        "location": {"lat": 50.0, "lon": 8.0},
        "map_bounds": {"south": 49.0, "west": 7.0, "north": 51.0, "east": 9.0},
        "steps": [
            {
                "at": "2026-09-12T10:00:00Z",
                "warning_events": [{"action": "update", "id": "missing-warning", "changes": {"headline": "x"}}],
                "radar_frames": _fresh_frames(),
            }
        ],
    }
    result = replay_scenario(base)
    assert result["state"] == "BLOCKED"
    assert result["steps"][0]["blocking_reason_codes"] == ["REPLAY_WARNING_UPDATE_MISSING_BASE"]

    base["scenario_id"] = "cancel-missing"
    base["steps"][0]["warning_events"] = [{"action": "cancel", "id": "missing-warning"}]  # type: ignore[index]
    cancelled = replay_scenario(base)
    assert "REPLAY_WARNING_CANCEL_MISSING_BASE" in cancelled["steps"][0]["blocking_reason_codes"]

    base["scenario_id"] = "expire-missing"
    base["steps"][0]["warning_events"] = [{"action": "expire", "id": "missing-warning"}]  # type: ignore[index]
    expired = replay_scenario(base)
    assert "REPLAY_WARNING_EXPIRE_MISSING_BASE" in expired["steps"][0]["blocking_reason_codes"]


def test_duplicate_issue_and_non_increasing_time_fail_closed() -> None:
    warning = {
        "identifier": "warning-1",
        "sent": "2026-09-12T09:50:00Z",
        "effective": "2026-09-12T09:50:00Z",
        "expires": "2026-09-12T12:00:00Z",
        "polygon": "49.5,7.5 49.5,8.5 50.5,8.5 50.5,7.5 49.5,7.5",
    }
    scenario = {
        "scenario_id": "duplicate-and-time",
        "location": {"lat": 50.0, "lon": 8.0},
        "map_bounds": {"south": 49.0, "west": 7.0, "north": 51.0, "east": 9.0},
        "steps": [
            {
                "at": "2026-09-12T10:00:00Z",
                "warning_events": [
                    {"action": "issue", "warning": warning},
                    {"action": "issue", "warning": warning},
                ],
                "radar_frames": _fresh_frames(),
            },
            {"at": "2026-09-12T10:00:00Z", "warning_events": []},
        ],
    }
    result = replay_scenario(scenario)
    assert result["state"] == "BLOCKED"
    assert "REPLAY_WARNING_DUPLICATE_ISSUE" in result["steps"][0]["blocking_reason_codes"]
    assert "REPLAY_STEP_TIME_NOT_INCREASING" in result["steps"][1]["blocking_reason_codes"]


def test_cli_emits_sanitized_machine_readable_replay_evidence() -> None:
    input_stream = io.StringIO(json.dumps(_fixture()))
    output_stream = io.StringIO()
    rc = main([], input_stream, output_stream)
    assert rc == 0
    payload = json.loads(output_stream.getvalue())
    assert payload["state"] == "WARN"
    assert payload["scenario_id"] == "warning-radar-lifecycle"
    assert len(payload["scenario_sha256"]) == 64
    assert payload["network_access_performed"] is False
    assert payload["runtime_mutation_performed"] is False
    assert '"lat"' not in output_stream.getvalue()
    assert '"lon"' not in output_stream.getvalue()
