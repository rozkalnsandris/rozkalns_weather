from __future__ import annotations

from collections.abc import Mapping
import json
import os
from typing import Any

from .config import Settings

CONFIG_PROFILES = frozenset({"development", "deployment"})


def validate_runtime_config(env: Mapping[str, str]) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    profile = (env.get("WEATHER_CONFIG_PROFILE") or "development").strip() or "development"
    if profile not in CONFIG_PROFILES:
        reasons.append("CONFIG_PROFILE_INVALID")

    try:
        settings = Settings.from_env(dict(env))
    except ValueError as exc:
        return {
            "state": "BLOCKED",
            "runtime_mode": (env.get("WEATHER_RUNTIME_MODE") or "unknown"),
            "reason_codes": ["CONFIG_INVALID"],
            "detail": str(exc),
            "privacy": {"coordinates_exposed": False, "credentials_exposed": False},
        }

    if profile == "deployment" and settings.database_init_mode != "require-existing":
        reasons.append("IMPLICIT_DATABASE_INITIALIZATION_UNSAFE")
    if profile == "development" and settings.database_init_mode == "auto":
        warnings.append("DEVELOPMENT_IMPLICIT_DATABASE_INITIALIZATION")

    return {
        "state": "BLOCKED" if reasons else ("WARN" if warnings else "PASS"),
        "runtime_mode": settings.runtime_mode,
        "config_profile": profile,
        "database_init_mode": settings.database_init_mode,
        "home_configured": settings.home_configured,
        "reason_codes": reasons,
        "warning_codes": warnings,
        "privacy": {
            "coordinate_values_exposed": False,
            "credential_values_exposed": False,
            "database_url_value_exposed": False,
        },
    }


def main() -> None:
    payload = validate_runtime_config(os.environ)
    print(json.dumps(payload, sort_keys=True))
    if payload["state"] == "BLOCKED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
