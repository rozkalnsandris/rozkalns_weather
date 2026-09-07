from __future__ import annotations

from pathlib import Path
import os

from .config import Settings
from .db import Database
from .providers import PROVIDERS
from .providers.weathernext import access_state

REQUIRED_TABLES = frozenset(
    {
        "locations",
        "forecast_runs",
        "forecast_values",
        "observations",
        "provider_ingest_status",
        "model_events",
    }
)
PUBLIC_PROVIDER_IDS = tuple(provider.id for provider in PROVIDERS if provider.id != "weathernext3")


def _database_exists(database: Database) -> bool:
    return database.path == ":memory:" or Path(database.path).is_file()


def database_schema_state(database: Database) -> dict[str, object]:
    exists = _database_exists(database)
    if not exists:
        return {
            "state": "missing",
            "exists": False,
            "required_tables_present": False,
            "missing_tables": sorted(REQUIRED_TABLES),
            "tables": [],
        }
    try:
        tables = set(database.table_names())
    except Exception as exc:
        return {
            "state": "error",
            "exists": True,
            "required_tables_present": False,
            "missing_tables": sorted(REQUIRED_TABLES),
            "tables": [],
            "detail": type(exc).__name__,
        }
    missing = sorted(REQUIRED_TABLES - tables)
    return {
        "state": "ready" if not missing else "schema_incomplete",
        "exists": True,
        "required_tables_present": not missing,
        "missing_tables": missing,
        "tables": sorted(tables),
    }


def storage_state(database: Database) -> dict[str, object]:
    if database.path == ":memory:":
        return {
            "class": "ephemeral_memory",
            "persistent": False,
            "writable": True,
            "path_exposed": False,
        }
    path = Path(database.path)
    target = path if path.exists() else path.parent
    return {
        "class": "persistent_sqlite_file",
        "persistent": True,
        "writable": bool(target.exists() and os.access(target, os.W_OK)),
        "path_exposed": False,
    }


def readiness_payload(settings: Settings, database: Database) -> dict[str, object]:
    database_state = database_schema_state(database)
    storage = storage_state(database)
    stored = database.provider_statuses() if database_state["state"] == "ready" else {}

    providers: list[dict[str, object]] = []
    for provider in PROVIDERS:
        saved = stored.get(provider.id, {})
        if provider.id == "weathernext3":
            state = saved.get("state") or access_state(configured=settings.weathernext_cloud_configured)
            required_for_runtime = False
        else:
            state = saved.get("state", "adapter_ready_not_ingested")
            required_for_runtime = provider.id in PUBLIC_PROVIDER_IDS
        providers.append(
            {
                "id": provider.id,
                "role": provider.role,
                "state": state,
                "required_for_runtime": required_for_runtime,
                "last_success_at_utc": saved.get("last_success_at_utc"),
            }
        )

    ready = bool(database_state["state"] == "ready" and storage["writable"])
    return {
        "schema_version": 1,
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "runtime_mode": settings.runtime_mode,
        "database_init_mode": settings.database_init_mode,
        "database": database_state,
        "storage": storage,
        "home": {
            "configured": settings.home_configured,
            "required_for_public_runtime": False,
            "coordinates_exposed": False,
        },
        "weathernext": {
            "configured": settings.weathernext_cloud_configured,
            "required_for_public_runtime": False,
            "values_fabricated": False,
        },
        "providers": providers,
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
        },
    }
