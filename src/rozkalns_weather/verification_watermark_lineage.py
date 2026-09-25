from __future__ import annotations

from collections.abc import Mapping

from .verification_watermark import validate_verification_watermark


def watermark_report_lineage_inputs(
    evidence: Mapping[str, object],
    *,
    sample_counts: Mapping[str, int],
) -> dict[str, dict[str, object]]:
    """Return inputs accepted by report_lineage without mutating either artifact.

    The existing lineage contract already fingerprints ``sample_filters`` and
    ``sample_evidence``. Binding the watermark contract, as-of timestamp and
    exact watermark identity into those structures makes a receipt change when
    the cutoff changes, while the matched-set identity becomes the common
    sample identity consumed by report lineage.
    """

    validated = validate_verification_watermark(evidence)
    normalized_counts: dict[str, int] = {}
    for key, value in sample_counts.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("sample_counts must contain non-negative integers")
        normalized_counts[str(key)] = value
    if not normalized_counts:
        raise ValueError("sample_counts must not be empty")

    return {
        "sample_filters": {
            "watermark_contract": validated["contract"],
            "as_of_utc": validated["as_of_utc"],
            "watermark_identity_sha256": validated["watermark_identity_sha256"],
        },
        "sample_evidence": {
            "common_sample_identity_sha256": validated["matched_set_identity_sha256"],
            "sample_counts": dict(sorted(normalized_counts.items())),
        },
    }
