from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import sys
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
CONTRACT_ID = "weather-release-readiness-matrix.v1"

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REASON = re.compile(r"^[A-Z0-9][A-Z0-9_:-]{0,159}$")
_EVIDENCE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:#@+-]{0,199}$")

VALID_STATES = frozenset({"PASS", "WARN", "BLOCKED"})
MAX_FUTURE_SKEW_SECONDS = 300
MIN_EVIDENCE_TTL_SECONDS = 60
MAX_EVIDENCE_TTL_SECONDS = 604_800

_PRIVATE_KEYS = frozenset(
    {
        "home_lat",
        "home_lon",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "credentials",
        "credential",
        "token",
        "secret",
        "service_account",
        "project_id",
        "dataset_id",
        "google_cloud_project",
        "weathernext_bigquery_dataset",
        "database_path",
        "filesystem_path",
        "host_path",
        "raw_log",
        "raw_logs",
        "environment",
        "env",
        "sql",
        "query_sql",
    }
)
_PRIVATE_PATH_MARKERS = ("/home/", "/opt/", "/root/", "/etc/")

_CAPABILITY_KEYS = frozenset(
    {
        "id",
        "state",
        "source_sha",
        "evidence_ref",
        "checked_at_utc",
        "max_age_seconds",
        "block_reasons",
        "warn_reasons",
        "invariants",
    }
)

CAPABILITY_SPECS: dict[str, dict[str, object]] = {
    "source_contracts": {
        "track": "public_release",
        "dependencies": (),
        "invariants": {
            "privacy_safe": True,
            "immutable_provenance_preserved": True,
        },
    },
    "public_runtime": {
        "track": "public_release",
        "dependencies": ("source_contracts",),
        "invariants": {
            "privacy_safe": True,
            "runtime_mode": "public-only",
            "private_runtime_required": False,
            "live_authority_granted": False,
        },
    },
    "public_corpus": {
        "track": "public_release",
        "dependencies": ("source_contracts",),
        "invariants": {
            "privacy_safe": True,
            "immutable_history_preserved": True,
            "production_data_authority_granted": False,
        },
    },
    "provider_health": {
        "track": "public_release",
        "dependencies": ("source_contracts", "public_corpus"),
        "invariants": {
            "privacy_safe": True,
            "provider_level_provenance_preserved": True,
        },
    },
    "verification": {
        "track": "public_release",
        "dependencies": ("public_corpus", "provider_health"),
        "invariants": {
            "privacy_safe": True,
            "measured_truth_location_id": "station_10416",
            "private_home_measured_accuracy_claimed": False,
        },
    },
    "reporting_exports": {
        "track": "public_release",
        "dependencies": ("verification",),
        "invariants": {
            "privacy_safe": True,
            "reproducible": True,
            "source_sha_bound": True,
        },
    },
    "pwa": {
        "track": "public_release",
        "dependencies": ("public_runtime", "provider_health"),
        "invariants": {
            "privacy_safe": True,
            "private_fields_exposed": False,
            "public_private_state_separated": True,
        },
    },
    "dwd_safety_radar": {
        "track": "public_release",
        "dependencies": ("source_contracts", "public_runtime"),
        "invariants": {
            "privacy_safe": True,
            "official_warning_authority": "DWD",
            "model_warning_substitution": False,
            "radar_separate_from_model_forecast": True,
        },
    },
    "weathernext_research": {
        "track": "weathernext_research",
        "dependencies": ("source_contracts",),
        "invariants": {
            "privacy_safe": True,
            "primary_research_model": True,
            "values_fabricated": False,
            "official_warning_authority": "DWD",
        },
    },
    "private_home_runtime": {
        "track": "private_activation",
        "dependencies": ("public_corpus", "weathernext_research"),
        "invariants": {
            "privacy_safe": True,
            "exact_coordinates_exposed": False,
            "measured_home_accuracy_claimed": False,
            "official_warning_authority": "DWD",
            "activation_authority_granted": False,
        },
    },
    "production_data_write": {
        "track": "production_data_write",
        "dependencies": ("source_contracts", "public_corpus"),
        "invariants": {
            "privacy_safe": True,
            "authority_granted": False,
            "mutation_performed": False,
        },
    },
}

TRACK_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "public_release": tuple(
        capability_id
        for capability_id, spec in CAPABILITY_SPECS.items()
        if spec["track"] == "public_release"
    ),
    "weathernext_research": ("weathernext_research",),
    "private_activation": ("private_home_runtime",),
    "production_data_write": ("production_data_write",),
}


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], *, path: str) -> None:
    observed = frozenset(str(key) for key in value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(f"{path} schema mismatch: missing={missing} extra={extra}")


def _mapping(value: object, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return value


def _utc(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 UTC timestamp") from exc
    return parsed.astimezone(timezone.utc)


def _scan_private(value: object, *, path: str = "") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower()
            child_path = f"{path}.{key}" if path else key
            if key in _PRIVATE_KEYS:
                raise ValueError(f"private evidence field forbidden: {child_path}")
            _scan_private(child, path=child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_private(child, path=f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _PRIVATE_PATH_MARKERS):
            raise ValueError(f"private host path forbidden at {path or 'value'}")


def _reason_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _REASON.fullmatch(item):
            raise ValueError(f"{field} contains invalid reason code")
        if item not in result:
            result.append(item)
    return result


def _aggregate_state(states: Sequence[str]) -> str:
    if any(state == "BLOCKED" for state in states):
        return "BLOCKED"
    if any(state == "WARN" for state in states):
        return "WARN"
    return "PASS"


def _effective_capability(
    item: Mapping[str, Any],
    *,
    matrix_source_sha: str,
    matrix_checked_at: datetime,
    prior: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    _exact_keys(item, _CAPABILITY_KEYS, path="capability")
    capability_id = item.get("id")
    if not isinstance(capability_id, str) or capability_id not in CAPABILITY_SPECS:
        raise ValueError("capability.id is unknown")
    spec = CAPABILITY_SPECS[capability_id]

    input_state = item.get("state")
    if input_state not in VALID_STATES:
        raise ValueError(f"{capability_id}.state must be PASS, WARN, or BLOCKED")
    block_reasons = _reason_list(
        item.get("block_reasons"), field=f"{capability_id}.block_reasons"
    )
    warn_reasons = _reason_list(
        item.get("warn_reasons"), field=f"{capability_id}.warn_reasons"
    )
    if input_state == "PASS" and (block_reasons or warn_reasons):
        raise ValueError(f"{capability_id} PASS contradicts supplied reasons")
    if input_state == "WARN" and (block_reasons or not warn_reasons):
        raise ValueError(f"{capability_id} WARN requires warn reasons only")
    if input_state == "BLOCKED" and not block_reasons:
        raise ValueError(f"{capability_id} BLOCKED requires block reasons")

    source_sha = item.get("source_sha")
    if not isinstance(source_sha, str) or not _SHA40.fullmatch(source_sha):
        raise ValueError(
            f"{capability_id}.source_sha must be a lowercase 40-character git SHA"
        )
    if source_sha != matrix_source_sha:
        block_reasons.append("SOURCE_SHA_MISMATCH")

    evidence_ref = item.get("evidence_ref")
    if not isinstance(evidence_ref, str) or not _EVIDENCE_REF.fullmatch(evidence_ref):
        raise ValueError(f"{capability_id}.evidence_ref is invalid")

    checked_at = _utc(item.get("checked_at_utc"), field=f"{capability_id}.checked_at_utc")
    ttl = item.get("max_age_seconds")
    if (
        type(ttl) is not int
        or ttl < MIN_EVIDENCE_TTL_SECONDS
        or ttl > MAX_EVIDENCE_TTL_SECONDS
    ):
        raise ValueError(
            f"{capability_id}.max_age_seconds must be between "
            f"{MIN_EVIDENCE_TTL_SECONDS} and {MAX_EVIDENCE_TTL_SECONDS}"
        )
    if checked_at > matrix_checked_at + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        block_reasons.append("EVIDENCE_FROM_FUTURE")
    elif matrix_checked_at - checked_at > timedelta(seconds=ttl):
        block_reasons.append("STALE_EVIDENCE")

    invariants = _mapping(item.get("invariants"), path=f"{capability_id}.invariants")
    expected_invariants = spec["invariants"]
    assert isinstance(expected_invariants, dict)
    _exact_keys(
        invariants,
        frozenset(expected_invariants),
        path=f"{capability_id}.invariants",
    )
    for key, expected in expected_invariants.items():
        if invariants.get(key) != expected:
            block_reasons.append(f"INVARIANT_{key.upper()}")

    for dependency_id in spec["dependencies"]:
        dependency = prior.get(str(dependency_id))
        if dependency is None:
            block_reasons.append(f"DEPENDENCY_MISSING:{str(dependency_id).upper()}")
            continue
        dependency_state = dependency["state"]
        if dependency_state == "BLOCKED":
            block_reasons.append(f"DEPENDENCY_BLOCKED:{str(dependency_id).upper()}")
        elif dependency_state == "WARN":
            warn_reasons.append(f"DEPENDENCY_WARN:{str(dependency_id).upper()}")

    block_reasons = list(dict.fromkeys(block_reasons))
    warn_reasons = list(dict.fromkeys(warn_reasons))
    effective_state = (
        "BLOCKED"
        if block_reasons
        else "WARN"
        if input_state == "WARN" or warn_reasons
        else "PASS"
    )
    return {
        "id": capability_id,
        "track": spec["track"],
        "state": effective_state,
        "evidence_ref": evidence_ref,
        "block_reasons": block_reasons,
        "warn_reasons": warn_reasons,
    }


def _missing_capability(capability_id: str) -> dict[str, object]:
    spec = CAPABILITY_SPECS[capability_id]
    return {
        "id": capability_id,
        "track": spec["track"],
        "state": "BLOCKED",
        "evidence_ref": None,
        "block_reasons": ["CAPABILITY_EVIDENCE_MISSING"],
        "warn_reasons": [],
    }


def evaluate_release_readiness_matrix(evidence: Mapping[str, Any]) -> dict[str, object]:
    """Aggregate sanitized capability evidence without granting any LIVE authority."""

    _scan_private(evidence)
    expected_top = frozenset(
        {"schema_version", "source_sha", "checked_at_utc", "capabilities"}
    )
    _exact_keys(evidence, expected_top, path="evidence")
    if evidence.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must equal {SCHEMA_VERSION}")

    source_sha = evidence.get("source_sha")
    if not isinstance(source_sha, str) or not _SHA40.fullmatch(source_sha):
        raise ValueError("source_sha must be a lowercase 40-character git SHA")
    checked_at = _utc(evidence.get("checked_at_utc"), field="checked_at_utc")

    raw_capabilities = evidence.get("capabilities")
    if not isinstance(raw_capabilities, list):
        raise ValueError("capabilities must be a list")

    supplied: dict[str, Mapping[str, Any]] = {}
    for raw_item in raw_capabilities:
        item = _mapping(raw_item, path="capability")
        capability_id = item.get("id")
        if not isinstance(capability_id, str) or capability_id not in CAPABILITY_SPECS:
            raise ValueError("capability.id is unknown")
        if capability_id in supplied:
            raise ValueError(f"duplicate capability evidence: {capability_id}")
        supplied[capability_id] = item

    effective: dict[str, dict[str, object]] = {}
    for capability_id in CAPABILITY_SPECS:
        item = supplied.get(capability_id)
        if item is None:
            effective[capability_id] = _missing_capability(capability_id)
            continue
        effective[capability_id] = _effective_capability(
            item,
            matrix_source_sha=source_sha,
            matrix_checked_at=checked_at,
            prior=effective,
        )

    tracks: dict[str, dict[str, object]] = {}
    for track_id, capability_ids in TRACK_CAPABILITIES.items():
        rows = [effective[capability_id] for capability_id in capability_ids]
        state = _aggregate_state([str(row["state"]) for row in rows])
        tracks[track_id] = {
            "state": state,
            "capabilities": list(capability_ids),
            "blocked_capabilities": [
                str(row["id"]) for row in rows if row["state"] == "BLOCKED"
            ],
            "warn_capabilities": [
                str(row["id"]) for row in rows if row["state"] == "WARN"
            ],
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT_ID,
        "source_sha": source_sha,
        "checked_at_utc": evidence["checked_at_utc"],
        "capabilities": list(effective.values()),
        "tracks": tracks,
        "handoff_summary": {
            "public_release": tracks["public_release"]["state"],
            "weathernext_research": tracks["weathernext_research"]["state"],
            "private_activation": tracks["private_activation"]["state"],
            "production_data_write": tracks["production_data_write"]["state"],
            "public_blocked_capabilities": tracks["public_release"][
                "blocked_capabilities"
            ],
            "public_warn_capabilities": tracks["public_release"]["warn_capabilities"],
        },
        "authority_boundary": {
            "grants_merge_authority": False,
            "grants_live_authority": False,
            "grants_production_data_authority": False,
            "grants_credential_or_secret_authority": False,
            "grants_cloudflare_or_network_authority": False,
        },
        "privacy": {
            "private_coordinates_in_output": False,
            "credential_material_in_output": False,
            "private_paths_in_output": False,
            "raw_provider_payloads_in_output": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m rozkalns_weather.release_readiness"
    )
    parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("release-readiness evidence must be a JSON object")
        result = evaluate_release_readiness_matrix(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "contract": CONTRACT_ID,
                    "state": "BLOCKED",
                    "block_reasons": ["MALFORMED_OR_PRIVATE_EVIDENCE"],
                    "error": str(exc),
                    "authority_boundary": {
                        "grants_merge_authority": False,
                        "grants_live_authority": False,
                        "grants_production_data_authority": False,
                        "grants_credential_or_secret_authority": False,
                        "grants_cloudflare_or_network_authority": False,
                    },
                },
                sort_keys=True,
            )
        )
        raise SystemExit(3)
    print(json.dumps(result, sort_keys=True))
    if result["tracks"]["public_release"]["state"] == "BLOCKED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
