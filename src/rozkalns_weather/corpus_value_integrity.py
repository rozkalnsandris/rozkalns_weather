from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from .missing_values import MissingValueEvidence, normalize_missing_value

CORPUS_VALUE_INTEGRITY_CONTRACT = "corpus-value-integrity-v1"


def _audit_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    source_kind: str,
    provider_field: str,
    provider_sentinels: Mapping[str, tuple[object, ...]] | None = None,
) -> tuple[list[dict[str, object]], Counter[str]]:
    sentinels = provider_sentinels or {}
    findings: list[dict[str, object]] = []
    reason_counts: Counter[str] = Counter()

    for index, row in enumerate(rows):
        provider = str(row.get(provider_field) or "unknown")
        field_present = "value" in row
        evidence: MissingValueEvidence = normalize_missing_value(
            row.get("value"),
            provider=provider,
            field="value",
            field_present=field_present,
            provider_sentinels=sentinels.get(provider, ()),
        )
        if not evidence.is_missing:
            continue
        reason_counts[evidence.reason_code] += 1
        findings.append(
            {
                "source_kind": source_kind,
                "row_index": index,
                "provider": provider,
                "variable": row.get("variable"),
                "reason_code": evidence.reason_code,
                "missing_class": evidence.missing_class,
                "raw_type": evidence.raw_type,
                "raw_token": evidence.raw_token,
            }
        )
    return findings, reason_counts


def audit_corpus_values(
    *,
    forecast_values: Iterable[Mapping[str, object]],
    observations: Iterable[Mapping[str, object]],
    forecast_provider_sentinels: Mapping[str, tuple[object, ...]] | None = None,
    observation_provider_sentinels: Mapping[str, tuple[object, ...]] | None = None,
) -> dict[str, object]:
    """Audit already-retrieved corpus value rows without repair or mutation."""

    forecast_findings, forecast_counts = _audit_rows(
        forecast_values,
        source_kind="forecast_value",
        provider_field="provider",
        provider_sentinels=forecast_provider_sentinels,
    )
    observation_findings, observation_counts = _audit_rows(
        observations,
        source_kind="observation",
        provider_field="source_provider",
        provider_sentinels=observation_provider_sentinels,
    )
    findings = sorted(
        [*forecast_findings, *observation_findings],
        key=lambda row: (
            str(row["source_kind"]),
            str(row["provider"]),
            str(row.get("variable") or ""),
            int(row["row_index"]),
        ),
    )
    combined = forecast_counts + observation_counts
    return {
        "contract": CORPUS_VALUE_INTEGRITY_CONTRACT,
        "normalization_contract": "missing-value-normalization-v1",
        "state": "BLOCKED" if findings else "PASS",
        "block_reason_codes": sorted(combined),
        "reason_counts": dict(sorted(combined.items())),
        "finding_count": len(findings),
        "findings": findings,
        "read_only": True,
        "repair_performed": False,
        "imputation_performed": False,
    }
