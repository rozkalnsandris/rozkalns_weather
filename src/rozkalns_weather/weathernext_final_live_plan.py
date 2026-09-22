"""Closed, public-safe source plan. No network, credentials, DB or host access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .locations import BENCHMARK_LOCATION

RPI5_SOURCE_SHA = "8182bb24545fd676843a9177e69177502c34214c"
NEXT_OWNER_COMMAND = (
    "AUTHORIZE RPi5_main WEATHERNEXT-PRIVATE-EXECUTION-BRIDGE "
    "CREATE-ONE-SOURCE-ISSUE-AND-DRAFT-PR NO-MERGE NO-LIVE"
)
BLOCKED = "BLOCKED_BY_EXTERNAL_SOURCE_CAPABILITY"


def build_final_live_plan() -> dict:
    def stage(identity, mode, classification, evidence, postconditions):
        return {"class": identity, "mode": mode, "source_readiness": classification,
                "source_evidence": evidence, "postconditions": postconditions,
                "authorized": False}

    return {
        "schema": "weathernext-final-live-plan.v1",
        "repository": "rozkalnsandris/rozkalns_weather",
        "issue": 125,
        "next_state": BLOCKED,
        "next_owner_command": NEXT_OWNER_COMMAND,
        "access_approval": {"state": "approved", "evidence_issue": 122,
                            "live_access_verified": False},
        "source_bindings": {
            "weather": {"resolution": "fresh_exact_merged_main_containing_this_plan",
                        "exact_sha_required": True, "exact_sha_ci_required": True,
                        "final_receipt_issue": 125},
            "rpi5": {"repository": "rozkalnsandris/RPi5_main", "reviewed_sha": RPI5_SOURCE_SHA,
                     "materializer_pr": 544, "refresh_before_owner_gate": True,
                     "changed_sha_requires_new_source_review": True},
        },
        "target": {"host_alias": "rpi5", "location_id": BENCHMARK_LOCATION.id,
                   "home_scope_enabled": False},
        "canary": {
            "HOURS": 6, "maximum_initial_hours": 6, "selected_init_count": 1,
            "MAX_BYTES_BILLED_PER_QUERY": 1073741824,
            "real_cap_policy": "smallest_defensible_cap_from_fresh_exact_query_dry_run",
            "metadata_probe_also_capped": True,
            "required_surfaces": ["0p05_station", "0p1_surface"],
            "model_version_contract": "3.0.0",
            "exact_init_time_partition_filter": True, "selected_columns_only": True,
            "dry_run_required_for_both_surfaces": True,
            "dry_run_bound_to_exact_query": True,
            "first_access_sqlite_write": False,
            "entrypoint": "rozkalns_weather.weathernext_access.read_first_access_canary",
        },
        "ordered_stages": [
            stage("private_execution_bridge", "source_prerequisite", "EXTERNAL_SOURCE_CAPABILITY_MISSING",
                  ["RPi5_main:ops/lib/deploy_executor/weather_private_bigquery_runtime_materialization.py:materialize_reviewed_runtime is not wired into LIVE execution"],
                  ["reviewed private dispatch with owner/replay/source/baseline guards",
                   "verified offline artifact staging and exact Weather application source binding",
                   "fixed entrypoints; no arbitrary shell/path/argv/environment authority"]),
            stage("weathernext_private_runtime_materialization", "mutation", "SOURCE_READY",
                  ["RPi5_main:ops/lib/deploy_executor/weather_private_bigquery_runtime_materialization.py",
                   "RPi5_main:.github/workflows/weathernext-private-runtime-source.yml"],
                  ["fresh artifact source/closure/digest/size proof", "linux/aarch64 CPython 3.13 cp313 baseline",
                   "absent target and partial staging", "matching installed marker",
                   "dependency closure alone does not install Weather application source"]),
            stage("google_auth_binding", "mutation_if_absent", "EXTERNAL_SOURCE_CAPABILITY_MISSING",
                  ["RPi5_main:ops/lib/deploy_executor/weather_private_bigquery_contract.py:execution_enabled false; class name only"],
                  ["reviewed private binding mechanism", "sanitized binding-present evidence",
                   "no credential readout or replacement; IAM changes separately authorized"]),
            stage("google_project_binding", "mutation_if_absent", "EXTERNAL_SOURCE_CAPABILITY_MISSING",
                  ["RPi5_main:ops/lib/deploy_executor/weather_private_bigquery_contract.py:execution_enabled false; class name only"],
                  ["reviewed private binding mechanism", "sanitized project-binding-present evidence"]),
            stage("analytics_hub_link_create", "mutation_if_absent", "EXTERNAL_SOURCE_CAPABILITY_MISSING",
                  ["RPi5_main:ops/lib/deploy_executor/weather_private_bigquery_contract.py:execution_enabled false; class name only"],
                  ["reviewed approved-listing linkage mechanism", "linked-dataset-present evidence",
                   "no link deletion or alternate dataset"]),
            stage("read_only_private_bigquery", "private_read_only", "SOURCE_READY",
                  ["src/rozkalns_weather/weathernext_access.py:read_first_access_canary",
                   "src/rozkalns_weather/providers/weathernext.py",
                   "tests/test_weathernext_first_access_execution.py"],
                  ["canonical gate remains issue 122", "fresh source and private bindings",
                   "linked_dataset_probe", "schema_fingerprint", "dry_run_cost_guard",
                   "bounded_canary_query", "provenance_validate", "no SQLite write"]),
            stage("production_sqlite_forecast_snapshot_write", "separate_later_mutation", "SOURCE_READY",
                  ["src/rozkalns_weather/weathernext_snapshot_admission.py:prepare_first_snapshot_run",
                   "src/rozkalns_weather/db.py:Database.insert_forecast_run"],
                  ["separate exact data authorization and trusted execution binding",
                   "validated two-surface canary and complete statistic matrix",
                   "fresh bounded candidate and schema fingerprint", "immutable snapshot idempotency",
                   "station API/PWA provenance visible; no home accuracy claim"]),
        ],
        "classification_semantics": {
            "SOURCE_READY": "reviewed executable source exists; not installed or authorized; earlier prerequisites still apply",
            "LIVE_BINDING_REQUIRED": "executable source exists; only fresh private binding/authorization remains",
            "EXTERNAL_SOURCE_CAPABILITY_MISSING": "required trusted executable connection absent; documented class is insufficient",
        },
        "verification": [
            "fresh exact Weather merged SHA and all required CI/reviews",
            "fresh reviewed RPi5 SHA and relevant source/artifact CI",
            "fresh trusted rpi5 baseline; no runtime claim from source",
            "fresh linked-schema required fingerprint equals expected contract",
            "both query estimates known, nonnegative and within explicitly frozen cap",
            "both nonempty surfaces with init/retrieval/valid/lead/model/statistic/native provenance",
            "sanitized counts/status/hash evidence only in GitHub",
            "DWD remains authoritative warning source; WeatherNext primary_research",
        ],
        "failure_policy": {
            "consume_authority_at_first_authorized_operation": True,
            "error_timeout_drift_lock_permission_schema_cost_or_health_ambiguity": "STOP",
            "automatic_retry": False, "automatic_cleanup": False, "automatic_rollback": False,
            "credential_substitution": False, "alternate_dataset": False,
            "alternate_mutation_path": False,
            "recovery_requires_separate_frozen_authority": True,
        },
        "authority": {"plan_grants_live_authority": False, "google_request_performed": False,
                      "production_mutation_performed": False, "external_repository_write": False},
    }


def validate_final_live_plan(value: object) -> dict:
    # Closed structural schema: unknown fields/strings cannot smuggle private
    # identity into a trusted plan. Do not echo rejected input in error messages.
    expected = build_final_live_plan()
    if json.dumps(value, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True):
        raise ValueError("FINAL-LIVE PLAN differs from reviewed public-safe source contract")
    return {"schema": expected["schema"], "valid": True, "next_state": BLOCKED,
            "next_owner_command": NEXT_OWNER_COMMAND, "live_authorized": False}


def bind_source_receipt(*, weather_sha: str, observed_weather_main: str,
                        rpi5_sha: str, weather_ci_pass: bool, rpi5_ci_pass: bool) -> dict:
    """Validate supplied fresh GitHub evidence; does not fetch or invent it."""
    if (not re.fullmatch(r"[0-9a-f]{40}", weather_sha)
            or weather_sha != observed_weather_main or rpi5_sha != RPI5_SOURCE_SHA
            or weather_ci_pass is not True or rpi5_ci_pass is not True):
        raise ValueError("fresh source/CI binding mismatch; re-review required")
    return {"weather_source_sha": weather_sha, "rpi5_source_sha": rpi5_sha,
            "next_state": BLOCKED, "next_owner_command": NEXT_OWNER_COMMAND,
            "runtime_verified": False, "live_authorized": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args()
    result = (validate_final_live_plan(json.loads(args.validate.read_text()))
              if args.validate else build_final_live_plan())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
