from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Mapping, Sequence

SCHEMA_VERSION = 1
CONTRACT = "post-rollout-acceptance-v1"
TARGET_ALIAS = "rozkalns-weather-public-rpi5"
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,159}$")
PUBLIC_PROVIDERS = (
    "dwd_mosmix_l",
    "dwd_observations",
    "icon_d2",
    "ecmwf_ifs",
    "ecmwf_aifs",
)
DEGRADED_PROVIDER_STATES = frozenset(
    {"lagging", "degraded", "stale", "error", "unknown", "not_ingested"}
)
FORBIDDEN_KEYS = frozenset(
    {
        "home_lat",
        "home_lon",
        "credentials",
        "credential",
        "token",
        "secret",
        "raw_logs",
        "raw_log",
        "database_path",
        "host_path",
        "env",
        "environment",
    }
)
PRIVATE_PATH_PREFIXES = ("/home/", "/opt/", "/root/", "/etc/")


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _scan_privacy(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_KEYS or normalized.endswith("_path"):
                raise ValueError(f"acceptance evidence contains forbidden private field: {key}")
            _scan_privacy(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _scan_privacy(child)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in PRIVATE_PATH_PREFIXES):
            raise ValueError("acceptance evidence contains a private host path")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} evidence missing or malformed")
    return value


def _provider_map(value: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError("provider freshness evidence missing or malformed")
    result: dict[str, Mapping[str, object]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("provider freshness evidence item malformed")
        provider_id = str(item.get("id", "")).strip()
        if not provider_id:
            raise ValueError("provider freshness evidence item missing id")
        if provider_id in result:
            raise ValueError(f"duplicate provider freshness evidence: {provider_id}")
        result[provider_id] = item
    return result


def evaluate_post_rollout_acceptance(
    evidence: Mapping[str, object],
    *,
    expected_source_sha: str,
    expected_release_identity: str,
) -> dict[str, object]:
    """Evaluate sanitized post-rollout evidence without mutating runtime or data."""

    if not SOURCE_SHA_RE.fullmatch(expected_source_sha):
        raise ValueError("expected source SHA must be an exact lowercase 40-character commit SHA")
    if not RELEASE_ID_RE.fullmatch(expected_release_identity):
        raise ValueError("expected release identity is invalid")
    _scan_privacy(evidence)

    blockers: list[str] = []
    warnings: list[str] = []
    application_reasons: list[str] = []
    corpus_reasons: list[str] = []

    if evidence.get("source_sha") != expected_source_sha:
        blockers.append("SOURCE_SHA_MISMATCH")
        application_reasons.append("SOURCE_SHA_MISMATCH")
    if evidence.get("release_identity") != expected_release_identity:
        blockers.append("RELEASE_IDENTITY_MISMATCH")
        application_reasons.append("RELEASE_IDENTITY_MISMATCH")
    if evidence.get("target_alias") != TARGET_ALIAS:
        blockers.append("TARGET_ALIAS_MISMATCH")
        application_reasons.append("TARGET_ALIAS_MISMATCH")

    endpoints = _mapping(evidence.get("endpoints"), "endpoint")
    endpoint_contract = {
        "health_status": "HEALTH_ENDPOINT_FAILED",
        "ready_status": "READY_ENDPOINT_FAILED",
        "provider_health_status": "PROVIDER_HEALTH_ENDPOINT_FAILED",
        "api_current_status": "PUBLIC_API_REACHABILITY_FAILED",
        "pwa_status": "PWA_REACHABILITY_FAILED",
    }
    for key, reason in endpoint_contract.items():
        if endpoints.get(key) != 200:
            blockers.append(reason)
            application_reasons.append(reason)

    readiness = _mapping(evidence.get("readiness"), "readiness")
    if readiness.get("ready") is not True:
        blockers.append("RUNTIME_NOT_READY")
        application_reasons.append("RUNTIME_NOT_READY")
    if readiness.get("runtime_mode") != "public-only":
        blockers.append("RUNTIME_MODE_MISMATCH")
        application_reasons.append("RUNTIME_MODE_MISMATCH")

    schema = _mapping(evidence.get("schema"), "schema")
    if schema.get("state") != "ready":
        blockers.append("SCHEMA_NOT_READY")
    if schema.get("implicit_migration_performed") is not False:
        blockers.append("SCHEMA_IMPLICIT_MIGRATION_DETECTED")

    storage = _mapping(evidence.get("storage"), "storage")
    if storage.get("state") != "ready":
        blockers.append("STORAGE_NOT_READY")
    if storage.get("persistent") is not True:
        blockers.append("PERSISTENT_STORAGE_NOT_PROVEN")

    corpus = _mapping(evidence.get("corpus_integrity"), "corpus integrity")
    if corpus.get("ok") is not True:
        blockers.append("CORPUS_INTEGRITY_FAILED")
        corpus_reasons.append("CORPUS_INTEGRITY_FAILED")
    if corpus.get("regression_detected") is True:
        blockers.append("CORPUS_REGRESSION_DETECTED")
        corpus_reasons.append("CORPUS_REGRESSION_DETECTED")

    providers = _provider_map(evidence.get("providers"))
    missing = [provider for provider in PUBLIC_PROVIDERS if provider not in providers]
    if missing:
        blockers.append("PUBLIC_PROVIDER_EVIDENCE_MISSING")
    provider_summary: list[dict[str, object]] = []
    for provider in PUBLIC_PROVIDERS:
        item = providers.get(provider)
        if item is None:
            continue
        freshness_state = str(item.get("freshness_state", "")).strip()
        reason_code = str(item.get("reason_code", "")).strip()
        if not freshness_state or not reason_code:
            blockers.append(f"{provider.upper()}_PROVIDER_EVIDENCE_INCOMPLETE")
        elif freshness_state != "fresh":
            warnings.append(f"{provider.upper()}_PROVIDER_{freshness_state.upper()}")
        provider_summary.append(
            {
                "id": provider,
                "freshness_state": freshness_state,
                "reason_code": reason_code,
            }
        )

    weathernext = providers.get("weathernext3")
    if weathernext is not None:
        if weathernext.get("required_for_runtime") is not False:
            blockers.append("WEATHERNEXT_PUBLIC_RUNTIME_AUTHORITY_DRIFT")
        if weathernext.get("values_fabricated") is not False:
            blockers.append("WEATHERNEXT_VALUES_FABRICATED")

    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    application_reasons = _dedupe(application_reasons)
    corpus_reasons = _dedupe(corpus_reasons)
    state = "BLOCKED" if blockers else "WARN" if warnings else "PASS"

    return {
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "state": state,
        "source_sha": expected_source_sha,
        "release_identity": expected_release_identity,
        "target_alias": TARGET_ALIAS,
        "block_reasons": blockers,
        "warn_reasons": warnings,
        "providers": provider_summary,
        "rollback_decision_inputs": {
            "application": {
                "candidate": bool(application_reasons),
                "reasons": application_reasons,
                "automatic_rollback_allowed": False,
                "retry_restart_or_rollback_requires_fresh_exact_live_authorization": True,
            },
            "production_corpus": {
                "candidate": bool(corpus_reasons),
                "reasons": corpus_reasons,
                "automatic_restore_allowed": False,
                "automatic_delete_allowed": False,
                "application_rollback_implies_corpus_rollback": False,
                "restore_or_delete_requires_separate_exact_live_data_authorization": True,
            },
        },
        "authority": {
            "live_authority_granted": False,
            "production_data_authority_granted": False,
            "retry_authority_granted": False,
            "rollback_authority_granted": False,
        },
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "private_paths_exposed": False,
            "raw_logs_exposed": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m rozkalns_weather.post_rollout_acceptance"
    )
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--release-identity", required=True)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("acceptance evidence must be a JSON object")
        result = evaluate_post_rollout_acceptance(
            payload,
            expected_source_sha=args.source_sha,
            expected_release_identity=args.release_identity,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "contract": CONTRACT,
                    "state": "BLOCKED",
                    "block_reasons": ["MALFORMED_OR_PRIVATE_EVIDENCE"],
                    "error": str(exc),
                    "authority": {
                        "live_authority_granted": False,
                        "production_data_authority_granted": False,
                        "retry_authority_granted": False,
                        "rollback_authority_granted": False,
                    },
                },
                sort_keys=True,
            )
        )
        raise SystemExit(3)
    print(json.dumps(result, sort_keys=True))
    if result["state"] == "BLOCKED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
