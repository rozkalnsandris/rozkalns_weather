from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import re
import sys
from typing import Any, TextIO

from .map_validation import validate_map_evidence

CONTRACT_VERSION = "dwd-warning-radar-replay-v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_STATE_ORDER = {"PASS": 0, "WARN": 1, "BLOCKED": 2}


class ReplayError(ValueError):
    """Invalid deterministic replay input."""


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ReplayError("timestamp must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayError("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise ReplayError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _warning_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    identifier = value.get("id") or value.get("identifier")
    if not isinstance(identifier, str) or not _SAFE_ID.fullmatch(identifier):
        return None
    return identifier


def _combine_state(states: list[str]) -> str:
    if not states:
        return "BLOCKED"
    return max(states, key=lambda state: _STATE_ORDER.get(state, 2))


def _radar_surface_state(result: dict[str, Any]) -> str:
    blocking = set(result.get("blocking_reason_codes", []))
    warning = set(result.get("warning_reason_codes", []))
    if any(code.startswith("RADAR_") for code in blocking):
        return "blocked"
    if "RADAR_EVIDENCE_MISSING" in warning or "RADAR_OBSERVED_MISSING" in warning:
        return "missing"
    if "RADAR_OBSERVED_STALE" in warning or "RADAR_NOWCAST_MISSING" in warning:
        return "stale"
    return "fresh"


def _step_surface_state(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = result["warning_summary"]
    authority_blocked = "DWD_WARNING_AUTHORITY_CONTRACT_INVALID" in result["blocking_reason_codes"]
    if authority_blocked:
        warning_state = "blocked"
    elif summary["active"] > 0:
        warning_state = "official_warning_active"
    elif summary["upcoming"] > 0:
        warning_state = "official_warning_upcoming"
    else:
        warning_state = "no_active_official_warning"
    radar_state = _radar_surface_state(result)
    api_state = {
        "warnings": warning_state,
        "warning_authority": "DWD",
        "radar": radar_state,
        "radar_kind": "observed_nowcast",
        "model_forecast_is_separate": True,
    }
    pwa_state = {
        "warnings_region": warning_state,
        "warning_panel_kind": "official_warning",
        "warning_authority": "DWD",
        "model_warning_substitution": False,
        "radar_region": radar_state,
        "radar_not_model_forecast": True,
        "degraded": result["state"] != "PASS",
    }
    return api_state, pwa_state


def _empty_result(*, scenario_id: str, scenario_sha256: str, reason_code: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "scenario_id": scenario_id,
        "scenario_sha256": scenario_sha256,
        "state": "BLOCKED",
        "reason_codes": [reason_code],
        "steps": [],
        "warning_event_summary": {"issue": 0, "update": 0, "cancel": 0, "expire": 0},
        "privacy": {
            "synthetic_coordinates_used": True,
            "coordinates_exposed": False,
            "geometry_exposed": False,
            "credentials_exposed": False,
            "raw_payload_exposed": False,
        },
        "network_access_performed": False,
        "runtime_mutation_performed": False,
        "live_authority_granted": False,
    }


def replay_scenario(scenario: dict[str, Any], *, index_html: str | None = None) -> dict[str, Any]:
    """Replay synthetic DWD warning/radar evidence without network or runtime mutation.

    Coordinates and warning geometry are accepted only as injected validation input. They are
    intentionally omitted from the returned evidence.
    """

    if not isinstance(scenario, dict):
        return _empty_result(scenario_id="invalid", scenario_sha256=_canonical_sha256(None), reason_code="REPLAY_INPUT_INVALID")
    scenario_sha256 = _canonical_sha256(scenario)
    scenario_id_raw = scenario.get("scenario_id")
    if not isinstance(scenario_id_raw, str) or not _SAFE_ID.fullmatch(scenario_id_raw):
        return _empty_result(scenario_id="invalid", scenario_sha256=scenario_sha256, reason_code="REPLAY_SCENARIO_ID_INVALID")
    scenario_id = scenario_id_raw
    location = scenario.get("location")
    map_bounds = scenario.get("map_bounds")
    steps = scenario.get("steps")
    if not isinstance(steps, list) or not steps:
        return _empty_result(scenario_id=scenario_id, scenario_sha256=scenario_sha256, reason_code="REPLAY_STEPS_MISSING")

    warning_state: dict[str, dict[str, Any]] = {}
    radar_frames: list[dict[str, Any]] = []
    event_summary = {"issue": 0, "update": 0, "cancel": 0, "expire": 0}
    outputs: list[dict[str, Any]] = []
    all_reason_codes: set[str] = set()
    last_time: datetime | None = None

    for index, raw_step in enumerate(steps):
        replay_blocked: set[str] = set()
        if not isinstance(raw_step, dict):
            outputs.append(
                {
                    "step": index,
                    "at": None,
                    "state": "BLOCKED",
                    "reason_codes": ["REPLAY_STEP_INVALID"],
                    "blocking_reason_codes": ["REPLAY_STEP_INVALID"],
                    "warning_reason_codes": [],
                }
            )
            all_reason_codes.add("REPLAY_STEP_INVALID")
            continue
        try:
            now = _parse_time(raw_step.get("at"))
        except ReplayError:
            outputs.append(
                {
                    "step": index,
                    "at": None,
                    "state": "BLOCKED",
                    "reason_codes": ["REPLAY_STEP_TIME_INVALID"],
                    "blocking_reason_codes": ["REPLAY_STEP_TIME_INVALID"],
                    "warning_reason_codes": [],
                }
            )
            all_reason_codes.add("REPLAY_STEP_TIME_INVALID")
            continue
        if last_time is not None and now <= last_time:
            replay_blocked.add("REPLAY_STEP_TIME_NOT_INCREASING")
        else:
            last_time = now

        raw_events = raw_step.get("warning_events", [])
        if not isinstance(raw_events, list):
            replay_blocked.add("REPLAY_WARNING_EVENTS_INVALID")
            raw_events = []

        if not replay_blocked:
            for event in raw_events:
                if not isinstance(event, dict):
                    replay_blocked.add("REPLAY_WARNING_EVENT_INVALID")
                    continue
                action = event.get("action")
                if action not in event_summary:
                    replay_blocked.add("REPLAY_WARNING_ACTION_INVALID")
                    continue
                event_summary[action] += 1
                if action == "issue":
                    warning = deepcopy(event.get("warning"))
                    identifier = _warning_id(warning)
                    if identifier is None:
                        replay_blocked.add("REPLAY_WARNING_ID_INVALID")
                    elif identifier in warning_state:
                        replay_blocked.add("REPLAY_WARNING_DUPLICATE_ISSUE")
                    elif isinstance(warning, dict):
                        warning.pop("lifecycle", None)
                        warning_state[identifier] = warning
                elif action == "update":
                    identifier = event.get("id")
                    changes = event.get("changes")
                    if not isinstance(identifier, str) or not _SAFE_ID.fullmatch(identifier):
                        replay_blocked.add("REPLAY_WARNING_ID_INVALID")
                    elif identifier not in warning_state:
                        replay_blocked.add("REPLAY_WARNING_UPDATE_MISSING_BASE")
                    elif not isinstance(changes, dict):
                        replay_blocked.add("REPLAY_WARNING_UPDATE_INVALID")
                    else:
                        updated = deepcopy(warning_state[identifier])
                        updated.update(deepcopy(changes))
                        updated["identifier"] = identifier
                        updated.pop("id", None)
                        updated.pop("lifecycle", None)
                        updated.setdefault("updated", _utc_iso(now))
                        warning_state[identifier] = updated
                elif action == "cancel":
                    identifier = event.get("id")
                    if not isinstance(identifier, str) or not _SAFE_ID.fullmatch(identifier):
                        replay_blocked.add("REPLAY_WARNING_ID_INVALID")
                    elif identifier not in warning_state:
                        replay_blocked.add("REPLAY_WARNING_CANCEL_MISSING_BASE")
                    else:
                        del warning_state[identifier]
                elif action == "expire":
                    identifier = event.get("id")
                    if not isinstance(identifier, str) or not _SAFE_ID.fullmatch(identifier):
                        replay_blocked.add("REPLAY_WARNING_ID_INVALID")
                    elif identifier not in warning_state:
                        replay_blocked.add("REPLAY_WARNING_EXPIRE_MISSING_BASE")
                    else:
                        expired = deepcopy(warning_state[identifier])
                        expired["expires"] = _utc_iso(now)
                        expired["updated"] = _utc_iso(now)
                        expired.pop("lifecycle", None)
                        warning_state[identifier] = expired

            if "radar_frames" in raw_step:
                candidate_frames = raw_step.get("radar_frames")
                if not isinstance(candidate_frames, list) or not all(isinstance(item, dict) for item in candidate_frames):
                    replay_blocked.add("REPLAY_RADAR_FRAMES_INVALID")
                else:
                    radar_frames = deepcopy(candidate_frames)

        evidence = {
            "location": deepcopy(location),
            "map_bounds": deepcopy(map_bounds),
            "warnings": {
                "authority": "DWD",
                "official": True,
                "kind": "official_warning",
                "alerts": [deepcopy(warning_state[key]) for key in sorted(warning_state)],
            },
            "radar": {
                "not_model_forecast": True,
                "frames": deepcopy(radar_frames),
            },
        }
        validation = validate_map_evidence(evidence, now=now, index_html=index_html)
        blocking = set(validation["blocking_reason_codes"]) | replay_blocked
        warning_codes = set(validation["warning_reason_codes"])
        step_state = "BLOCKED" if blocking else "WARN" if warning_codes else "PASS"
        reason_codes = sorted(blocking | warning_codes)
        all_reason_codes.update(reason_codes)
        projected = dict(validation)
        projected["state"] = step_state
        projected["blocking_reason_codes"] = sorted(blocking)
        projected["warning_reason_codes"] = sorted(warning_codes)
        projected["reason_codes"] = reason_codes
        api_state, pwa_state = _step_surface_state(projected)
        outputs.append(
            {
                "step": index,
                "at": _utc_iso(now),
                "state": step_state,
                "reason_codes": reason_codes,
                "blocking_reason_codes": sorted(blocking),
                "warning_reason_codes": sorted(warning_codes),
                "warning_summary": projected["warning_summary"],
                "radar_summary": projected["radar_summary"],
                "api_state": api_state,
                "pwa_state": pwa_state,
                "presentation": projected["presentation"],
            }
        )

    result = {
        "contract_version": CONTRACT_VERSION,
        "scenario_id": scenario_id,
        "scenario_sha256": scenario_sha256,
        "state": _combine_state([step["state"] for step in outputs]),
        "reason_codes": sorted(all_reason_codes),
        "steps": outputs,
        "warning_event_summary": event_summary,
        "privacy": {
            "synthetic_coordinates_used": True,
            "coordinates_exposed": False,
            "geometry_exposed": False,
            "credentials_exposed": False,
            "raw_payload_exposed": False,
        },
        "network_access_performed": False,
        "runtime_mutation_performed": False,
        "live_authority_granted": False,
    }
    return result


def main(argv: list[str] | None = None, input_stream: TextIO | None = None, output_stream: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rozkalns_weather.dwd_replay")
    parser.parse_args(argv)
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    try:
        payload = json.load(input_stream)
    except (json.JSONDecodeError, TypeError, ValueError):
        payload = None
    result = replay_scenario(payload) if isinstance(payload, dict) else _empty_result(
        scenario_id="invalid", scenario_sha256=_canonical_sha256(None), reason_code="REPLAY_INPUT_INVALID"
    )
    print(json.dumps(result, sort_keys=True, indent=2), file=output_stream)
    return 2 if result["state"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
