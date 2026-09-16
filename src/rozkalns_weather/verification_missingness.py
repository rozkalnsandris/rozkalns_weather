from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from typing import Iterable, Sequence

from .verification import lead_bucket

AUDIT_CONTRACT = "verification-missingness-selection-bias-v1"
AUDIT_SCHEMA_VERSION = 1
WARN_IMBALANCE_FRACTION = 0.10
BLOCKED_IMBALANCE_FRACTION = 0.25

MATCHED = "MATCHED"
UPSTREAM_FORECAST_MISSING = "UPSTREAM_FORECAST_MISSING"
TRUTH_GAP = "TRUTH_GAP"
SEMANTIC_INCOMPATIBILITY = "SEMANTIC_INCOMPATIBILITY"
VERIFICATION_FILTER_EXCLUDED = "VERIFICATION_FILTER_EXCLUDED"
PEER_COMMON_SAMPLE_EXCLUDED = "PEER_COMMON_SAMPLE_EXCLUDED"

PASS = "PASS"
WARN = "WARN"
BLOCKED = "BLOCKED"
NO_COMMON_MATCHED_SAMPLES = "NO_COMMON_MATCHED_SAMPLES"
ATTRITION_IMBALANCE_WARN = "ATTRITION_IMBALANCE_WARN"
ATTRITION_IMBALANCE_BLOCKED = "ATTRITION_IMBALANCE_BLOCKED"

_DIRECT_REASON_ORDER = (
    UPSTREAM_FORECAST_MISSING,
    TRUTH_GAP,
    SEMANTIC_INCOMPATIBILITY,
    VERIFICATION_FILTER_EXCLUDED,
)


class MissingnessAuditError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class ExpectedVerificationSample:
    sample_id: str
    provider: str
    model_version: str
    lead_hours: float
    variable: str
    valid_time_utc: str
    init_time_utc: str
    forecast_available: bool = True
    truth_available: bool = True
    semantic_compatible: bool = True
    verification_included: bool = True


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parse_utc(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MissingnessAuditError(
            "INVALID_TIMESTAMP", f"{field} must be ISO-8601 UTC"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise MissingnessAuditError("INVALID_TIMESTAMP", f"{field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _slice_key(sample: ExpectedVerificationSample) -> tuple[str, str, str, str]:
    valid = _parse_utc(sample.valid_time_utc, field="valid_time_utc")
    init = _parse_utc(sample.init_time_utc, field="init_time_utc")
    return (
        sample.variable,
        lead_bucket(sample.lead_hours),
        valid.strftime("%Y-%m"),
        init.strftime("%HZ"),
    )


def _direct_reasons(sample: ExpectedVerificationSample) -> tuple[str, ...]:
    flags = (
        not sample.forecast_available,
        not sample.truth_available,
        not sample.semantic_compatible,
        not sample.verification_included,
    )
    return tuple(code for code, active in zip(_DIRECT_REASON_ORDER, flags) if active)


def _state_rank(state: str) -> int:
    return {PASS: 0, WARN: 1, BLOCKED: 2}[state]


def _comparison_state(
    providers: Sequence[dict[str, object]], matched_n: int
) -> tuple[str, list[str], float]:
    availability = [float(row["availability_fraction"]) for row in providers]
    eligibility = [float(row["eligibility_fraction"]) for row in providers]
    imbalance = max(
        max(availability) - min(availability),
        max(eligibility) - min(eligibility),
    )
    if matched_n == 0:
        return BLOCKED, [NO_COMMON_MATCHED_SAMPLES], imbalance
    if imbalance >= BLOCKED_IMBALANCE_FRACTION:
        return BLOCKED, [ATTRITION_IMBALANCE_BLOCKED], imbalance
    if imbalance >= WARN_IMBALANCE_FRACTION:
        return WARN, [ATTRITION_IMBALANCE_WARN], imbalance
    return PASS, [], imbalance


def build_verification_missingness_report(
    samples: Iterable[ExpectedVerificationSample],
    *,
    expected_providers: Sequence[str] | None = None,
) -> dict[str, object]:
    """Return a deterministic machine-readable attrition audit.

    Every expected provider/sample cell must be explicit. A missing upstream
    forecast is represented with ``forecast_available=False``; an absent matrix
    cell is rejected because its attrition reason cannot be inferred safely.
    """

    items = list(samples)
    if not items:
        raise MissingnessAuditError(
            "NO_EXPECTED_SAMPLES", "missingness audit requires expected samples"
        )
    provider_source = (
        [item.provider for item in items]
        if expected_providers is None
        else expected_providers
    )
    providers = tuple(sorted(set(provider_source)))
    if len(providers) < 2:
        raise MissingnessAuditError(
            "INSUFFICIENT_PROVIDER_SCOPE",
            "missingness audit requires at least two expected providers",
        )
    if any(not provider for provider in providers):
        raise MissingnessAuditError("INVALID_PROVIDER", "provider must be non-empty")

    matrix: dict[
        tuple[str, str, str, str],
        dict[str, dict[str, ExpectedVerificationSample]],
    ] = {}
    for item in items:
        if item.provider not in providers:
            raise MissingnessAuditError(
                "UNEXPECTED_PROVIDER",
                f"provider {item.provider} is outside expected provider scope",
            )
        if not item.sample_id or not item.model_version or not item.variable:
            raise MissingnessAuditError(
                "INCOMPLETE_EXPECTED_SAMPLE",
                "sample_id, model_version and variable are required",
            )
        if not isfinite(float(item.lead_hours)) or item.lead_hours < 0:
            raise MissingnessAuditError(
                "INVALID_LEAD", "lead_hours must be finite and non-negative"
            )
        slice_key = _slice_key(item)
        provider_map = matrix.setdefault(slice_key, {}).setdefault(item.sample_id, {})
        if item.provider in provider_map:
            raise MissingnessAuditError(
                "DUPLICATE_EXPECTED_CELL",
                f"duplicate expected cell {item.provider}:{item.sample_id}:{slice_key}",
            )
        provider_map[item.provider] = item

    comparisons: list[dict[str, object]] = []
    overall_state = PASS
    for (variable, bucket, month, init_cycle), sample_maps in sorted(matrix.items()):
        for sample_id, provider_map in sorted(sample_maps.items()):
            missing = sorted(set(providers) - set(provider_map))
            if missing:
                raise MissingnessAuditError(
                    "INCOMPLETE_EXPECTED_MATRIX",
                    f"{sample_id} missing expected provider cells: {','.join(missing)}",
                )
            if len({provider_map[p].valid_time_utc for p in providers}) != 1:
                raise MissingnessAuditError(
                    "SAMPLE_IDENTITY_MISMATCH",
                    f"{sample_id} maps to multiple valid_time_utc values",
                )

        cohorts: dict[tuple[tuple[str, str], ...], list[str]] = {}
        for sample_id, provider_map in sorted(sample_maps.items()):
            vector = tuple(
                (provider, provider_map[provider].model_version)
                for provider in providers
            )
            cohorts.setdefault(vector, []).append(sample_id)

        for version_vector, cohort_sample_ids in sorted(cohorts.items()):
            expected_ids = sorted(cohort_sample_ids)
            cohort = dict(version_vector)
            matched_ids = [
                sample_id
                for sample_id in expected_ids
                if all(not _direct_reasons(sample_maps[sample_id][p]) for p in providers)
            ]
            matched_set_id = _fingerprint(
                {
                    "contract": AUDIT_CONTRACT,
                    "variable": variable,
                    "lead_bucket": bucket,
                    "month": month,
                    "init_cycle": init_cycle,
                    "comparison_cohort": cohort,
                    "matched_sample_ids": matched_ids,
                }
            )

            provider_rows: list[dict[str, object]] = []
            for provider in providers:
                provider_samples = [sample_maps[sample_id][provider] for sample_id in expected_ids]
                expected_n = len(provider_samples)
                available_n = sum(item.forecast_available for item in provider_samples)
                eligible_n = sum(not _direct_reasons(item) for item in provider_samples)
                reason_counts = {
                    MATCHED: 0,
                    UPSTREAM_FORECAST_MISSING: 0,
                    TRUTH_GAP: 0,
                    SEMANTIC_INCOMPATIBILITY: 0,
                    VERIFICATION_FILTER_EXCLUDED: 0,
                    PEER_COMMON_SAMPLE_EXCLUDED: 0,
                }
                excluded_ids = {
                    UPSTREAM_FORECAST_MISSING: [],
                    TRUTH_GAP: [],
                    SEMANTIC_INCOMPATIBILITY: [],
                    VERIFICATION_FILTER_EXCLUDED: [],
                    PEER_COMMON_SAMPLE_EXCLUDED: [],
                }
                direct_reasons_by_sample: dict[str, list[str]] = {}
                for sample_id in expected_ids:
                    item = sample_maps[sample_id][provider]
                    direct = list(_direct_reasons(item))
                    if direct:
                        direct_reasons_by_sample[sample_id] = direct
                    if sample_id in matched_ids:
                        reason_counts[MATCHED] += 1
                        continue
                    reason = direct[0] if direct else PEER_COMMON_SAMPLE_EXCLUDED
                    reason_counts[reason] += 1
                    excluded_ids[reason].append(sample_id)

                provider_rows.append(
                    {
                        "provider": provider,
                        "model_version": cohort[provider],
                        "expected_n": expected_n,
                        "available_n": available_n,
                        "eligible_n": eligible_n,
                        "matched_n": len(matched_ids),
                        "excluded_n": expected_n - len(matched_ids),
                        "availability_fraction": available_n / expected_n,
                        "eligibility_fraction": eligible_n / expected_n,
                        "matched_fraction": len(matched_ids) / expected_n,
                        "reason_counts": reason_counts,
                        "excluded_sample_ids_by_reason": excluded_ids,
                        "direct_reason_codes_by_sample": direct_reasons_by_sample,
                    }
                )

            state, state_reasons, imbalance = _comparison_state(
                provider_rows, len(matched_ids)
            )
            if _state_rank(state) > _state_rank(overall_state):
                overall_state = state
            comparison_id = _fingerprint(
                {
                    "contract": AUDIT_CONTRACT,
                    "variable": variable,
                    "lead_bucket": bucket,
                    "month": month,
                    "init_cycle": init_cycle,
                    "comparison_cohort": cohort,
                    "expected_sample_ids": expected_ids,
                }
            )
            comparisons.append(
                {
                    "comparison_id": comparison_id,
                    "variable": variable,
                    "lead_bucket": bucket,
                    "month": month,
                    "init_cycle": init_cycle,
                    "comparison_cohort": cohort,
                    "expected_sample_ids": expected_ids,
                    "expected_n": len(expected_ids),
                    "matched_set_id": matched_set_id,
                    "matched_sample_ids": matched_ids,
                    "matched_n": len(matched_ids),
                    "excluded_n": len(expected_ids) - len(matched_ids),
                    "state": state,
                    "state_reason_codes": state_reasons,
                    "imbalance_fraction": imbalance,
                    "providers": provider_rows,
                }
            )

    comparisons.sort(
        key=lambda row: (
            str(row["variable"]),
            str(row["lead_bucket"]),
            str(row["month"]),
            str(row["init_cycle"]),
            str(sorted(dict(row["comparison_cohort"]).items())),
        )
    )
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "contract": AUDIT_CONTRACT,
        "state": overall_state,
        "thresholds": {
            "warn_imbalance_fraction": WARN_IMBALANCE_FRACTION,
            "blocked_imbalance_fraction": BLOCKED_IMBALANCE_FRACTION,
        },
        "expected_providers": list(providers),
        "reason_code_precedence": [
            *_DIRECT_REASON_ORDER,
            PEER_COMMON_SAMPLE_EXCLUDED,
        ],
        "comparisons": comparisons,
        "automatic_weighting": False,
    }
