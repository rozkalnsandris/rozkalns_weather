from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from .missing_values import MissingValueEvidence
from .verification_missingness import AUDIT_CONTRACT

INTEGRATION_CONTRACT = "verification-value-missingness-v1"
VALUE_NORMALIZATION_EXCLUDED = "VALUE_NORMALIZATION_EXCLUDED"


def build_value_missingness_evidence(
    samples: Iterable[tuple[str, MissingValueEvidence]],
) -> dict[str, object]:
    """Build deterministic verification exclusion evidence.

    The caller supplies the verification sample id associated with each normalized
    provider value. Missing values are excluded; present numeric zero values remain
    eligible. No weighting, replacement or imputation is performed.
    """

    rows = sorted(samples, key=lambda item: (item[1].provider, item[0], item[1].field))
    reason_counts: Counter[str] = Counter()
    excluded: dict[str, dict[str, list[str]]] = {}
    present_n = 0

    for sample_id, evidence in rows:
        if evidence.is_missing:
            reason_counts[evidence.reason_code] += 1
            by_provider = excluded.setdefault(evidence.provider, {})
            by_provider.setdefault(evidence.reason_code, []).append(sample_id)
        else:
            present_n += 1

    normalized_excluded = {
        provider: {
            reason: sorted(sample_ids)
            for reason, sample_ids in sorted(by_reason.items())
        }
        for provider, by_reason in sorted(excluded.items())
    }
    missing_n = len(rows) - present_n
    return {
        "contract": INTEGRATION_CONTRACT,
        "normalization_contract": "missing-value-normalization-v1",
        "state": "DEGRADED" if missing_n else "PASS",
        "sample_value_n": len(rows),
        "present_value_n": present_n,
        "excluded_value_n": missing_n,
        "reason_code": VALUE_NORMALIZATION_EXCLUDED if missing_n else None,
        "normalization_reason_counts": dict(sorted(reason_counts.items())),
        "excluded_sample_ids_by_provider_and_reason": normalized_excluded,
        "automatic_weighting": False,
        "imputation_performed": False,
    }


def attach_value_missingness(
    report: Mapping[str, object],
    evidence: Mapping[str, object],
) -> dict[str, object]:
    """Attach value-normalization evidence to the canonical missingness report.

    This adapter deliberately does not rewrite the existing comparison matrix. A
    caller must mark a normalized-missing sample as verification-excluded before
    building that matrix; this attachment preserves the granular normalization
    reason codes explaining why.
    """

    if report.get("contract") != AUDIT_CONTRACT:
        raise ValueError("verification_missingness_contract_mismatch")
    if evidence.get("contract") != INTEGRATION_CONTRACT:
        raise ValueError("value_missingness_contract_mismatch")
    enriched = dict(report)
    enriched["value_normalization"] = dict(evidence)
    return enriched
