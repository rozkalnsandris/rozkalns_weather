from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping

from .weathernext_access import expected_required_schema_fingerprint

CONTRACT_ID = "private-home-weathernext-runtime-activation.v1"
EXPECTED_MODEL_NAME = "WeatherNext 3"
EXPECTED_MODEL_VERSION = "3.0.0"
EXPECTED_PROVIDER = "weathernext3"
EXPECTED_ACCESS_STATE = "canary_ready_for_snapshot"
EXPECTED_SURFACES = ("0p05", "0p1")
EXPECTED_STATISTICS = ("mean", "p10", "p25", "p50", "p75", "p90")
MAX_ACCESS_EVIDENCE_AGE_SECONDS = 86_400
MAX_FUTURE_SKEW_SECONDS = 300

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_PRIVATE_KEYS = frozenset(
    {
        "home_lat",
        "home_lon",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "project",
        "project_id",
        "google_cloud_project",
        "dataset",
        "dataset_id",
        "weathernext_bigquery_dataset",
        "credential",
        "credentials",
        "token",
        "secret",
        "service_account",
        "sql",
        "query_sql",
        "database_path",
        "filesystem_path",
        "host_path",
        "raw_log",
        "raw_logs",
        "environment",
        "env",
    }
)

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "source_sha",
        "checked_at_utc",
        "runtime_mode",
        "home",
        "credentials",
        "weathernext_access",
        "accepted_snapshot",
        "production_corpus",
        "ui_safety",
        "authority",
    }
)
_HOME_KEYS = frozenset(
    {
        "coordinates_present",
        "exact_coordinates_exposed",
        "forecast_display_enabled",
        "measured_home_accuracy_claimed",
    }
)
_CREDENTIAL_KEYS = frozenset(
    {
        "google_auth_present",
        "project_dataset_config_present",
        "credential_material_exposed",
    }
)
_ACCESS_KEYS = frozenset(
    {
        "verified",
        "state",
        "verified_at_utc",
        "provider",
        "model_name",
        "model_version",
        "schema_fingerprint_sha256",
    }
)
_SNAPSHOT_KEYS = frozenset(
    {
        "present",
        "provenance_complete",
        "provider",
        "model_name",
        "model_version",
        "schema_fingerprint_sha256",
        "product_surfaces",
        "statistics",
        "snapshot_identity_sha256",
        "real_values_exposed",
    }
)
_CORPUS_KEYS = frozenset(
    {
        "schema_ready",
        "station_10416_truth_ready",
        "public_forecast_corpus_ready",
        "immutable_forecast_history_ready",
    }
)
_UI_KEYS = frozenset(
    {
        "station_measured_accuracy_location_id",
        "home_display_role",
        "official_warning_authority",
        "model_warning_authority",
    }
)
_AUTHORITY_KEYS = frozenset(
    {
        "live_authority_granted",
        "production_data_authority_granted",
        "credential_mutation_authority_granted",
        "runtime_mutation_performed",
    }
)


def _mapping(value: object, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], *, path: str) -> None:
    observed = frozenset(str(key) for key in value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(f"{path} schema mismatch: missing={missing} extra={extra}")


def _find_private_key(value: object, *, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            child_path = f"{path}.{key}" if path else key
            if key in _PRIVATE_KEYS:
                return child_path
            found = _find_private_key(child, path=child_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_private_key(child, path=f"{path}[{index}]")
            if found:
                return found
    return None


def _utc(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 UTC timestamp") from exc
    return parsed.astimezone(timezone.utc)


def _bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be boolean")
    return value


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _string_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    return list(value)


def evaluate_private_runtime_activation(
    evidence: Mapping[str, Any], *, now: datetime | None = None
) -> dict[str, object]:
    """Validate sanitized source-side eligibility evidence without performing any mutation."""

    private_key = _find_private_key(evidence)
    if private_key:
        raise ValueError(f"private evidence field forbidden: {private_key}")

    _require_exact_keys(evidence, _TOP_LEVEL_KEYS, path="evidence")
    if evidence.get("schema_version") != 1:
        raise ValueError("schema_version must equal 1")

    source_sha = _string(evidence.get("source_sha"), field="source_sha")
    if not _SHA40.fullmatch(source_sha):
        raise ValueError("source_sha must be a lowercase 40-character git SHA")

    checked_at = _utc(evidence.get("checked_at_utc"), field="checked_at_utc")
    effective_now = now.astimezone(timezone.utc) if now is not None else checked_at

    home = _mapping(evidence.get("home"), path="home")
    credentials = _mapping(evidence.get("credentials"), path="credentials")
    access = _mapping(evidence.get("weathernext_access"), path="weathernext_access")
    snapshot = _mapping(evidence.get("accepted_snapshot"), path="accepted_snapshot")
    corpus = _mapping(evidence.get("production_corpus"), path="production_corpus")
    ui = _mapping(evidence.get("ui_safety"), path="ui_safety")
    authority = _mapping(evidence.get("authority"), path="authority")

    _require_exact_keys(home, _HOME_KEYS, path="home")
    _require_exact_keys(credentials, _CREDENTIAL_KEYS, path="credentials")
    _require_exact_keys(access, _ACCESS_KEYS, path="weathernext_access")
    _require_exact_keys(snapshot, _SNAPSHOT_KEYS, path="accepted_snapshot")
    _require_exact_keys(corpus, _CORPUS_KEYS, path="production_corpus")
    _require_exact_keys(ui, _UI_KEYS, path="ui_safety")
    _require_exact_keys(authority, _AUTHORITY_KEYS, path="authority")

    blockers: list[str] = []

    if evidence.get("runtime_mode") != "private-research":
        blockers.append("RUNTIME_MODE_MISMATCH")

    if not _bool(home.get("coordinates_present"), field="home.coordinates_present"):
        blockers.append("HOME_COORDINATES_MISSING")
    if _bool(home.get("exact_coordinates_exposed"), field="home.exact_coordinates_exposed"):
        blockers.append("HOME_COORDINATES_EXPOSED")
    if not _bool(home.get("forecast_display_enabled"), field="home.forecast_display_enabled"):
        blockers.append("HOME_ACCURACY_SEMANTICS_VIOLATION")
    if _bool(home.get("measured_home_accuracy_claimed"), field="home.measured_home_accuracy_claimed"):
        blockers.append("HOME_ACCURACY_SEMANTICS_VIOLATION")

    if not _bool(credentials.get("google_auth_present"), field="credentials.google_auth_present"):
        blockers.append("GOOGLE_AUTH_MISSING")
    if not _bool(
        credentials.get("project_dataset_config_present"),
        field="credentials.project_dataset_config_present",
    ):
        blockers.append("PROJECT_DATASET_CONFIG_MISSING")
    if _bool(
        credentials.get("credential_material_exposed"),
        field="credentials.credential_material_exposed",
    ):
        blockers.append("CREDENTIAL_MATERIAL_EXPOSED")

    if not _bool(access.get("verified"), field="weathernext_access.verified"):
        blockers.append("PRIVATE_ACCESS_NOT_VERIFIED")
    if access.get("state") != EXPECTED_ACCESS_STATE:
        blockers.append("ACCESS_STATE_NOT_READY")

    access_verified_at = _utc(
        access.get("verified_at_utc"), field="weathernext_access.verified_at_utc"
    )
    age_seconds = (checked_at - access_verified_at).total_seconds()
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        blockers.append("ACCESS_EVIDENCE_FROM_FUTURE")
    elif age_seconds > MAX_ACCESS_EVIDENCE_AGE_SECONDS:
        blockers.append("ACCESS_EVIDENCE_STALE")
    if (effective_now - checked_at).total_seconds() > MAX_ACCESS_EVIDENCE_AGE_SECONDS:
        blockers.append("ACCESS_EVIDENCE_STALE")

    expected_schema = expected_required_schema_fingerprint()
    access_schema = _string(
        access.get("schema_fingerprint_sha256"),
        field="weathernext_access.schema_fingerprint_sha256",
    )
    snapshot_schema = _string(
        snapshot.get("schema_fingerprint_sha256"),
        field="accepted_snapshot.schema_fingerprint_sha256",
    )
    if not _SHA256.fullmatch(access_schema) or not _SHA256.fullmatch(snapshot_schema):
        raise ValueError("schema fingerprints must be lowercase SHA-256 values")

    if (
        access.get("provider") != EXPECTED_PROVIDER
        or access.get("model_name") != EXPECTED_MODEL_NAME
        or access.get("model_version") != EXPECTED_MODEL_VERSION
    ):
        blockers.append("MODEL_IDENTITY_DRIFT")
    if access_schema != expected_schema:
        blockers.append("SCHEMA_FINGERPRINT_DRIFT")

    if not _bool(snapshot.get("present"), field="accepted_snapshot.present"):
        blockers.append("ACCEPTED_SNAPSHOT_MISSING")
    if not _bool(
        snapshot.get("provenance_complete"), field="accepted_snapshot.provenance_complete"
    ):
        blockers.append("SNAPSHOT_PROVENANCE_INCOMPLETE")
    if (
        snapshot.get("provider") != EXPECTED_PROVIDER
        or snapshot.get("model_name") != EXPECTED_MODEL_NAME
        or snapshot.get("model_version") != EXPECTED_MODEL_VERSION
    ):
        blockers.append("MODEL_IDENTITY_DRIFT")
    if snapshot_schema != expected_schema or snapshot_schema != access_schema:
        blockers.append("SCHEMA_FINGERPRINT_DRIFT")

    surfaces = _string_list(snapshot.get("product_surfaces"), field="accepted_snapshot.product_surfaces")
    if tuple(surfaces) != EXPECTED_SURFACES:
        blockers.append("SNAPSHOT_SURFACE_DRIFT")
    statistics = _string_list(snapshot.get("statistics"), field="accepted_snapshot.statistics")
    if tuple(statistics) != EXPECTED_STATISTICS:
        blockers.append("SNAPSHOT_STATISTIC_DRIFT")
    snapshot_identity = _string(
        snapshot.get("snapshot_identity_sha256"), field="accepted_snapshot.snapshot_identity_sha256"
    )
    if not _SHA256.fullmatch(snapshot_identity):
        blockers.append("SNAPSHOT_IDENTITY_INVALID")
    if _bool(snapshot.get("real_values_exposed"), field="accepted_snapshot.real_values_exposed"):
        blockers.append("REAL_VALUES_EXPOSED")

    if not _bool(corpus.get("schema_ready"), field="production_corpus.schema_ready"):
        blockers.append("PRODUCTION_SCHEMA_NOT_READY")
    if not _bool(
        corpus.get("station_10416_truth_ready"),
        field="production_corpus.station_10416_truth_ready",
    ):
        blockers.append("STATION_TRUTH_NOT_READY")
    if not _bool(
        corpus.get("public_forecast_corpus_ready"),
        field="production_corpus.public_forecast_corpus_ready",
    ):
        blockers.append("PUBLIC_CORPUS_NOT_READY")
    if not _bool(
        corpus.get("immutable_forecast_history_ready"),
        field="production_corpus.immutable_forecast_history_ready",
    ):
        blockers.append("IMMUTABLE_HISTORY_NOT_READY")

    if (
        ui.get("station_measured_accuracy_location_id") != "station_10416"
        or ui.get("home_display_role") != "forecast_only"
    ):
        blockers.append("HOME_ACCURACY_SEMANTICS_VIOLATION")
    if ui.get("official_warning_authority") != "DWD" or _bool(
        ui.get("model_warning_authority"), field="ui_safety.model_warning_authority"
    ):
        blockers.append("DWD_WARNING_AUTHORITY_VIOLATION")

    if any(
        _bool(authority.get(key), field=f"authority.{key}")
        for key in sorted(_AUTHORITY_KEYS)
    ):
        blockers.append("AUTHORITY_EXPANSION")

    blockers = sorted(set(blockers))
    return {
        "schema_version": 1,
        "contract": CONTRACT_ID,
        "state": "PASS" if not blockers else "BLOCKED",
        "ready": not blockers,
        "blockers": blockers,
        "source_sha": source_sha,
        "runtime_mode": "private-research",
        "location_semantics": {
            "station_10416_measured_accuracy": True,
            "home_forecast_only": True,
        },
        "weathernext": {
            "provider": EXPECTED_PROVIDER,
            "model_name": EXPECTED_MODEL_NAME,
            "model_version": EXPECTED_MODEL_VERSION,
            "schema_fingerprint_sha256": expected_schema,
            "accepted_snapshot_identity_sha256": snapshot_identity,
        },
        "warning_authority": "DWD",
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "project_dataset_identity_exposed": False,
            "real_weather_values_exposed": False,
            "private_paths_or_logs_exposed": False,
        },
        "authority": {
            "live_authority_granted": False,
            "production_data_authority_granted": False,
            "credential_mutation_authority_granted": False,
            "runtime_mutation_performed": False,
        },
    }
