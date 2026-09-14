from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
import re
from typing import Any

from .config import Settings
from .db import Database
from .provider_health import PUBLIC_PROVIDER_HEALTH_POLICIES, classify_public_provider_health
from .runtime import readiness_payload
from .runtime_config import validate_runtime_config

INCIDENT_DIAGNOSTICS_SCHEMA = "incident-diagnostics-v1"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

INCIDENT_DIAGNOSTICS_CONTRACT: dict[str, Any] = {
    "schema": INCIDENT_DIAGNOSTICS_SCHEMA,
    "schema_version": 1,
    "states": ["PASS", "WARN", "BLOCKED", "ERROR"],
    "required_sections": [
        "source_sha",
        "app",
        "config",
        "database",
        "providers",
        "corpus",
        "privacy",
        "authority",
    ],
    "incident_classes": [
        "configuration_readiness",
        "database_schema",
        "application_readiness",
        "corpus_integrity",
        "provider_upstream",
        "provider_local_ingest",
        "provider_stale_data",
        "provider_not_ingested",
        "provider_evidence_unknown",
        "evidence_corruption",
        "privacy_rejection",
    ],
    "reason_codes": [
        "SOURCE_SHA_INVALID",
        "DIAGNOSTICS_EVIDENCE_CORRUPT",
        "PRIVATE_COORDINATE_EVIDENCE_REJECTED",
        "CREDENTIAL_EVIDENCE_REJECTED",
        "PRIVATE_PATH_EVIDENCE_REJECTED",
        "RAW_LOG_OR_DETAIL_EVIDENCE_REJECTED",
        "PRIVATE_PAYLOAD_EVIDENCE_REJECTED",
        "CONFIG_READINESS_FAILURE",
        "CONFIG_READINESS_WARNING",
        "DATABASE_SCHEMA_MISMATCH",
        "APPLICATION_NOT_READY",
        "CORPUS_INTEGRITY_FAILURE",
        "PROVIDER_UPSTREAM_OUTAGE",
        "PROVIDER_LOCAL_INGEST_FAILURE",
        "PROVIDER_STALE_DATA",
        "PROVIDER_NOT_INGESTED",
        "PROVIDER_EVIDENCE_UNKNOWN",
    ],
    "privacy": {
        "exact_home_coordinates_allowed": False,
        "credentials_or_tokens_allowed": False,
        "private_filesystem_paths_allowed": False,
        "raw_logs_or_details_allowed": False,
        "private_payloads_allowed": False,
        "sensitive_values_echoed_on_failure": False,
    },
    "authority": {
        "read_only": True,
        "live_authority_granted": False,
        "production_data_authority_granted": False,
        "automatic_recovery_authority_granted": False,
    },
}

_COORDINATE_KEYS = {"home_lat", "home_lon", "latitude", "longitude"}
_CREDENTIAL_KEYS = {
    "credential",
    "credentials",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "authorization",
}
_PRIVATE_PATH_KEYS = {"database_path", "db_path", "filesystem_path", "private_path", "host_path"}
_RAW_DETAIL_KEYS = {"raw_log", "raw_logs", "log", "logs", "detail", "traceback", "stacktrace"}
_PRIVATE_PAYLOAD_KEYS = {"private_payload", "private_payloads", "raw_payload", "raw_payloads"}
_PRIVATE_PATH_RE = re.compile(r"(?i)(?:^|[\s\"'=])/(?:home|root|srv|etc|var/lib|opt|mnt|media)/")
_CREDENTIAL_VALUE_RE = re.compile(
    r"(?i)(?:authorization\s*:\s*bearer|bearer\s+[a-z0-9._-]{12,}|(?:token|password|api[_-]?key|secret)=)"
)
_PROVIDER_SAFE_FIELDS = (
    "ingest_state",
    "freshness_state",
    "failure_domain",
    "reason_code",
    "last_attempt_at_utc",
    "last_success_at_utc",
    "last_init_time_utc",
    "last_retrieved_at_utc",
    "latest_valid_time_utc",
    "last_observed_at_utc",
    "attempt_age_hours",
    "success_age_hours",
    "source_age_hours",
)


def _meaningful(value: object) -> bool:
    return value not in (None, "", [], {}, ())


def _privacy_reasons(value: object, *, key: str | None = None) -> set[str]:
    reasons: set[str] = set()
    normalized_key = key.lower() if isinstance(key, str) else None

    if normalized_key in _COORDINATE_KEYS and _meaningful(value):
        reasons.add("PRIVATE_COORDINATE_EVIDENCE_REJECTED")
    if normalized_key in _CREDENTIAL_KEYS and _meaningful(value):
        reasons.add("CREDENTIAL_EVIDENCE_REJECTED")
    if normalized_key in _PRIVATE_PATH_KEYS and _meaningful(value):
        reasons.add("PRIVATE_PATH_EVIDENCE_REJECTED")
    if normalized_key in _RAW_DETAIL_KEYS and _meaningful(value):
        reasons.add("RAW_LOG_OR_DETAIL_EVIDENCE_REJECTED")
    if normalized_key in _PRIVATE_PAYLOAD_KEYS and _meaningful(value):
        reasons.add("PRIVATE_PAYLOAD_EVIDENCE_REJECTED")

    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            reasons.update(_privacy_reasons(child_value, key=str(child_key)))
    elif isinstance(value, (list, tuple)):
        for item in value:
            reasons.update(_privacy_reasons(item))
    elif isinstance(value, str):
        if value.startswith("sqlite:///") or _PRIVATE_PATH_RE.search(value):
            reasons.add("PRIVATE_PATH_EVIDENCE_REJECTED")
        if _CREDENTIAL_VALUE_RE.search(value):
            reasons.add("CREDENTIAL_EVIDENCE_REJECTED")
    return reasons


def _provider_incident(health: Mapping[str, object]) -> tuple[str, str] | None:
    freshness = str(health.get("freshness_state") or "unknown")
    domain = str(health.get("failure_domain") or "unknown")
    reason = str(health.get("reason_code") or "")

    if freshness == "fresh":
        return None
    if freshness == "not_ingested" or reason == "NO_INGEST_ATTEMPT":
        return ("PROVIDER_NOT_INGESTED", "provider_not_ingested")
    if freshness in {"stale", "lagging"} and domain == "upstream_data":
        return ("PROVIDER_STALE_DATA", "provider_stale_data")
    if domain in {"upstream_or_transport", "upstream_data"}:
        return ("PROVIDER_UPSTREAM_OUTAGE", "provider_upstream")
    if domain in {"local_persistence", "local_scheduler_or_ingest", "local_ingest", "local_ingest_not_started"}:
        return ("PROVIDER_LOCAL_INGEST_FAILURE", "provider_local_ingest")
    if freshness in {"stale", "lagging"}:
        return ("PROVIDER_STALE_DATA", "provider_stale_data")
    return ("PROVIDER_EVIDENCE_UNKNOWN", "provider_evidence_unknown")


def _safe_provider_input(health: Mapping[str, object]) -> dict[str, object]:
    return {field: health.get(field) for field in _PROVIDER_SAFE_FIELDS}


def _sanitize_provider(provider: str, health: Mapping[str, object]) -> dict[str, object]:
    return {"id": provider, **_safe_provider_input(health)}


def build_incident_diagnostics(
    *,
    source_sha: str,
    readiness: Mapping[str, object] | object,
    config: Mapping[str, object] | object,
    provider_health: Mapping[str, Mapping[str, object]] | object,
    corpus_integrity: Mapping[str, object] | object,
) -> dict[str, object]:
    reasons: set[str] = set()
    incident_classes: set[str] = set()
    warnings = False
    blocked = False
    error = False

    readiness_map = readiness if isinstance(readiness, Mapping) else {}
    config_map = config if isinstance(config, Mapping) else {}
    provider_map = provider_health if isinstance(provider_health, Mapping) else {}
    corpus_map = corpus_integrity if isinstance(corpus_integrity, Mapping) else {}
    if len(readiness_map) == 0 or len(config_map) == 0 or not isinstance(provider_health, Mapping) or not isinstance(corpus_integrity, Mapping):
        reasons.add("DIAGNOSTICS_EVIDENCE_CORRUPT")
        incident_classes.add("evidence_corruption")
        error = True

    if not _SOURCE_SHA_RE.fullmatch(source_sha):
        reasons.add("SOURCE_SHA_INVALID")
        incident_classes.add("evidence_corruption")
        error = True

    privacy_reasons: set[str] = set()
    for item in (readiness_map, config_map, provider_map, corpus_map):
        privacy_reasons.update(_privacy_reasons(item))
    if privacy_reasons:
        reasons.update(privacy_reasons)
        incident_classes.add("privacy_rejection")
        error = True

    config_state = str(config_map.get("state") or "ERROR")
    if config_state == "BLOCKED":
        reasons.add("CONFIG_READINESS_FAILURE")
        incident_classes.add("configuration_readiness")
        blocked = True
    elif config_state == "WARN":
        reasons.add("CONFIG_READINESS_WARNING")
        incident_classes.add("configuration_readiness")
        warnings = True
    elif config_state != "PASS":
        reasons.add("DIAGNOSTICS_EVIDENCE_CORRUPT")
        incident_classes.add("evidence_corruption")
        error = True

    database = readiness_map.get("database")
    storage = readiness_map.get("storage")
    if not isinstance(database, Mapping) or not isinstance(storage, Mapping):
        reasons.add("DIAGNOSTICS_EVIDENCE_CORRUPT")
        incident_classes.add("evidence_corruption")
        error = True
        database = {}
        storage = {}

    database_state = str(database.get("state") or "unknown")
    ready = readiness_map.get("ready")
    if config_state != "BLOCKED":
        if database_state != "ready":
            reasons.add("DATABASE_SCHEMA_MISMATCH")
            incident_classes.add("database_schema")
            blocked = True
        if ready is not True:
            reasons.add("APPLICATION_NOT_READY")
            incident_classes.add("application_readiness")
            blocked = True

    corpus_checked = corpus_map.get("checked", True)
    corpus_ok = corpus_map.get("ok")
    if corpus_checked is True and corpus_ok is not True:
        reasons.add("CORPUS_INTEGRITY_FAILURE")
        incident_classes.add("corpus_integrity")
        blocked = True
    elif corpus_checked not in {True, False}:
        reasons.add("DIAGNOSTICS_EVIDENCE_CORRUPT")
        incident_classes.add("evidence_corruption")
        error = True

    sanitized_providers: list[dict[str, object]] = []
    for provider in sorted(provider_map):
        health = provider_map[provider]
        if not isinstance(health, Mapping):
            reasons.add("DIAGNOSTICS_EVIDENCE_CORRUPT")
            incident_classes.add("evidence_corruption")
            error = True
            continue
        sanitized_providers.append(_sanitize_provider(str(provider), health))
        incident = _provider_incident(health)
        if incident is not None:
            reason_code, incident_class = incident
            reasons.add(reason_code)
            incident_classes.add(incident_class)
            warnings = True

    state = "ERROR" if error else "BLOCKED" if blocked else "WARN" if warnings else "PASS"
    config_presence = config_map.get("presence")
    if not isinstance(config_presence, Mapping):
        config_presence = {}

    return {
        "schema": INCIDENT_DIAGNOSTICS_SCHEMA,
        "schema_version": 1,
        "state": state,
        "source_sha": source_sha if _SOURCE_SHA_RE.fullmatch(source_sha) else "invalid",
        "reason_codes": sorted(reasons),
        "incident_classes": sorted(incident_classes),
        "app": {
            "ready": ready is True,
            "status": readiness_map.get("status"),
            "runtime_mode": readiness_map.get("runtime_mode"),
            "database_init_mode": readiness_map.get("database_init_mode"),
        },
        "config": {
            "state": config_state,
            "runtime_mode": config_map.get("runtime_mode"),
            "config_profile": config_map.get("config_profile"),
            "reason_codes": list(config_map.get("reason_codes") or []),
            "warning_codes": list(config_map.get("warning_codes") or []),
            "presence": {
                "database_url": bool(config_presence.get("database_url")),
                "home_coordinates": bool(config_presence.get("home_coordinates")),
                "google_project_and_dataset": bool(config_presence.get("google_project_and_dataset")),
                "google_auth": bool(config_presence.get("google_auth")),
            },
        },
        "database": {
            "schema_state": database_state,
            "required_tables_present": bool(database.get("required_tables_present")),
            "missing_table_count": len(database.get("missing_tables") or []),
            "storage_class": storage.get("class"),
            "persistent": bool(storage.get("persistent")),
            "writable": bool(storage.get("writable")),
        },
        "providers": sanitized_providers,
        "corpus": {
            "checked": corpus_checked is True,
            "ok": corpus_ok is True if corpus_checked is True else None,
            "error_count": int(corpus_map.get("error_count") or 0),
        },
        "privacy": {
            "safe_for_github": not privacy_reasons,
            "rejected_reason_codes": sorted(privacy_reasons),
            "coordinate_values_exposed": False,
            "credential_values_exposed": False,
            "database_path_exposed": False,
            "raw_logs_exposed": False,
            "private_payloads_exposed": False,
        },
        "authority": {
            "read_only": True,
            "live_authority_granted": False,
            "production_data_authority_granted": False,
            "automatic_recovery_authority_granted": False,
        },
    }


def collect_incident_diagnostics(
    *,
    source_sha: str,
    env: Mapping[str, str] | None = None,
    settings: Settings | None = None,
    database: Database | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    source_env = os.environ if env is None else env
    if settings is None:
        try:
            settings = Settings.from_env(dict(source_env))
        except ValueError:
            config = validate_runtime_config(source_env)
            return build_incident_diagnostics(
                source_sha=source_sha,
                readiness={
                    "ready": False,
                    "status": "not_ready",
                    "runtime_mode": config.get("runtime_mode"),
                    "database_init_mode": None,
                    "database": {"state": "not_evaluated", "required_tables_present": False, "missing_tables": []},
                    "storage": {"class": "not_evaluated", "persistent": False, "writable": False},
                },
                config=config,
                provider_health={},
                corpus_integrity={"checked": False, "ok": None, "error_count": 0},
            )

    config = validate_runtime_config(source_env, settings=settings)
    database = database or Database(settings.database_url)
    readiness = readiness_payload(settings, database)
    database_state = readiness.get("database")
    schema_ready = isinstance(database_state, Mapping) and database_state.get("state") == "ready"

    provider_health: dict[str, Mapping[str, object]] = {}
    corpus_integrity: Mapping[str, object] = {"checked": False, "ok": None, "error_count": 0}
    if schema_ready:
        stored = database.provider_statuses()
        freshness = database.provider_freshness_evidence()
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        for provider in PUBLIC_PROVIDER_HEALTH_POLICIES:
            classified = classify_public_provider_health(
                provider,
                stored.get(provider),
                freshness.get(provider),
                now=current,
            )
            provider_health[provider] = _safe_provider_input(classified)
        corpus_integrity = {"checked": True, **database.corpus_integrity()}

    return build_incident_diagnostics(
        source_sha=source_sha,
        readiness=readiness,
        config=config,
        provider_health=provider_health,
        corpus_integrity=corpus_integrity,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m rozkalns_weather.incident_diagnostics",
        description="Emit one privacy-safe, read-only incident diagnostics bundle.",
    )
    parser.add_argument("--source-sha", required=True, help="exact reviewed 40-character weather source SHA")
    args = parser.parse_args()

    payload = collect_incident_diagnostics(source_sha=args.source_sha)
    print(json.dumps(payload, sort_keys=True))
    if payload["state"] == "BLOCKED":
        raise SystemExit(3)
    if payload["state"] == "ERROR":
        raise SystemExit(4)


if __name__ == "__main__":
    main()
