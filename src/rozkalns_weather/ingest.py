from __future__ import annotations

from .config import Settings
from .db import Database
from .orchestrator import IngestOrchestrator


def ingest_public_baselines(settings: Settings, database: Database) -> dict[str, str]:
    """Backward-compatible wrapper around the hardened orchestrator."""
    detailed = IngestOrchestrator(settings, database).collect_public()
    return {provider: str(payload["state"]) for provider, payload in detailed.items()}
