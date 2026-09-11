from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterable, Mapping

RUNTIME_CLASS = "public-only-rpi5"
TARGET_ALIAS = "rozkalns-weather-public-rpi5"
OPERATION_ID = "rozkalns-weather.public-runtime-release.v1"
SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
TRUTH_STATION_ID = "10416"
TRUTH_LOCATION_ID = "station_10416"
BOOTSTRAP_MODELS = ("icon_d2", "ecmwf_ifs", "ecmwf_aifs")
BOOTSTRAP_RUN_HOURS_UTC = (0, 6, 12, 18)
COMMON_BENCHMARK_START = date(2026, 4, 2)
MAX_BOOTSTRAP_INCLUSIVE_DAYS = 180
RECOVERY_DECISIONS = (
    "verified_backup_available",
    "owner_accepts_proceeding_without_prewrite_backup",
)
BOOTSTRAP_STAGE_ORDER = (
    "volume_ensure",
    "explicit_schema_init",
    "readiness_check",
    "public_smoke_read_only",
    "bounded_dwd_truth_backfill",
    "bounded_forecast_backfill",
    "corpus_integrity_check",
    "enable_recurring_public_ingest",
)
REQUIRED_EVIDENCE_PROVIDERS = (
    "dwd_mosmix_l",
    "dwd_observations",
    "icon_d2",
    "ecmwf_ifs",
    "ecmwf_aifs",
    "weathernext3",
)
REQUIRED_SQLITE_TABLES = frozenset(
    {
        "locations",
        "forecast_runs",
        "forecast_values",
        "observations",
        "provider_ingest_status",
        "model_events",
    }
)
FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {
        "home_lat",
        "home_lon",
        "credentials",
        "credential",
        "raw_logs",
        "raw_log",
        "database_path",
        "host_path",
        "env",
        "environment",
    }
)


def _load_json(root: Path, relative_path: str) -> dict[str, object]:
    path = root / relative_path
    if not path.is_file():
        raise ValueError(f"required rollout source file is missing: {relative_path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"rollout source file must contain a JSON object: {relative_path}")
    return payload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _parse_models(value: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        items = tuple(item.strip() for item in value.split(",") if item.strip())
    else:
        items = tuple(str(item).strip() for item in value if str(item).strip())
    if len(items) != len(set(items)):
        raise ValueError("bootstrap models must not contain duplicates")
    if set(items) != set(BOOTSTRAP_MODELS):
        raise ValueError(f"bootstrap models must be exactly: {','.join(BOOTSTRAP_MODELS)}")
    return BOOTSTRAP_MODELS


def _parse_run_hours(value: str | Iterable[int]) -> tuple[int, ...]:
    if isinstance(value, str):
        try:
            items = tuple(int(item.strip()) for item in value.split(",") if item.strip())
        except ValueError as exc:
            raise ValueError("run hours must be comma-separated UTC integers") from exc
    else:
        items = tuple(int(item) for item in value)
    if len(items) != len(set(items)):
        raise ValueError("bootstrap run hours must not contain duplicates")
    if set(items) != set(BOOTSTRAP_RUN_HOURS_UTC):
        raise ValueError("bootstrap run hours must be exactly 0,6,12,18 UTC")
    return BOOTSTRAP_RUN_HOURS_UTC


def validate_bootstrap_inputs(
    *,
    start: date,
    end: date,
    models: str | Iterable[str],
    run_hours_utc: str | Iterable[int],
) -> dict[str, object]:
    if end < start:
        raise ValueError("bootstrap end date must not be before start date")
    inclusive_days = (end - start).days + 1
    if inclusive_days > MAX_BOOTSTRAP_INCLUSIVE_DAYS:
        raise ValueError(f"bootstrap window exceeds {MAX_BOOTSTRAP_INCLUSIVE_DAYS} inclusive days")
    if start < COMMON_BENCHMARK_START:
        raise ValueError(f"three-model common benchmark starts at {COMMON_BENCHMARK_START.isoformat()}")
    canonical_models = _parse_models(models)
    canonical_hours = _parse_run_hours(run_hours_utc)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "inclusive_days": inclusive_days,
        "models": list(canonical_models),
        "run_hours_utc": list(canonical_hours),
        "truth_station_id": TRUTH_STATION_ID,
        "truth_location_id": TRUTH_LOCATION_ID,
        "max_inclusive_days": MAX_BOOTSTRAP_INCLUSIVE_DAYS,
    }


def validate_completed_stages(completed_stages: Iterable[str]) -> dict[str, object]:
    completed = tuple(str(stage) for stage in completed_stages)
    if len(completed) != len(set(completed)):
        raise ValueError("completed bootstrap stages must not contain duplicates")
    expected_prefix = BOOTSTRAP_STAGE_ORDER[: len(completed)]
    if completed != expected_prefix:
        raise ValueError("completed bootstrap stages must form an exact ordered prefix; skipping or reordering stages is forbidden")
    next_stage = BOOTSTRAP_STAGE_ORDER[len(completed)] if len(completed) < len(BOOTSTRAP_STAGE_ORDER) else None
    return {
        "completed_stages": list(completed),
        "next_stage": next_stage,
        "complete": next_stage is None,
        "hidden_retry_allowed": False,
        "implicit_stage_advance_allowed": False,
    }


def validate_source_package(root: Path | None = None) -> dict[str, object]:
    root = root or Path.cwd()
    descriptor = _load_json(root, "deploy/runtime-descriptor.json")
    readiness = _load_json(root, "deploy/rollout-readiness.json")
    source_binding = _load_json(root, "deploy/rpi5-source-binding.json")
    first_live_preflight = _load_json(root, "deploy/first-public-rollout-preflight.json")
    production_bootstrap = _load_json(root, "deploy/production-public-corpus-bootstrap.json")
    schedule = _load_json(root, "deploy/public-ingest-schedule.json")
    compose_path = root / "deploy/docker-compose.public.yml"
    if not compose_path.is_file():
        raise ValueError("required rollout source file is missing: deploy/docker-compose.public.yml")
    compose = compose_path.read_text(encoding="utf-8")

    _require(descriptor.get("runtime_class") == RUNTIME_CLASS, "runtime descriptor class mismatch")
    _require(descriptor.get("target_alias") == TARGET_ALIAS, "runtime descriptor target mismatch")
    _require(descriptor.get("operation_id_candidate") == OPERATION_ID, "runtime descriptor operation mismatch")
    rollout_refs = descriptor.get("rollout_readiness")
    _require(isinstance(rollout_refs, dict), "runtime rollout references missing")
    assert isinstance(rollout_refs, dict)
    _require(rollout_refs.get("production_public_corpus_bootstrap_descriptor") == "deploy/production-public-corpus-bootstrap.json", "runtime production bootstrap descriptor reference mismatch")
    runtime_contract = descriptor.get("runtime_contract")
    _require(isinstance(runtime_contract, dict), "runtime descriptor contract missing")
    assert isinstance(runtime_contract, dict)
    _require(runtime_contract.get("runtime_mode") == "public-only", "runtime must be public-only")
    _require(runtime_contract.get("database_init_mode") == "require-existing", "database init mode must be require-existing")
    persistent = descriptor.get("persistent_data")
    _require(isinstance(persistent, dict), "persistent data contract missing")
    assert isinstance(persistent, dict)
    _require(persistent.get("logical_name") == "weather_data", "persistent volume identity mismatch")
    _require(persistent.get("implicit_backfill_on_start") is False, "implicit backfill must remain disabled")
    _require(persistent.get("corpus_deletion_allowed") is False, "corpus deletion must remain disabled")

    _require(readiness.get("schema_version") == 1, "rollout readiness schema mismatch")
    _require(readiness.get("runtime_class") == RUNTIME_CLASS, "rollout readiness class mismatch")
    _require(readiness.get("target_alias") == TARGET_ALIAS, "rollout readiness target mismatch")
    _require(readiness.get("operation_id") == OPERATION_ID, "rollout readiness operation mismatch")
    bootstrap = readiness.get("bootstrap_contract")
    _require(isinstance(bootstrap, dict), "bootstrap contract missing")
    assert isinstance(bootstrap, dict)
    _require(bootstrap.get("truth_station_id") == TRUTH_STATION_ID, "bootstrap truth station mismatch")
    _require(tuple(bootstrap.get("models", [])) == BOOTSTRAP_MODELS, "bootstrap model contract mismatch")
    _require(tuple(bootstrap.get("run_hours_utc", [])) == BOOTSTRAP_RUN_HOURS_UTC, "bootstrap run-hour contract mismatch")
    _require(bootstrap.get("max_inclusive_days") == MAX_BOOTSTRAP_INCLUSIVE_DAYS, "bootstrap window contract mismatch")
    _require(tuple(bootstrap.get("stage_order", [])) == BOOTSTRAP_STAGE_ORDER, "bootstrap stage order mismatch")
    _require(bootstrap.get("production_corpus_bootstrap_descriptor") == "deploy/production-public-corpus-bootstrap.json", "rollout production bootstrap descriptor reference mismatch")

    _require(source_binding.get("contract") == "rozkalns-weather.rpi5-source-binding.v1", "RPi5 source binding contract mismatch")
    _require(source_binding.get("status") == "SOURCE_RECONCILED_RUNTIME_UNPROVEN", "RPi5 source binding must remain runtime-unproven")
    _require(source_binding.get("target_alias") == TARGET_ALIAS, "RPi5 source binding target mismatch")
    _require(source_binding.get("operation_id") == OPERATION_ID, "RPi5 source binding operation mismatch")
    weather_binding = source_binding.get("weather_source")
    rpi_binding = source_binding.get("rpi5_main_source")
    source_safety = source_binding.get("source_safety")
    legacy_checkout = source_binding.get("legacy_checkout")
    research_safety = source_binding.get("research_and_safety")
    _require(isinstance(weather_binding, dict), "Weather source binding missing")
    _require(isinstance(rpi_binding, dict), "RPi5 source snapshot missing")
    _require(isinstance(source_safety, dict), "RPi5 source safety contract missing")
    _require(isinstance(legacy_checkout, dict), "legacy checkout evidence contract missing")
    _require(isinstance(research_safety, dict), "research safety contract missing")
    assert isinstance(weather_binding, dict) and isinstance(rpi_binding, dict)
    assert isinstance(source_safety, dict) and isinstance(legacy_checkout, dict) and isinstance(research_safety, dict)
    _require(bool(SOURCE_SHA_PATTERN.fullmatch(str(weather_binding.get("candidate_sha_at_reconciliation", "")))), "Weather source binding SHA invalid")
    _require(bool(SOURCE_SHA_PATTERN.fullmatch(str(rpi_binding.get("main_sha_at_reconciliation", "")))), "RPi5 source binding SHA invalid")
    for field in ("source_merge_authorizes_live", "source_merge_proves_host_ready", "source_merge_proves_deployment", "operator_host_installed", "helper_installation_enabled", "operator_installation_enabled", "privileged_install_invocation_enabled", "production_mutation_enabled", "production_mutation_started"):
        _require(source_safety.get(field) is False, f"source binding safety flag must remain false: {field}")
    _require(source_safety.get("fresh_human_composite_strict_live_authorization_required") is True, "fresh Composite STRICT LIVE authorization must remain required")
    _require(source_safety.get("fresh_sanitized_runtime_baseline_required") is True, "fresh sanitized runtime baseline must remain required")
    _require(legacy_checkout.get("historical_evidence_only") is True, "legacy checkout must remain evidence-only")
    _require(legacy_checkout.get("authority_source") is False, "legacy checkout cannot be an authority source")
    _require(legacy_checkout.get("mutation_allowed") is False, "legacy checkout mutation must remain forbidden")
    _require(research_safety.get("dwd_severe_weather_warning_authority") == "DWD", "DWD warning authority drifted")
    _require(research_safety.get("weathernext3_role") == "primary_research", "WeatherNext 3 research role drifted")
    _require(research_safety.get("weathernext_real_values_fabricated") is False, "WeatherNext values must never be fabricated")

    _require(first_live_preflight.get("contract") == "rozkalns-weather.first-public-rollout-preflight.v1", "first public rollout preflight contract mismatch")
    _require(first_live_preflight.get("runtime_class") == RUNTIME_CLASS, "first public rollout preflight runtime class mismatch")
    _require(first_live_preflight.get("target_alias") == TARGET_ALIAS, "first public rollout preflight target mismatch")
    _require(first_live_preflight.get("operation_id") == OPERATION_ID, "first public rollout preflight operation mismatch")
    _require(first_live_preflight.get("host_alias") == "rpi5", "first public rollout preflight host mismatch")
    pf_queue = first_live_preflight.get("deploy_queue")
    pf_rpi = first_live_preflight.get("rpi5_contracts")
    pf_bootstrap = first_live_preflight.get("bootstrap")
    pf_recovery = first_live_preflight.get("recovery")
    pf_budgets = first_live_preflight.get("mutation_budgets")
    pf_result = first_live_preflight.get("machine_result")
    pf_authority = first_live_preflight.get("authority")
    pf_next_gate = first_live_preflight.get("next_owner_live_gate")
    for label, value in (("queue", pf_queue), ("RPi5 contracts", pf_rpi), ("bootstrap", pf_bootstrap), ("recovery", pf_recovery), ("budgets", pf_budgets), ("result", pf_result), ("authority", pf_authority), ("next LIVE gate", pf_next_gate)):
        _require(isinstance(value, dict), f"first public rollout preflight {label} contract missing")
    assert isinstance(pf_queue, dict) and isinstance(pf_rpi, dict) and isinstance(pf_bootstrap, dict)
    assert isinstance(pf_recovery, dict) and isinstance(pf_budgets, dict) and isinstance(pf_result, dict)
    assert isinstance(pf_authority, dict) and isinstance(pf_next_gate, dict)
    _require(pf_queue.get("repository") == "rozkalnsandris/ops-workflows" and pf_queue.get("issue") == 46, "first public rollout queue identity mismatch")
    _require(pf_queue.get("eligibility_only") is True and pf_queue.get("grants_live_authority") is False, "READY queue must remain eligibility-only")
    _require(pf_queue.get("queue_refresh_authorized_by_this_source_issue") is False, "Weather source issue cannot authorize queue refresh")
    _require(pf_rpi.get("operator_artifact_count") == 23, "operator install artifact count mismatch")
    _require(pf_rpi.get("helper_artifact_count") == 13, "helper install artifact count mismatch")
    _require(pf_rpi.get("operator_installer_status") == "SOURCE_ONLY_INSTALLER_BRIDGE_INACTIVE", "operator installer source must remain inactive")
    parsed_pf_bootstrap = validate_bootstrap_inputs(
        start=date.fromisoformat(str(pf_bootstrap.get("start_date"))),
        end=date.fromisoformat(str(pf_bootstrap.get("end_date"))),
        models=pf_bootstrap.get("models", []),
        run_hours_utc=pf_bootstrap.get("run_hours_utc", []),
    )
    _require(parsed_pf_bootstrap.get("inclusive_days") == pf_bootstrap.get("inclusive_days") == 162, "first rollout bootstrap inclusive-day contract mismatch")
    _require(pf_recovery.get("required") is True and pf_recovery.get("source_default") is None, "recovery decision must remain explicit and owner-bound")
    _require(tuple(pf_recovery.get("allowed_weather_values", [])) == RECOVERY_DECISIONS, "recovery decision contract mismatch")
    expected_release_budget = [
        {"category": "filesystem.release-materialization", "max_operations": 1},
        {"category": "docker.named-volume-ensure", "max_operations": 1},
        {"category": "docker.compose-build", "max_operations": 1},
        {"category": "docker.compose-application-apply", "max_operations": 1},
        {"category": "systemd.public-ingest-schedule-install-or-update", "max_operations": 1},
    ]
    expected_supplemental_budget = [
        {"category": "git.trusted-checkout-fetch", "max_operations": 1},
        {"category": "git.trusted-checkout-worktree-add", "max_operations": 1},
        {"category": "filesystem.weather-helper-install-transaction", "max_operations": 1},
        {"category": "filesystem.weather-helper-activation-publish", "max_operations": 1},
        {"category": "sqlite.schema-init", "max_operations": 1},
        {"category": "sqlite.corpus-truth-backfill", "max_operations": 1},
        {"category": "sqlite.corpus-forecast-backfill", "max_operations": 3},
    ]
    expected_read_only_budget = [
        {"stage_id": "readiness_schema_privacy", "max_operations": 1},
        {"stage_id": "public_smoke_read_only", "max_operations": 1},
        {"stage_id": "corpus_integrity_check", "max_operations": 3},
    ]
    _require(pf_budgets.get("release") == expected_release_budget, "release mutation budget mismatch")
    _require(pf_budgets.get("supplemental") == expected_supplemental_budget, "supplemental mutation budget mismatch")
    _require(pf_budgets.get("read_only") == expected_read_only_budget, "read-only stage budget mismatch")
    _require(pf_result.get("states") == ["PASS", "BLOCKED"] and pf_result.get("pass_requires_zero_block_reasons") is True, "preflight PASS/BLOCKED result contract mismatch")
    _require(pf_result.get("live_authority_granted") is False and pf_result.get("authorization_consumed") is False, "source preflight must not grant or consume LIVE authority")
    for field in ("source_auto_full_authorizes_live", "source_merge_authorizes_live", "source_preflight_creates_live_authorization", "source_preflight_consumes_live_authorization", "source_preflight_performs_runtime_mutation"):
        _require(pf_authority.get(field) is False, f"first public rollout authority flag must remain false: {field}")
    _require(pf_next_gate.get("name") == "INSTALL_WEATHER_PUBLIC_RUNTIME_OPERATOR", "next owner LIVE gate identity mismatch")
    _require(pf_next_gate.get("artifact_count") == 23 and pf_next_gate.get("created_by_this_source_issue") is False and pf_next_gate.get("consumed_by_this_source_issue") is False, "next owner LIVE gate must remain uncreated and unconsumed")

    _require(production_bootstrap.get("contract") == "rozkalns-weather.production-public-corpus-bootstrap.v1", "production bootstrap contract mismatch")
    _require(production_bootstrap.get("status") == "SOURCE_READY_DATA_WRITE_NOT_AUTHORIZED", "production bootstrap status mismatch")
    pb_window = production_bootstrap.get("first_window")
    pb_forecast = production_bootstrap.get("forecast_scope")
    pb_truth = production_bootstrap.get("truth_scope")
    pb_schema = production_bootstrap.get("schema_init")
    pb_recovery = production_bootstrap.get("recovery")
    pb_destructive = production_bootstrap.get("destructive_behavior")
    pb_authority = production_bootstrap.get("authority")
    for label, value in (("window", pb_window), ("forecast", pb_forecast), ("truth", pb_truth), ("schema", pb_schema), ("recovery", pb_recovery), ("destructive", pb_destructive), ("authority", pb_authority)):
        _require(isinstance(value, dict), f"production bootstrap {label} contract missing")
    assert isinstance(pb_window, dict) and isinstance(pb_forecast, dict) and isinstance(pb_truth, dict)
    assert isinstance(pb_schema, dict) and isinstance(pb_recovery, dict) and isinstance(pb_destructive, dict) and isinstance(pb_authority, dict)
    _require(pb_window.get("start_date") == "2026-04-02" and pb_window.get("end_date") == "2026-09-10", "production bootstrap first window mismatch")
    _require(pb_window.get("inclusive_days") == 162 and pb_window.get("max_inclusive_days") == MAX_BOOTSTRAP_INCLUSIVE_DAYS, "production bootstrap window bounds mismatch")
    _require(tuple(pb_forecast.get("models", [])) == BOOTSTRAP_MODELS and tuple(pb_forecast.get("run_hours_utc", [])) == BOOTSTRAP_RUN_HOURS_UTC, "production bootstrap forecast scope mismatch")
    _require(pb_truth.get("chunk_days") == 14 and pb_truth.get("source_authority") == "DWD" and pb_truth.get("nearest_station_fallback_allowed") is False, "production bootstrap truth scope mismatch")
    _require(pb_schema.get("implicit_init_or_migration_from_backfill") is False and pb_schema.get("require_existing_ready_schema_before_backfill") is True, "production bootstrap schema separation mismatch")
    _require(tuple(pb_recovery.get("allowed_decisions", [])) == RECOVERY_DECISIONS, "production bootstrap recovery choices mismatch")
    for field in ("automatic_restore_allowed", "automatic_delete_allowed", "automatic_cleanup_allowed"):
        _require(pb_recovery.get(field) is False, f"production bootstrap recovery flag must remain false: {field}")
    for field in ("delete_allowed", "restore_allowed", "implicit_migration_allowed", "automatic_repair_allowed"):
        _require(pb_destructive.get(field) is False, f"production bootstrap destructive flag must remain false: {field}")
    _require(pb_authority.get("source_auto_full_authorizes_production_write") is False and pb_authority.get("source_merge_authorizes_production_write") is False, "source must not authorize production corpus writes")
    _require(pb_authority.get("production_sqlite_or_corpus_write_requires_separate_exact_live_data_authority") is True, "separate production data authority must remain required")

    _require(schedule.get("runtime_class") == RUNTIME_CLASS, "schedule runtime class mismatch")
    systemd = schedule.get("systemd_timer")
    _require(isinstance(systemd, dict), "systemd timer handoff contract missing")
    assert isinstance(systemd, dict)
    _require(systemd.get("timer_unit") == "rozkalns-weather-public-ingest.timer", "timer unit identity mismatch")
    _require(systemd.get("service_unit") == "rozkalns-weather-public-ingest.service", "service unit identity mismatch")
    _require(systemd.get("on_calendar") == "*:0/30", "timer cadence mismatch")
    _require(systemd.get("persistent") is True, "timer Persistent semantics must be enabled")
    _require(systemd.get("randomized_delay_seconds") == 60, "timer jitter contract mismatch")
    _require(systemd.get("enable_order") == "last_after_corpus_integrity", "timer must be enabled last")
    weathernext = schedule.get("weathernext")
    _require(isinstance(weathernext, dict) and weathernext.get("enabled") is False, "WeatherNext scheduling must remain disabled")

    fixed_tokens = (
        'command: ["rozkalns-weather", "init-database"]',
        'command: ["rozkalns-weather", "ingest-public"]',
        'command: ["rozkalns-weather", "readiness"]',
        'command: ["rozkalns-weather", "corpus-check"]',
        "DATABASE_INIT_MODE: require-existing",
        "WEATHER_RUNTIME_MODE: public-only",
        "weather_data:/app/data",
        "no-new-privileges:true",
        "cap_drop:",
        "/ready",
    )
    for token in fixed_tokens:
        _require(token in compose, f"compose contract missing fixed token: {token}")
    for forbidden in ("env_file:", "HOME_LAT", "HOME_LON", "depends_on:"):
        _require(forbidden not in compose, f"compose contract contains forbidden implicit/private wiring: {forbidden}")

    return {
        "ok": True,
        "validated_files": [
            "deploy/runtime-descriptor.json",
            "deploy/rollout-readiness.json",
            "deploy/rpi5-source-binding.json",
            "deploy/first-public-rollout-preflight.json",
            "deploy/production-public-corpus-bootstrap.json",
            "deploy/public-ingest-schedule.json",
            "deploy/docker-compose.public.yml",
        ],
        "runtime_class": RUNTIME_CLASS,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "host_private_paths_exposed": False,
        },
    }


def _bootstrap_fingerprint(
    *,
    source_sha: str,
    bootstrap: Mapping[str, object],
    recovery_decision: str,
) -> str:
    payload = {
        "source_sha": source_sha,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "bootstrap": dict(bootstrap),
        "recovery_decision": recovery_decision,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_rollout_plan(
    *,
    source_sha: str,
    start: date,
    end: date,
    models: str | Iterable[str],
    run_hours_utc: str | Iterable[int],
    recovery_decision: str,
    completed_stages: Iterable[str] = (),
    root: Path | None = None,
) -> dict[str, object]:
    if not SOURCE_SHA_PATTERN.fullmatch(source_sha):
        raise ValueError("source SHA must be an exact lowercase 40-character commit SHA")
    if recovery_decision not in RECOVERY_DECISIONS:
        raise ValueError("unsupported recovery decision")
    package = validate_source_package(root)
    bootstrap = validate_bootstrap_inputs(start=start, end=end, models=models, run_hours_utc=run_hours_utc)
    stage_state = validate_completed_stages(completed_stages)
    fingerprint = _bootstrap_fingerprint(source_sha=source_sha, bootstrap=bootstrap, recovery_decision=recovery_decision)
    return {
        "schema_version": 1,
        "state": "source_preflight_ready",
        "source_identity": {
            "sha": source_sha,
            "must_be_merged_to_main": True,
            "exact_sha_ci_required": True,
            "main_membership_verified_by_this_command": False,
        },
        "runtime_class": RUNTIME_CLASS,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "package_validation": package,
        "bootstrap": bootstrap,
        "bootstrap_fingerprint": fingerprint,
        "stage_state": stage_state,
        "recovery": {
            "decision": recovery_decision,
            "automatic_restore_allowed": False,
            "automatic_delete_or_cleanup_allowed": False,
            "application_rollback_implies_sqlite_rollback": False,
        },
        "mutation_classes": {
            "application_release": "docker.compose-application-apply",
            "volume_ensure": "docker.named-volume-ensure",
            "explicit_schema_init": "sqlite.schema-init",
            "bounded_dwd_truth_backfill": "historical.public-corpus-backfill",
            "bounded_forecast_backfill": "historical.public-corpus-backfill",
            "enable_recurring_public_ingest": "systemd.public-ingest-schedule-install-or-update",
        },
        "live_authority_granted": False,
        "production_data_authority_granted": False,
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
            "host_private_paths_exposed": False,
            "raw_logs_exposed": False,
        },
    }


def verify_sqlite_backup(backup_path: Path) -> dict[str, object]:
    if not backup_path.is_file():
        raise ValueError("backup file does not exist")
    digest = hashlib.sha256()
    with backup_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    try:
        with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as connection:
            integrity = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
    except sqlite3.DatabaseError as exc:
        raise ValueError("backup is not a readable SQLite database") from exc
    missing = sorted(REQUIRED_SQLITE_TABLES - tables)
    return {
        "schema_version": 1,
        "state": "verified" if integrity == ["ok"] and not missing else "invalid",
        "integrity_ok": integrity == ["ok"],
        "required_tables_present": not missing,
        "missing_tables": missing,
        "sha256": digest.hexdigest(),
        "size_bytes": backup_path.stat().st_size,
        "path_exposed": False,
    }


def _walk_evidence(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_EVIDENCE_KEYS:
                raise ValueError(f"evidence contains forbidden private field: {key}")
            _walk_evidence(item)
    elif isinstance(value, list):
        for item in value:
            _walk_evidence(item)
    elif isinstance(value, str):
        lowered = value.lower()
        if lowered.startswith("/home/") or lowered.startswith("/opt/") or lowered.startswith("/root/"):
            raise ValueError("evidence contains a host-private path")


def validate_post_rollout_evidence(payload: Mapping[str, object]) -> dict[str, object]:
    _walk_evidence(payload)
    source_sha = str(payload.get("source_sha", ""))
    if not SOURCE_SHA_PATTERN.fullmatch(source_sha):
        raise ValueError("evidence source SHA is invalid")
    _require(payload.get("target_alias") == TARGET_ALIAS, "evidence target mismatch")
    _require(payload.get("operation_id") == OPERATION_ID, "evidence operation mismatch")
    _require(payload.get("runtime_mode") == "public-only", "evidence runtime mode mismatch")
    _require(payload.get("storage_class") == "docker_named_volume", "evidence storage class mismatch")
    _require(payload.get("weather_data_retained") is True, "persistent weather_data retention not proven")

    endpoints = payload.get("endpoints")
    _require(isinstance(endpoints, Mapping), "endpoint evidence missing")
    assert isinstance(endpoints, Mapping)
    for key in ("health_status", "ready_status", "provider_health_status"):
        _require(endpoints.get(key) == 200, f"endpoint postcondition failed: {key}")

    readiness = payload.get("readiness")
    _require(isinstance(readiness, Mapping), "readiness evidence missing")
    assert isinstance(readiness, Mapping)
    _require(readiness.get("ready") is True, "runtime readiness is not true")
    _require(readiness.get("database_state") == "ready", "database schema readiness not proven")
    _require(readiness.get("storage_class") == "persistent_sqlite_file", "SQLite storage class mismatch")
    for key in ("coordinates_exposed", "credentials_exposed", "database_path_exposed"):
        _require(readiness.get(key) is False, f"privacy postcondition failed: {key}")

    corpus = payload.get("corpus_integrity")
    _require(isinstance(corpus, Mapping) and corpus.get("ok") is True, "corpus integrity postcondition failed")

    providers = payload.get("providers")
    _require(isinstance(providers, list), "provider freshness evidence missing")
    provider_map = {
        str(item.get("id")): item
        for item in providers
        if isinstance(item, Mapping) and item.get("id") is not None
    }
    missing_providers = [provider for provider in REQUIRED_EVIDENCE_PROVIDERS if provider not in provider_map]
    _require(not missing_providers, f"provider evidence missing: {','.join(missing_providers)}")
    for provider in REQUIRED_EVIDENCE_PROVIDERS:
        state = str(provider_map[provider].get("state", ""))
        _require(bool(state), f"provider state missing: {provider}")

    weathernext = provider_map["weathernext3"]
    _require(weathernext.get("required_for_runtime") is False, "WeatherNext must remain optional in public-only runtime")
    _require(weathernext.get("values_fabricated") is False, "WeatherNext values must never be fabricated")

    return {
        "schema_version": 1,
        "state": "verified",
        "source_sha": source_sha,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "providers": [
            {"id": provider, "state": str(provider_map[provider].get("state"))}
            for provider in REQUIRED_EVIDENCE_PROVIDERS
        ],
        "privacy": {
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
            "host_private_paths_exposed": False,
            "raw_logs_exposed": False,
        },
    }
