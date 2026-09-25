from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping

from .weathernext_access import MAX_ALLOWED_BYTES_BILLED

SUPPORTED_RUN_CLASSES = frozenset({"interim_48h", "synoptic_360h"})
SUPPORTED_QUOTA_STATES = frozenset({"known_within_limit", "known_exceeded", "unknown"})
PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 31}

BLOCKING_REASON_CODES = frozenset(
    {
        "DRY_RUN_REQUIRED",
        "DRY_RUN_ESTIMATE_MISSING",
        "MAXIMUM_BYTES_BILLED_MISSING",
        "MAXIMUM_BYTES_BILLED_POLICY_OVERFLOW",
        "PER_QUERY_CAP_OVERFLOW",
        "PARTITION_BOUND_REQUIRED",
        "SELECTED_COLUMNS_REQUIRED",
        "RUN_CLASS_ESTIMATE_MISSING",
        "QUOTA_STATE_UNKNOWN",
        "QUOTA_EXCEEDED",
        "PERIOD_BUDGET_EXCEEDED",
        "MODEL_VERSION_PLAN_CHANGED",
        "SCHEMA_FINGERPRINT_PLAN_CHANGED",
        "DUPLICATE_QUERY_PLAN_ITEM",
    }
)
WARNING_REASON_CODES = frozenset({"PERIOD_BUDGET_WARNING"})


@dataclass(frozen=True, slots=True)
class BudgetThreshold:
    warning_bytes: int
    blocking_bytes: int

    def __post_init__(self) -> None:
        if type(self.warning_bytes) is not int or type(self.blocking_bytes) is not int:
            raise ValueError("budget thresholds must be integer bytes")
        if not 0 < self.warning_bytes <= self.blocking_bytes:
            raise ValueError("budget thresholds require 0 < warning <= blocking")


@dataclass(frozen=True, slots=True)
class AccountingPolicy:
    expected_model_version: str
    expected_schema_fingerprint: str
    per_query_hard_cap_bytes: int
    planned_runs_per_day: Mapping[str, int]
    budgets: Mapping[str, BudgetThreshold]

    def __post_init__(self) -> None:
        if not self.expected_model_version.strip():
            raise ValueError("expected model version is required")
        if not self.expected_schema_fingerprint.strip():
            raise ValueError("expected schema fingerprint is required")
        if type(self.per_query_hard_cap_bytes) is not int or not (
            1 <= self.per_query_hard_cap_bytes <= MAX_ALLOWED_BYTES_BILLED
        ):
            raise ValueError("per-query hard cap exceeds the source ceiling")
        run_classes = set(self.planned_runs_per_day)
        if run_classes != set(SUPPORTED_RUN_CLASSES):
            raise ValueError("planned_runs_per_day must cover exactly the supported run classes")
        for count in self.planned_runs_per_day.values():
            if type(count) is not int or count < 0:
                raise ValueError("planned run counts must be non-negative integers")
        if set(self.budgets) != set(PERIOD_DAYS):
            raise ValueError("budgets must define daily, weekly and monthly thresholds")


@dataclass(frozen=True, slots=True)
class QueryEstimateEvidence:
    plan_item_id: str
    run_class: str
    query_role: str
    model_version: str
    schema_fingerprint: str
    estimated_bytes: int | None
    maximum_bytes_billed: int | None
    dry_run: bool = True
    partition_bounded: bool = True
    selected_columns_only: bool = True

    def __post_init__(self) -> None:
        if not self.plan_item_id.strip():
            raise ValueError("plan_item_id is required")
        if self.run_class not in SUPPORTED_RUN_CLASSES:
            raise ValueError("unsupported WeatherNext run class")
        if not self.query_role.strip():
            raise ValueError("query_role is required")
        if self.estimated_bytes is not None and (
            type(self.estimated_bytes) is not int or self.estimated_bytes < 0
        ):
            raise ValueError("estimated_bytes must be a non-negative integer or None")
        if self.maximum_bytes_billed is not None and (
            type(self.maximum_bytes_billed) is not int or self.maximum_bytes_billed <= 0
        ):
            raise ValueError("maximum_bytes_billed must be a positive integer or None")


@dataclass(frozen=True, slots=True)
class QuotaEvidence:
    state: str
    limit_bytes: int | None = None
    used_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.state not in SUPPORTED_QUOTA_STATES:
            raise ValueError("unknown quota evidence state")
        if self.state == "known_within_limit":
            if type(self.limit_bytes) is not int or type(self.used_bytes) is not int:
                raise ValueError("known quota state requires integer limit_bytes and used_bytes")
            if self.limit_bytes <= 0 or not 0 <= self.used_bytes <= self.limit_bytes:
                raise ValueError("invalid known quota evidence")
        elif self.limit_bytes is not None or self.used_bytes is not None:
            if self.limit_bytes is not None and (
                type(self.limit_bytes) is not int or self.limit_bytes <= 0
            ):
                raise ValueError("quota limit must be a positive integer")
            if self.used_bytes is not None and (
                type(self.used_bytes) is not int or self.used_bytes < 0
            ):
                raise ValueError("quota usage must be a non-negative integer")

    @property
    def remaining_bytes(self) -> int | None:
        if self.state != "known_within_limit":
            return None
        assert self.limit_bytes is not None and self.used_bytes is not None
        return self.limit_bytes - self.used_bytes


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _policy_identity(policy: AccountingPolicy) -> dict[str, object]:
    return {
        "expected_model_version": policy.expected_model_version,
        "expected_schema_fingerprint": policy.expected_schema_fingerprint,
        "per_query_hard_cap_bytes": policy.per_query_hard_cap_bytes,
        "planned_runs_per_day": dict(sorted(policy.planned_runs_per_day.items())),
        "period_days": dict(PERIOD_DAYS),
        "budgets": {
            period: {
                "warning_bytes": policy.budgets[period].warning_bytes,
                "blocking_bytes": policy.budgets[period].blocking_bytes,
            }
            for period in sorted(PERIOD_DAYS)
        },
    }


def _evidence_identity(items: Iterable[QueryEstimateEvidence]) -> list[dict[str, object]]:
    return sorted(
        (
            {
                "plan_item_id_sha256": hashlib.sha256(item.plan_item_id.encode()).hexdigest(),
                "run_class": item.run_class,
                "query_role": item.query_role,
                "model_version": item.model_version,
                "schema_fingerprint": item.schema_fingerprint,
                "estimated_bytes": item.estimated_bytes,
                "maximum_bytes_billed": item.maximum_bytes_billed,
                "dry_run": item.dry_run,
                "partition_bounded": item.partition_bounded,
                "selected_columns_only": item.selected_columns_only,
            }
            for item in items
        ),
        key=lambda row: (
            str(row["run_class"]),
            str(row["query_role"]),
            str(row["plan_item_id_sha256"]),
        ),
    )


def evaluate_cost_quota_envelope(
    *,
    policy: AccountingPolicy,
    query_evidence: Iterable[QueryEstimateEvidence],
    quota: QuotaEvidence,
) -> dict[str, object]:
    """Evaluate source-side WeatherNext dry-run byte evidence without executing a query.

    The result is deliberately privacy-safe: plan item identifiers are hashed only for
    the deterministic receipt identity and are not emitted. No SQL, project, dataset,
    credential, billing identifier, currency cost or raw BigQuery payload is accepted.
    """

    items = tuple(query_evidence)
    reasons: set[str] = set()
    seen_ids: set[str] = set()
    bytes_per_run_class = {run_class: 0 for run_class in SUPPORTED_RUN_CLASSES}
    complete_run_class = {run_class: False for run_class in SUPPORTED_RUN_CLASSES}
    item_counts = {run_class: 0 for run_class in SUPPORTED_RUN_CLASSES}
    complete_estimate_evidence = True

    for item in items:
        if item.plan_item_id in seen_ids:
            reasons.add("DUPLICATE_QUERY_PLAN_ITEM")
        seen_ids.add(item.plan_item_id)
        item_counts[item.run_class] += 1
        if not item.dry_run:
            reasons.add("DRY_RUN_REQUIRED")
        if not item.partition_bounded:
            reasons.add("PARTITION_BOUND_REQUIRED")
        if not item.selected_columns_only:
            reasons.add("SELECTED_COLUMNS_REQUIRED")
        if item.model_version != policy.expected_model_version:
            reasons.add("MODEL_VERSION_PLAN_CHANGED")
        if item.schema_fingerprint != policy.expected_schema_fingerprint:
            reasons.add("SCHEMA_FINGERPRINT_PLAN_CHANGED")
        if item.maximum_bytes_billed is None:
            reasons.add("MAXIMUM_BYTES_BILLED_MISSING")
        elif item.maximum_bytes_billed > policy.per_query_hard_cap_bytes:
            reasons.add("MAXIMUM_BYTES_BILLED_POLICY_OVERFLOW")
        if item.estimated_bytes is None:
            reasons.add("DRY_RUN_ESTIMATE_MISSING")
            complete_estimate_evidence = False
        else:
            bytes_per_run_class[item.run_class] += item.estimated_bytes
            if (
                item.maximum_bytes_billed is not None
                and item.estimated_bytes > item.maximum_bytes_billed
            ):
                reasons.add("PER_QUERY_CAP_OVERFLOW")
            if item.estimated_bytes > policy.per_query_hard_cap_bytes:
                reasons.add("PER_QUERY_CAP_OVERFLOW")

    for run_class in SUPPORTED_RUN_CLASSES:
        if policy.planned_runs_per_day[run_class] > 0 and item_counts[run_class] == 0:
            reasons.add("RUN_CLASS_ESTIMATE_MISSING")
            complete_estimate_evidence = False
        else:
            complete_run_class[run_class] = item_counts[run_class] > 0

    if quota.state == "unknown":
        reasons.add("QUOTA_STATE_UNKNOWN")
    elif quota.state == "known_exceeded":
        reasons.add("QUOTA_EXCEEDED")

    daily_projected: int | None = None
    period_projection: dict[str, int | None] = {period: None for period in PERIOD_DAYS}
    period_status: dict[str, str] = {period: "INCOMPLETE" for period in PERIOD_DAYS}

    if complete_estimate_evidence:
        daily_projected = sum(
            bytes_per_run_class[run_class] * policy.planned_runs_per_day[run_class]
            for run_class in SUPPORTED_RUN_CLASSES
        )
        for period, days in PERIOD_DAYS.items():
            projected = daily_projected * days
            period_projection[period] = projected
            threshold = policy.budgets[period]
            if projected > threshold.blocking_bytes:
                reasons.add("PERIOD_BUDGET_EXCEEDED")
                period_status[period] = "BLOCKED"
            elif projected >= threshold.warning_bytes:
                reasons.add("PERIOD_BUDGET_WARNING")
                period_status[period] = "WARN"
            else:
                period_status[period] = "PASS"
        remaining = quota.remaining_bytes
        if remaining is not None and daily_projected > remaining:
            reasons.add("QUOTA_EXCEEDED")

    ordered_reasons = sorted(reasons)
    if any(reason in BLOCKING_REASON_CODES for reason in reasons):
        state = "BLOCKED"
    elif any(reason in WARNING_REASON_CODES for reason in reasons):
        state = "WARN"
    else:
        state = "PASS"

    identity = {
        "contract": "weathernext-cost-quota-accounting-v1",
        "policy": _policy_identity(policy),
        "query_evidence": _evidence_identity(items),
        "quota": {
            "state": quota.state,
            "limit_bytes": quota.limit_bytes,
            "used_bytes": quota.used_bytes,
        },
    }
    return {
        "schema_version": 1,
        "contract": "weathernext-cost-quota-accounting-v1",
        "state": state,
        "reason_codes": ordered_reasons,
        "provider": "weathernext3",
        "model_version_contract": policy.expected_model_version,
        "schema_fingerprint": policy.expected_schema_fingerprint,
        "run_class_accounting": {
            run_class: {
                "query_item_count": item_counts[run_class],
                "estimate_evidence_present": complete_run_class[run_class],
                "estimated_bytes_per_run": (
                    bytes_per_run_class[run_class] if complete_run_class[run_class] else None
                ),
                "planned_runs_per_day": policy.planned_runs_per_day[run_class],
            }
            for run_class in sorted(SUPPORTED_RUN_CLASSES)
        },
        "complete_estimate_evidence": complete_estimate_evidence,
        "projected_bytes": period_projection,
        "period_status": period_status,
        "quota": {
            "state": quota.state,
            "remaining_bytes": quota.remaining_bytes,
            "hardcoded_provider_default_used": False,
        },
        "plan_fingerprint": _canonical_hash(identity),
        "dry_run_estimates_are_actual_billed_cost": False,
        "actual_billed_cost_known": False,
        "currency_cost_projected": False,
        "real_query_performed": False,
        "billing_or_quota_mutation_performed": False,
        "production_write_performed": False,
        "scheduler_activation_performed": False,
        "private_fields_exposed": False,
    }
