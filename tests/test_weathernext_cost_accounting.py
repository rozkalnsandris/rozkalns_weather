import json
from pathlib import Path

import pytest

from rozkalns_weather.weathernext_access import MAX_ALLOWED_BYTES_BILLED
from rozkalns_weather.weathernext_cost_accounting import (
    AccountingPolicy,
    BudgetThreshold,
    QueryEstimateEvidence,
    QuotaEvidence,
    evaluate_cost_quota_envelope,
)


def _budgets(*, monthly_blocking: int = 10_000_000) -> dict[str, BudgetThreshold]:
    return {
        "daily": BudgetThreshold(warning_bytes=100_000, blocking_bytes=200_000),
        "weekly": BudgetThreshold(warning_bytes=500_000, blocking_bytes=1_000_000),
        "monthly": BudgetThreshold(
            warning_bytes=min(5_000_000, monthly_blocking),
            blocking_bytes=monthly_blocking,
        ),
    }


def _policy(*, monthly_blocking: int = 10_000_000) -> AccountingPolicy:
    return AccountingPolicy(
        expected_model_version="3.0.0",
        expected_schema_fingerprint="schema-v1",
        per_query_hard_cap_bytes=10_000,
        planned_runs_per_day={"interim_48h": 20, "synoptic_360h": 4},
        budgets=_budgets(monthly_blocking=monthly_blocking),
    )


def _evidence() -> list[QueryEstimateEvidence]:
    return [
        QueryEstimateEvidence(
            plan_item_id="interim-station",
            run_class="interim_48h",
            query_role="station_0p05",
            model_version="3.0.0",
            schema_fingerprint="schema-v1",
            estimated_bytes=100,
            maximum_bytes_billed=1000,
        ),
        QueryEstimateEvidence(
            plan_item_id="interim-surface",
            run_class="interim_48h",
            query_role="surface_0p1",
            model_version="3.0.0",
            schema_fingerprint="schema-v1",
            estimated_bytes=100,
            maximum_bytes_billed=1000,
        ),
        QueryEstimateEvidence(
            plan_item_id="synoptic-station",
            run_class="synoptic_360h",
            query_role="station_0p05",
            model_version="3.0.0",
            schema_fingerprint="schema-v1",
            estimated_bytes=200,
            maximum_bytes_billed=1000,
        ),
        QueryEstimateEvidence(
            plan_item_id="synoptic-surface",
            run_class="synoptic_360h",
            query_role="surface_0p1",
            model_version="3.0.0",
            schema_fingerprint="schema-v1",
            estimated_bytes=200,
            maximum_bytes_billed=1000,
        ),
    ]


def _quota() -> QuotaEvidence:
    return QuotaEvidence(state="known_within_limit", limit_bytes=1_000_000, used_bytes=0)


def test_contract_is_source_only_and_does_not_claim_billed_cost() -> None:
    payload = json.loads(Path("contracts/weathernext-cost-quota-accounting-v1.json").read_text())
    assert payload["contract"] == "weathernext-cost-quota-accounting-v1"
    assert payload["scope"]["dry_run_estimates_only"] is True
    assert payload["scope"]["actual_billed_cost_known"] is False
    assert payload["query_requirements"]["maximum_bytes_billed_source_ceiling"] == MAX_ALLOWED_BYTES_BILLED
    assert payload["quota_state"]["hardcoded_provider_quota_defaults_allowed"] is False
    assert payload["authority"]["source_auto_full_authorizes_real_bigquery_query"] is False
    assert payload["authority"]["source_auto_full_authorizes_billing_or_quota_mutation"] is False
    assert payload["authority"]["runtime_live_authority_granted"] is False


def test_normal_envelope_passes_and_is_deterministic() -> None:
    policy = _policy()
    first = evaluate_cost_quota_envelope(policy=policy, query_evidence=_evidence(), quota=_quota())
    second = evaluate_cost_quota_envelope(
        policy=policy,
        query_evidence=list(reversed(_evidence())),
        quota=_quota(),
    )
    assert first["state"] == "PASS"
    assert first["reason_codes"] == []
    assert first["complete_estimate_evidence"] is True
    assert first["projected_bytes"] == {"daily": 5600, "weekly": 39200, "monthly": 173600}
    assert first["plan_fingerprint"] == second["plan_fingerprint"]
    assert first["actual_billed_cost_known"] is False
    assert first["currency_cost_projected"] is False
    assert first["real_query_performed"] is False
    assert first["billing_or_quota_mutation_performed"] is False


def test_one_expensive_query_is_blocked_by_its_explicit_cap() -> None:
    evidence = _evidence()
    evidence[0] = QueryEstimateEvidence(
        plan_item_id="interim-station",
        run_class="interim_48h",
        query_role="station_0p05",
        model_version="3.0.0",
        schema_fingerprint="schema-v1",
        estimated_bytes=1001,
        maximum_bytes_billed=1000,
    )
    result = evaluate_cost_quota_envelope(policy=_policy(), query_evidence=evidence, quota=_quota())
    assert result["state"] == "BLOCKED"
    assert "PER_QUERY_CAP_OVERFLOW" in result["reason_codes"]


def test_monthly_accumulation_overflow_blocks_even_when_shorter_periods_fit() -> None:
    result = evaluate_cost_quota_envelope(
        policy=_policy(monthly_blocking=150_000),
        query_evidence=_evidence(),
        quota=_quota(),
    )
    assert result["projected_bytes"]["daily"] == 5600
    assert result["projected_bytes"]["weekly"] == 39200
    assert result["projected_bytes"]["monthly"] == 173600
    assert result["period_status"]["daily"] == "PASS"
    assert result["period_status"]["weekly"] == "PASS"
    assert result["period_status"]["monthly"] == "BLOCKED"
    assert "PERIOD_BUDGET_EXCEEDED" in result["reason_codes"]


def test_missing_dry_run_estimate_fails_closed_without_zero_projection() -> None:
    evidence = _evidence()
    evidence[1] = QueryEstimateEvidence(
        plan_item_id="interim-surface",
        run_class="interim_48h",
        query_role="surface_0p1",
        model_version="3.0.0",
        schema_fingerprint="schema-v1",
        estimated_bytes=None,
        maximum_bytes_billed=1000,
    )
    result = evaluate_cost_quota_envelope(policy=_policy(), query_evidence=evidence, quota=_quota())
    assert result["state"] == "BLOCKED"
    assert result["complete_estimate_evidence"] is False
    assert result["projected_bytes"] == {"daily": None, "weekly": None, "monthly": None}
    assert "DRY_RUN_ESTIMATE_MISSING" in result["reason_codes"]


def test_missing_run_class_evidence_is_blocked() -> None:
    evidence = [item for item in _evidence() if item.run_class == "interim_48h"]
    result = evaluate_cost_quota_envelope(policy=_policy(), query_evidence=evidence, quota=_quota())
    assert result["state"] == "BLOCKED"
    assert result["complete_estimate_evidence"] is False
    assert "RUN_CLASS_ESTIMATE_MISSING" in result["reason_codes"]


def test_unknown_or_exhausted_quota_state_fails_closed() -> None:
    unknown = evaluate_cost_quota_envelope(
        policy=_policy(), query_evidence=_evidence(), quota=QuotaEvidence(state="unknown")
    )
    assert unknown["state"] == "BLOCKED"
    assert "QUOTA_STATE_UNKNOWN" in unknown["reason_codes"]
    exhausted = evaluate_cost_quota_envelope(
        policy=_policy(),
        query_evidence=_evidence(),
        quota=QuotaEvidence(state="known_within_limit", limit_bytes=10_000, used_bytes=5000),
    )
    assert exhausted["state"] == "BLOCKED"
    assert "QUOTA_EXCEEDED" in exhausted["reason_codes"]


def test_model_or_schema_plan_change_is_explicitly_blocked() -> None:
    model_changed = _evidence()
    model_changed[0] = QueryEstimateEvidence(
        plan_item_id="interim-station",
        run_class="interim_48h",
        query_role="station_0p05",
        model_version="4.0.0",
        schema_fingerprint="schema-v1",
        estimated_bytes=100,
        maximum_bytes_billed=1000,
    )
    result = evaluate_cost_quota_envelope(
        policy=_policy(), query_evidence=model_changed, quota=_quota()
    )
    assert "MODEL_VERSION_PLAN_CHANGED" in result["reason_codes"]
    schema_changed = _evidence()
    schema_changed[0] = QueryEstimateEvidence(
        plan_item_id="interim-station",
        run_class="interim_48h",
        query_role="station_0p05",
        model_version="3.0.0",
        schema_fingerprint="schema-v2",
        estimated_bytes=100,
        maximum_bytes_billed=1000,
    )
    result = evaluate_cost_quota_envelope(
        policy=_policy(), query_evidence=schema_changed, quota=_quota()
    )
    assert "SCHEMA_FINGERPRINT_PLAN_CHANGED" in result["reason_codes"]


def test_query_shape_and_maximum_bytes_billed_are_required() -> None:
    evidence = _evidence()
    evidence[0] = QueryEstimateEvidence(
        plan_item_id="interim-station",
        run_class="interim_48h",
        query_role="station_0p05",
        model_version="3.0.0",
        schema_fingerprint="schema-v1",
        estimated_bytes=100,
        maximum_bytes_billed=None,
        dry_run=False,
        partition_bounded=False,
        selected_columns_only=False,
    )
    result = evaluate_cost_quota_envelope(policy=_policy(), query_evidence=evidence, quota=_quota())
    assert result["state"] == "BLOCKED"
    assert {
        "DRY_RUN_REQUIRED",
        "MAXIMUM_BYTES_BILLED_MISSING",
        "PARTITION_BOUND_REQUIRED",
        "SELECTED_COLUMNS_REQUIRED",
    }.issubset(result["reason_codes"])


def test_policy_rejects_per_query_cap_above_existing_source_ceiling() -> None:
    with pytest.raises(ValueError):
        AccountingPolicy(
            expected_model_version="3.0.0",
            expected_schema_fingerprint="schema-v1",
            per_query_hard_cap_bytes=MAX_ALLOWED_BYTES_BILLED + 1,
            planned_runs_per_day={"interim_48h": 20, "synoptic_360h": 4},
            budgets=_budgets(),
        )


def test_accounting_output_is_privacy_safe_and_never_echoes_plan_item_identity() -> None:
    evidence = _evidence()
    evidence[0] = QueryEstimateEvidence(
        plan_item_id="private-project-private-dataset-secret",
        run_class="interim_48h",
        query_role="station_0p05",
        model_version="3.0.0",
        schema_fingerprint="schema-v1",
        estimated_bytes=100,
        maximum_bytes_billed=1000,
    )
    result = evaluate_cost_quota_envelope(policy=_policy(), query_evidence=evidence, quota=_quota())
    rendered = json.dumps(result, sort_keys=True)
    assert "private-project-private-dataset-secret" not in rendered
    assert "SELECT " not in rendered
    assert result["private_fields_exposed"] is False
    assert result["production_write_performed"] is False
    assert result["scheduler_activation_performed"] is False
