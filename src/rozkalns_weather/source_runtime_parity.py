from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Mapping

CONTRACT = "source-runtime-descriptor-parity-v1"
SCHEMA_VERSION = 1
SERVICE_ROLES = (
    "application_service",
    "schema_init_service",
    "public_ingest_service",
    "readiness_service",
    "corpus_check_service",
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _compose_snapshot(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    services: dict[str, dict[str, Any]] = {}
    current: str | None = None
    in_services = False
    for line in text.splitlines():
        if line == "services:":
            in_services = True
            continue
        if in_services and line and not line.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line) if in_services else None
        if match:
            current = match.group(1)
            services[current] = {"environment": {}, "text": ""}
            continue
        if current is None:
            continue
        services[current]["text"] += line + "\n"
        env_match = re.match(r"^\s+-\s+([A-Z0-9_]+)=(.*)$", line)
        if env_match:
            services[current]["environment"][env_match.group(1)] = env_match.group(2)

    for payload in services.values():
        body = str(payload.pop("text"))
        command = re.search(r"^\s+command:\s*(.+)$", body, re.MULTILINE)
        payload["command"] = command.group(1).strip() if command else None
        payload["ready_healthcheck"] = "/ready" in body

    return {"services": services}


def _systemd_snapshot(root: Path) -> dict[str, Any]:
    service_path = root / "deploy" / "rozkalns-weather-public-ingest.service.example"
    timer_path = root / "deploy" / "rozkalns-weather-public-ingest.timer.example"
    service_text = service_path.read_text(encoding="utf-8")
    timer_text = timer_path.read_text(encoding="utf-8")
    calendar = re.search(r"^OnCalendar=(.+)$", timer_text, re.MULTILINE)
    return {
        "service_unit": service_path.name.removesuffix(".example"),
        "timer_unit": timer_path.name.removesuffix(".example"),
        "on_calendar": calendar.group(1).strip() if calendar else None,
        "ingest_command_present": "rozkalns-weather ingest-public" in service_text,
    }


def load_source_parity_bundle(root: Path, *, current_source_sha: str) -> dict[str, Any]:
    root = Path(root)
    return {
        "repository": "rozkalnsandris/rozkalns_weather",
        "current_source_sha": current_source_sha,
        "runtime_descriptor": _json(root / "deploy" / "runtime-descriptor.json"),
        "simple_deploy": _json(root / ".simple-deploy.json"),
        "schedule": _json(root / "deploy" / "public-ingest-schedule.json"),
        "bootstrap": _json(root / "deploy" / "production-public-corpus-bootstrap.json"),
        "release_identity": _json(root / "deploy" / "release-artifact-identity.json"),
        "source_binding": _json(root / "deploy" / "rpi5-source-binding.json"),
        "compose": _compose_snapshot(root / "deploy" / "docker-compose.public.yml"),
        "systemd_examples": _systemd_snapshot(root),
    }


def _nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def evaluate_source_runtime_parity(bundle: Mapping[str, Any]) -> dict[str, Any]:
    data = deepcopy(dict(bundle))
    reasons: set[str] = set()

    runtime = data.get("runtime_descriptor") or {}
    simple = data.get("simple_deploy") or {}
    schedule = data.get("schedule") or {}
    bootstrap = data.get("bootstrap") or {}
    release = data.get("release_identity") or {}
    binding = data.get("source_binding") or {}
    compose = data.get("compose") or {}
    systemd = data.get("systemd_examples") or {}

    packaging = _nested(runtime, "packaging") or {}
    expected_services = {
        role: packaging.get(role)
        for role in SERVICE_ROLES
        if isinstance(packaging, Mapping) and packaging.get(role)
    }
    compose_services = (compose.get("services") or {}) if isinstance(compose, Mapping) else {}
    for service_name in expected_services.values():
        if service_name not in compose_services:
            reasons.add("MISSING_COMPOSE_SERVICE")

    application_service = expected_services.get("application_service")
    public_ingest_service = expected_services.get("public_ingest_service")
    schema_init_service = expected_services.get("schema_init_service")

    if _nested(simple, "compose", "service") != application_service:
        reasons.add("COMPOSE_SERVICE_IDENTITY_MISMATCH")
    if _nested(simple, "compose", "file") != packaging.get("compose_file"):
        reasons.add("COMPOSE_FILE_IDENTITY_MISMATCH")
    if _nested(simple, "compose", "project") != _nested(runtime, "deployment_architecture", "compose_project"):
        reasons.add("COMPOSE_PROJECT_MISMATCH")

    scheduled_service = _nested(schedule, "public_ingest", "service")
    if scheduled_service != public_ingest_service or scheduled_service not in compose_services:
        reasons.add("INGEST_SERVICE_MISMATCH")

    schedule_service_unit = _nested(schedule, "systemd_timer", "service_unit")
    schedule_timer_unit = _nested(schedule, "systemd_timer", "timer_unit")
    schedule_calendar = _nested(schedule, "systemd_timer", "on_calendar")
    if (
        schedule_service_unit != systemd.get("service_unit")
        or schedule_timer_unit != systemd.get("timer_unit")
        or schedule_calendar != systemd.get("on_calendar")
        or systemd.get("ingest_command_present") is not True
    ):
        reasons.add("TIMER_JOB_IDENTITY_MISMATCH")

    health_endpoint = _nested(runtime, "health", "liveness_endpoint")
    ready_endpoint = _nested(runtime, "health", "readiness_endpoint")
    if _nested(simple, "health", "liveness_path") != health_endpoint:
        reasons.add("LIVENESS_ENDPOINT_MISMATCH")
    if _nested(simple, "health", "readiness", "path") != ready_endpoint:
        reasons.add("READINESS_ENDPOINT_MISMATCH")
    weather_payload = compose_services.get(application_service, {}) if application_service else {}
    if ready_endpoint == "/ready" and not weather_payload.get("ready_healthcheck"):
        reasons.add("READINESS_ENDPOINT_MISMATCH")

    runtime_mode = _nested(runtime, "runtime_contract", "runtime_mode")
    init_mode = _nested(runtime, "runtime_contract", "database_init_mode")
    weather_env = weather_payload.get("environment", {}) if isinstance(weather_payload, Mapping) else {}
    if weather_env.get("WEATHER_RUNTIME_MODE") != runtime_mode:
        reasons.add("RUNTIME_MODE_MISMATCH")
    if weather_env.get("DATABASE_INIT_MODE") != init_mode:
        reasons.add("DATABASE_INIT_MODE_MISMATCH")

    schema_payload = compose_services.get(schema_init_service, {}) if schema_init_service else {}
    schema_env = schema_payload.get("environment", {}) if isinstance(schema_payload, Mapping) else {}
    bootstrap_schema = _nested(bootstrap, "schema_init") or {}
    if init_mode != "require-existing" or weather_env.get("DATABASE_INIT_MODE") != "require-existing":
        reasons.add("IMPLICIT_SCHEMA_INIT_UNSUPPORTED")
    if schema_env.get("DATABASE_INIT_MODE") != "require-existing":
        reasons.add("IMPLICIT_SCHEMA_INIT_UNSUPPORTED")
    if isinstance(bootstrap_schema, Mapping):
        if bootstrap_schema.get("implicit_init_or_migration_from_backfill") is not False:
            reasons.add("IMPLICIT_SCHEMA_INIT_UNSUPPORTED")
        if bootstrap_schema.get("require_existing_ready_schema_before_backfill") is not True:
            reasons.add("IMPLICIT_SCHEMA_INIT_UNSUPPORTED")

    aliases = {
        runtime.get("target_alias"),
        _nested(simple, "target", "alias"),
        bootstrap.get("target_alias"),
        _nested(release, "expected_runtime", "target_alias"),
        binding.get("target_alias"),
    }
    aliases.discard(None)
    if len(aliases) != 1:
        reasons.add("TARGET_ALIAS_MISMATCH")

    runtime_classes = {
        runtime.get("runtime_class"),
        schedule.get("runtime_class"),
        _nested(release, "expected_runtime", "runtime_class"),
    }
    runtime_classes.discard(None)
    if len(runtime_classes) != 1:
        reasons.add("RELEASE_RUNTIME_IDENTITY_MISMATCH")

    image_repositories = {
        _nested(runtime, "deployment_architecture", "image"),
        simple.get("image"),
        _nested(release, "simple_deploy_v1", "image_repository"),
    }
    image_repositories.discard(None)
    if len(image_repositories) != 1:
        reasons.add("RELEASE_IMAGE_IDENTITY_MISMATCH")

    shared_shas = {
        _nested(runtime, "deployment_architecture", "shared_workflow_sha"),
        _nested(release, "simple_deploy_v1", "shared_workflow_sha"),
        _nested(binding, "lifecycle", "shared_workflow_sha"),
    }
    shared_shas.discard(None)
    if len(shared_shas) != 1:
        reasons.add("SHARED_WORKFLOW_IDENTITY_MISMATCH")

    current_source_sha = data.get("current_source_sha")
    lifecycle_role = _nested(binding, "lifecycle", "current_ordinary_release_role")
    candidate_sha = _nested(binding, "weather_source", "candidate_sha_at_reconciliation")
    snapshot_role = _nested(binding, "weather_source", "snapshot_role")
    legacy_binding = lifecycle_role == "LEGACY_SUPERSEDED" and snapshot_role == "pre_issue_140_main_anchor_only"
    if current_source_sha and candidate_sha and candidate_sha != current_source_sha and not legacy_binding:
        reasons.add("STALE_SOURCE_BINDING")

    state = "BLOCKED" if reasons else "PASS"
    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "reason_codes": sorted(reasons),
        "source_identity": {
            "repository": data.get("repository"),
            "current_source_sha": current_source_sha,
            "legacy_source_binding_recognized": legacy_binding,
        },
        "parity": {
            "compose_services": sorted(compose_services),
            "application_service": application_service,
            "public_ingest_service": public_ingest_service,
            "health_endpoint": health_endpoint,
            "readiness_endpoint": ready_endpoint,
            "database_init_mode": init_mode,
            "target_alias": next(iter(aliases)) if len(aliases) == 1 else None,
            "runtime_class": next(iter(runtime_classes)) if len(runtime_classes) == 1 else None,
            "image_repository": next(iter(image_repositories)) if len(image_repositories) == 1 else None,
            "systemd_service_unit": schedule_service_unit,
            "systemd_timer_unit": schedule_timer_unit,
            "on_calendar": schedule_calendar,
        },
        "runtime_evidence": {
            "source_parity_proven": state == "PASS",
            "runtime_deployed_proven": False,
            "runtime_healthy_proven": False,
            "host_state_observed": False,
        },
        "privacy": {
            "private_host_paths_exposed": False,
            "host_inventory_exposed": False,
            "credentials_or_secrets_exposed": False,
            "home_coordinates_exposed": False,
        },
        "authority": {
            "live_authority_granted": False,
            "runtime_mutation_performed": False,
            "production_data_mutation_performed": False,
        },
    }
