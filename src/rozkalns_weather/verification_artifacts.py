from __future__ import annotations

from collections.abc import Iterable

from .verification import ErrorPair, summarize

VERIFICATION_SUMMARY_CONTRACT = "verification-summary-v1"
VERIFICATION_SUMMARY_SCHEMA_VERSION = 1


def build_verification_summary_artifact(
    pairs: Iterable[ErrorPair],
    *,
    expected_n: int | None = None,
) -> dict[str, object]:
    """Build the versioned machine-readable envelope without changing metric primitives."""

    return {
        "schema_version": VERIFICATION_SUMMARY_SCHEMA_VERSION,
        "contract": VERIFICATION_SUMMARY_CONTRACT,
        **summarize(pairs, expected_n=expected_n),
    }
