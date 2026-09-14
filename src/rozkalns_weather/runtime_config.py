from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .config import Settings

RUNTIME_CONFIG_SCHEMA = "runtime-config-v1"
CONFIG_PROFILES = frozenset({"development", "deployment"})

RUNTIME_CONFIG_CONTRACT: dict[str, Any] = {
    "schema": RUNTIME_CONFIG_SCHEMA,
    "schema_version": 1,
    "runtime_modes": {
        "public-only": {
            "required": ["WEATHER_RUNTIME_MODE", "DATABASE_INIT_MODE", "DATABASE_URL"],
            "optional": [
                "HOME_TIMEZONE",
                "INGEST_TIMEOUT_SECONDS",
                "INGEST_RETRIES",
                "PRECIP_EVENT_THRESHOLD_MM",
            ],
            "deployment_database_init_mode": "require-existing",
            "private_home_required": False,
            "google_auth_required": False,
        },
        "private-research": {
            "required": [
                "WEATHER_RUNTIME_MODE",
                "DATABASE_INIT_MODE",
                "DATABASE_URL",
                "HOME_LAT",
                "HOME_LON",
                "GOOGLE_CLOUD_PROJECT",
                "WEATHERNEXT_BIGQUERY_DATASET",
                "GOOGLE_AUTH_PRESENT",
            ],
            "optional": [
                "HOME_TIMEZONE",
                "HOME_LABEL",
                "INGEST_TIMEOUT_SECONDS",
                "INGEST_RETRIES",
                "PRECIP_EVENT_THRESHOLD_MM",
            ],
            "deployment_database_init_mode": "require-existing",
            "private_home_required": True,
            "google_auth_required": True,
        },
    },
    "presence_only_keys": ["GOOGLE_AUTH_PRESENT", "HOME_COORDINATES_PRESENT"],
    "secret_values_allowed_in_evidence": False,
    "home_coordinates_allowed_in_evidence": False,
}


def _present(env: Mapping[str, str], key: str) -> bool:
    value = env.get(key)
    return bool(value is not None and value.strip())


def _flag(env: Mapping[str, str], key: str) -> bool | None:
    value = env.get(key)
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_reason(exc: ValueError) -> str:
    message = str(exc)
    if "WEATHER_RUNTIME_MODE" in message:
        return "RUNTIME_MODE_INVALID"
    if "DATABASE_INIT_MODE" in message:
        return "DATABASE_INIT_MODE_INVALID"
    if "HOME_LAT and HOME_LON" in message:
        return "HOME_COORDINATE_PAIR_INCOMPLETE"
    if "HOME_LAT" in message or "HOME_LON" in message:
        return "HOME_COORDINATE_INVALID"
    if "INGEST_TIMEOUT_SECONDS" in message:
        return "INGEST_TIMEOUT_INVALID"
    if "INGEST_RETRIES" in message:
        return "INGEST_RETRIES_INVALID"
    if "PRECIP_EVENT_THRESHOLD_MM" in message:
        return "PRECIP_THRESHOLD_INVALID"
    return "CONFIG_PARSE_ERROR"


def validate_runtime_config(
    env: Mapping[str, str],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []

    schema_value = (env.get("WEATHER_CONFIG_SCHEMA_VERSION") or "1").strip()
    if schema_value != "1":
        reasons.append("CONFIG_SCHEMA_UNSUPPORTED")

    profile = (env.get("WEATHER_CONFIG_PROFILE") or "development").strip() or "development"
    if profile not in CONFIG_PROFILES:
        reasons.append("CONFIG_PROFILE_INVALID")

    if settings is None:
        try:
            settings = Settings.from_env(dict(env))
        except ValueError as exc:
            reasons.append(_parse_reason(exc))
            return _payload(
                runtime_mode=(env.get("WEATHER_RUNTIME_MODE") or "unknown").strip() or "unknown",
                profile=profile,
                env=env,
                reasons=reasons,
                warnings=warnings,
            )

    auth_flag = _flag(env, "GOOGLE_AUTH_PRESENT")
    if _present(env, "GOOGLE_AUTH_PRESENT") and auth_flag is None:
        reasons.append("GOOGLE_AUTH_PRESENCE_FLAG_INVALID")

    if profile == "deployment" and settings.database_init_mode != "require-existing":
        reasons.append("IMPLICIT_DATABASE_INITIALIZATION_UNSAFE")

    if settings.runtime_mode == "public-only":
        if settings.home_configured:
            reasons.append("PUBLIC_RUNTIME_PRIVATE_HOME_UNSUPPORTED")
        if settings.weathernext_cloud_configured or auth_flag is True:
            reasons.append("PUBLIC_RUNTIME_PRIVATE_ACCESS_UNSUPPORTED")
        if profile == "development" and settings.database_init_mode == "auto":
            warnings.append("DEVELOPMENT_IMPLICIT_DATABASE_INITIALIZATION")
    elif settings.runtime_mode == "private-research":
        if not settings.home_configured:
            reasons.append("PRIVATE_HOME_REQUIRED")
        if not settings.weathernext_cloud_configured:
            reasons.append("PROJECT_DATASET_CONFIG_REQUIRED")
        if auth_flag is not True:
            reasons.append("GOOGLE_AUTH_PRESENCE_REQUIRED")
        if profile != "deployment":
            warnings.append("PRIVATE_RESEARCH_NOT_DEPLOYMENT_PROFILE")

    return _payload(
        runtime_mode=settings.runtime_mode,
        profile=profile,
        env=env,
        reasons=reasons,
        warnings=warnings,
        settings=settings,
        auth_flag=auth_flag,
    )


def _payload(
    *,
    runtime_mode: str,
    profile: str,
    env: Mapping[str, str],
    reasons: list[str],
    warnings: list[str],
    settings: Settings | None = None,
    auth_flag: bool | None = None,
) -> dict[str, Any]:
    state = "BLOCKED" if reasons else ("WARN" if warnings else "PASS")
    home_present = settings.home_configured if settings is not None else (_present(env, "HOME_LAT") and _present(env, "HOME_LON"))
    project_dataset_present = (
        settings.weathernext_cloud_configured
        if settings is not None
        else (_present(env, "GOOGLE_CLOUD_PROJECT") and _present(env, "WEATHERNEXT_BIGQUERY_DATASET"))
    )
    return {
        "schema": RUNTIME_CONFIG_SCHEMA,
        "schema_version": 1,
        "state": state,
        "runtime_mode": runtime_mode,
        "config_profile": profile,
        "reason_codes": sorted(set(reasons)),
        "warning_codes": sorted(set(warnings)),
        "presence": {
            "database_url": _present(env, "DATABASE_URL") or (settings is not None and bool(settings.database_url)),
            "home_coordinates": bool(home_present),
            "google_project_and_dataset": bool(project_dataset_present),
            "google_auth": auth_flag is True,
        },
        "privacy": {
            "coordinate_values_exposed": False,
            "credential_values_exposed": False,
            "database_url_value_exposed": False,
            "raw_environment_exposed": False,
        },
        "authority": {
            "live_authority_granted": False,
            "production_data_authority_granted": False,
            "credential_authority_granted": False,
        },
    }


def assert_startup_runtime_config(env: Mapping[str, str], settings: Settings) -> dict[str, Any]:
    payload = validate_runtime_config(env, settings=settings)
    if payload["state"] == "BLOCKED":
        codes = ",".join(payload["reason_codes"])
        raise RuntimeError(f"runtime configuration blocked: {codes}")
    return payload
