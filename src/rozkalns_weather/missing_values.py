from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Iterable

CONTRACT_VERSION = "missing-value-normalization-v1"

PRESENT = "PRESENT"
ABSENT_FIELD = "ABSENT_FIELD"
UPSTREAM_NULL = "UPSTREAM_NULL"
NON_FINITE_NUMERIC = "NON_FINITE_NUMERIC"
PROVIDER_SENTINEL = "PROVIDER_SENTINEL"
TRANSPORT_PARSE_OMISSION = "TRANSPORT_PARSE_OMISSION"

REASON_PRESENT = "VALUE_PRESENT"
REASON_ABSENT_FIELD = "MISSING_ABSENT_FIELD"
REASON_UPSTREAM_NULL = "MISSING_UPSTREAM_NULL"
REASON_NON_FINITE_NUMERIC = "MISSING_NON_FINITE_NUMERIC"
REASON_PROVIDER_SENTINEL = "MISSING_PROVIDER_SENTINEL"
REASON_TRANSPORT_PARSE_OMISSION = "MISSING_TRANSPORT_PARSE_OMISSION"

_MISSING_REASON_BY_CLASS = {
    ABSENT_FIELD: REASON_ABSENT_FIELD,
    UPSTREAM_NULL: REASON_UPSTREAM_NULL,
    NON_FINITE_NUMERIC: REASON_NON_FINITE_NUMERIC,
    PROVIDER_SENTINEL: REASON_PROVIDER_SENTINEL,
    TRANSPORT_PARSE_OMISSION: REASON_TRANSPORT_PARSE_OMISSION,
}


@dataclass(frozen=True, slots=True)
class MissingValueEvidence:
    provider: str
    field: str
    state: str
    missing_class: str | None
    reason_code: str
    raw_type: str
    raw_token: str | None
    numeric_value: float | None
    field_present: bool
    transport_omitted: bool
    imputed: bool = False

    @property
    def is_missing(self) -> bool:
        return self.state == "missing"

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": CONTRACT_VERSION,
            "provider": self.provider,
            "field": self.field,
            "state": self.state,
            "missing_class": self.missing_class,
            "reason_code": self.reason_code,
            "raw_type": self.raw_type,
            "raw_token": self.raw_token,
            "numeric_value": self.numeric_value,
            "field_present": self.field_present,
            "transport_omitted": self.transport_omitted,
            "imputed": self.imputed,
        }


class MissingValueError(ValueError):
    def __init__(self, evidence: MissingValueEvidence) -> None:
        self.evidence = evidence
        self.reason_code = evidence.reason_code
        super().__init__(f"{evidence.reason_code}:{evidence.provider}:{evidence.field}")


def _raw_token(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Real):
        number = float(value)
        if not isfinite(number):
            if number != number:
                return "NaN"
            return "+Inf" if number > 0 else "-Inf"
        return repr(value)
    if isinstance(value, str):
        return value
    return repr(value)


def _matches_sentinel(value: object, sentinels: Iterable[object]) -> bool:
    for sentinel in sentinels:
        if isinstance(value, str) and isinstance(sentinel, str):
            if value.strip().casefold() == sentinel.strip().casefold():
                return True
            continue
        if isinstance(value, bool) or isinstance(sentinel, bool):
            if value is sentinel:
                return True
            continue
        if isinstance(value, Real) and isinstance(sentinel, Real):
            candidate = float(value)
            expected = float(sentinel)
            if isfinite(candidate) and isfinite(expected) and candidate == expected:
                return True
    return False


def normalize_missing_value(
    value: object,
    *,
    provider: str,
    field: str,
    field_present: bool = True,
    transport_omitted: bool = False,
    provider_sentinels: Iterable[object] = (),
) -> MissingValueEvidence:
    """Classify missingness without inventing a replacement value.

    Sentinel values are caller/provider contract data. This module deliberately
    has no global sentinel registry because sentinel meaning is provider- and
    field-specific and must not be guessed.
    """

    if not provider or not field:
        raise ValueError("provider and field must be non-empty")

    missing_class: str | None = None
    if transport_omitted:
        missing_class = TRANSPORT_PARSE_OMISSION
    elif not field_present:
        missing_class = ABSENT_FIELD
    elif value is None:
        missing_class = UPSTREAM_NULL
    elif isinstance(value, Real) and not isinstance(value, bool) and not isfinite(float(value)):
        missing_class = NON_FINITE_NUMERIC
    elif _matches_sentinel(value, provider_sentinels):
        missing_class = PROVIDER_SENTINEL

    if missing_class is not None:
        return MissingValueEvidence(
            provider=provider,
            field=field,
            state="missing",
            missing_class=missing_class,
            reason_code=_MISSING_REASON_BY_CLASS[missing_class],
            raw_type=type(value).__name__,
            raw_token=_raw_token(value),
            numeric_value=None,
            field_present=field_present,
            transport_omitted=transport_omitted,
        )

    numeric_value: float | None = None
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric_value = float(value)
    return MissingValueEvidence(
        provider=provider,
        field=field,
        state="present",
        missing_class=None,
        reason_code=REASON_PRESENT,
        raw_type=type(value).__name__,
        raw_token=_raw_token(value),
        numeric_value=numeric_value,
        field_present=field_present,
        transport_omitted=transport_omitted,
    )


def require_present_numeric(
    value: object,
    *,
    provider: str,
    field: str,
    field_present: bool = True,
    transport_omitted: bool = False,
    provider_sentinels: Iterable[object] = (),
) -> float:
    evidence = normalize_missing_value(
        value,
        provider=provider,
        field=field,
        field_present=field_present,
        transport_omitted=transport_omitted,
        provider_sentinels=provider_sentinels,
    )
    if evidence.is_missing:
        raise MissingValueError(evidence)
    if evidence.numeric_value is None:
        raise ValueError(f"NON_NUMERIC_VALUE:{provider}:{field}")
    return evidence.numeric_value


def summarize_missingness(evidence: Iterable[MissingValueEvidence]) -> dict[str, object]:
    items = sorted(
        evidence,
        key=lambda item: (item.provider, item.field, item.reason_code, item.raw_type, item.raw_token or ""),
    )
    reason_counts = {reason: 0 for reason in sorted(_MISSING_REASON_BY_CLASS.values())}
    present_n = 0
    for item in items:
        if item.is_missing:
            reason_counts[item.reason_code] += 1
        else:
            present_n += 1
    missing_n = len(items) - present_n
    return {
        "contract": CONTRACT_VERSION,
        "state": "DEGRADED" if missing_n else "PASS",
        "sample_n": len(items),
        "present_n": present_n,
        "missing_n": missing_n,
        "reason_counts": reason_counts,
        "imputation_performed": False,
    }
