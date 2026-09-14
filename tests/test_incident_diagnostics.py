from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from rozkalns_weather.incident_diagnostics import (
    INCIDENT_DIAGNOSTICS_CONTRACT,
    build_incident_diagnostics,
    collect_incident_diagnostics,
)

SOURCE_SHA = "a" * 40


def _readiness() -> dict[str, object]:
    return {
        "ready": True,
        "status": "ready",
        "runtime_mode": "public-only",
        "database_init_mode": "require-existing",
        "database": {
            "state": "ready",
            "required_tables_present": True,
            "missing_tables": [],
        },
        "storage": {
            "class": "persistent_sqlite_file",
            "persistent": True,
            "writable": True,
        },
    }


def _config() -> dict[str, object]:
    return {
        "state": "PASS",
        "runtime_mode": "public-only",
        "config_profile": "deployment",
        "reason_codes": [],
        "warning_codes": [],
        "presence": {
            "database_url": True,
            "home_coordinates": False,
            "google_project_and_dataset": False,
            "google_auth": False,
        },
    }


def _fresh_provider() -> dict[str, object]:
    return {
        "ingest_state": "ok",
        "freshness_state": "fresh",
        "failure_domain": "none",
        "reason_code": "FRESH",
        "last_attempt_at_utc": "2026-09-14T18:00:00Z",
        "last_success_at_utc": "2026-09-14T18:00:00Z",
        "last_init_time_utc": "2026-09-14T18:00:00Z",
        "last_retrieved_at_utc": "2026-09-14T18:05:00Z",
        "latest_valid_time_utc": "2026-09-15T18:00:00Z",
        "last_observed_at_utc": None,
        "attempt_age_hours": 0.25,
        "success_age_hours": 0.25,
        "source_age_hours": 0.25,
    }


def _bundle(
    *,
    readiness: dict[str, object] | object | None = None,
    config: dict[str, object] | object | None = None,
    providers: dict[str, object] | object | None = None,
    corpus: dict[str, object] | object | None = None,
) -> dict[str, object]:
    return build_incident_diagnostics(
        source_sha=SOURCE_SHA,
        readiness=_readiness() if readiness is None else readiness,
        config=_config() if config is None else config,
        provider_health={"icon_d2": _fresh_provider()} if providers is None else providers,
        corpus_integrity={"checked": True, "ok": True, "error_count": 0} if corpus is None else corpus,
    )


def test_contract_snapshot_matches_executable_registry() -> None:
    path = Path(__file__).parents[1] / "contracts" / "incident-diagnostics-v1.json"
    assert json.loads(path.read_text()) == INCIDENT_DIAGNOSTICS_CONTRACT


def test_all_healthy_evidence_is_pass() -> None:
    payload = _bundle()
    assert payload["state"] == "PASS"
    assert payload["reason_codes"] == []
    assert payload["privacy"]["safe_for_github"] is True
    assert payload["authority"] == {
        "read_only": True,
        "live_authority_granted": False,
        "production_data_authority_granted": False,
        "automatic_recovery_authority_granted": False,
    }


def test_partial_upstream_outage_is_warn_and_other_provider_stays_visible() -> None:
    upstream = _fresh_provider()
    upstream.update(
        ingest_state="error",
        freshness_state="error",
        failure_domain="upstream_or_transport",
        reason_code="RECENT_UPSTREAM_OR_TRANSPORT_ERROR",
    )
    payload = _bundle(providers={"icon_d2": _fresh_provider(), "ecmwf_aifs": upstream})

    assert payload["state"] == "WARN"
    assert "PROVIDER_UPSTREAM_OUTAGE" in payload["reason_codes"]
    providers = {item["id"]: item for item in payload["providers"]}
    assert providers["icon_d2"]["freshness_state"] == "fresh"
    assert providers["ecmwf_aifs"]["freshness_state"] == "error"


def test_local_ingest_failure_is_not_mislabeled_as_upstream() -> None:
    local = _fresh_provider()
    local.update(
        ingest_state="error",
        freshness_state="error",
        failure_domain="local_persistence",
        reason_code="RECENT_LOCAL_PERSISTENCE_ERROR",
    )
    payload = _bundle(providers={"icon_d2": local})

    assert payload["state"] == "WARN"
    assert "PROVIDER_LOCAL_INGEST_FAILURE" in payload["reason_codes"]
    assert "PROVIDER_UPSTREAM_OUTAGE" not in payload["reason_codes"]


def test_stale_source_data_is_distinct_from_provider_outage() -> None:
    stale = _fresh_provider()
    stale.update(
        freshness_state="stale",
        failure_domain="upstream_data",
        reason_code="SOURCE_DATA_STALE",
        source_age_hours=16.0,
    )
    payload = _bundle(providers={"ecmwf_ifs": stale})

    assert payload["state"] == "WARN"
    assert "PROVIDER_STALE_DATA" in payload["reason_codes"]
    assert "PROVIDER_UPSTREAM_OUTAGE" not in payload["reason_codes"]


def test_schema_mismatch_is_blocked() -> None:
    readiness = _readiness()
    readiness["ready"] = False
    readiness["status"] = "not_ready"
    readiness["database"] = {
        "state": "schema_incomplete",
        "required_tables_present": False,
        "missing_tables": ["forecast_values"],
    }
    payload = _bundle(readiness=readiness)

    assert payload["state"] == "BLOCKED"
    assert "DATABASE_SCHEMA_MISMATCH" in payload["reason_codes"]
    assert "APPLICATION_NOT_READY" in payload["reason_codes"]
    assert payload["database"]["missing_table_count"] == 1


def test_configuration_failure_is_blocked_without_private_values() -> None:
    config = _config()
    config.update(
        state="BLOCKED",
        reason_codes=["HOME_COORDINATE_PAIR_INCOMPLETE"],
    )
    payload = _bundle(config=config)

    assert payload["state"] == "BLOCKED"
    assert "CONFIG_READINESS_FAILURE" in payload["reason_codes"]
    assert "DATABASE_SCHEMA_MISMATCH" not in payload["reason_codes"]


def test_corpus_integrity_failure_is_blocked_without_raw_errors() -> None:
    payload = _bundle(
        corpus={
            "checked": True,
            "ok": False,
            "error_count": 2,
            "errors": ["duplicate_payload:icon_d2:station_10416:2026-09-14T12:00:00Z"],
        }
    )

    assert payload["state"] == "BLOCKED"
    assert "CORPUS_INTEGRITY_FAILURE" in payload["reason_codes"]
    assert payload["corpus"] == {"checked": True, "ok": False, "error_count": 2}
    assert "errors" not in payload["corpus"]


def test_corrupted_evidence_is_error() -> None:
    payload = _bundle(providers={"icon_d2": "not-a-health-object"})
    assert payload["state"] == "ERROR"
    assert "DIAGNOSTICS_EVIDENCE_CORRUPT" in payload["reason_codes"]


def test_sensitive_evidence_is_rejected_and_never_echoed() -> None:
    providers = {"icon_d2": _fresh_provider()}
    providers["icon_d2"]["detail"] = "/home/private/weather.log token=super-secret-value"
    readiness = deepcopy(_readiness())
    readiness["HOME_LAT"] = 51.512345

    payload = _bundle(readiness=readiness, providers=providers)
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "ERROR"
    assert "PRIVATE_COORDINATE_EVIDENCE_REJECTED" in payload["reason_codes"]
    assert "PRIVATE_PATH_EVIDENCE_REJECTED" in payload["reason_codes"]
    assert "CREDENTIAL_EVIDENCE_REJECTED" in payload["reason_codes"]
    assert "RAW_LOG_OR_DETAIL_EVIDENCE_REJECTED" in payload["reason_codes"]
    assert "51.512345" not in rendered
    assert "super-secret-value" not in rendered
    assert "/home/private/weather.log" not in rendered


def test_missing_database_collection_is_read_only(tmp_path: Path) -> None:
    database_path = tmp_path / "must-not-be-created.db"
    env = {
        "WEATHER_RUNTIME_MODE": "public-only",
        "WEATHER_CONFIG_PROFILE": "deployment",
        "WEATHER_CONFIG_SCHEMA_VERSION": "1",
        "DATABASE_INIT_MODE": "require-existing",
        "DATABASE_URL": f"sqlite:///{database_path}",
    }

    payload = collect_incident_diagnostics(source_sha=SOURCE_SHA, env=env)

    assert payload["state"] == "BLOCKED"
    assert "DATABASE_SCHEMA_MISMATCH" in payload["reason_codes"]
    assert database_path.exists() is False
    assert str(database_path) not in json.dumps(payload, sort_keys=True)
