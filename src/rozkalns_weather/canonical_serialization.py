from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
import hashlib
import json
from math import isfinite
from numbers import Number
import re
from typing import Any

CANONICAL_SERIALIZATION_CONTRACT = "canonical-evidence-serialization-v1"
CANONICAL_SERIALIZATION_SCHEMA_VERSION = 1

_UTC_FIELD_RE = re.compile(r"(?:^|_)utc$")
_UTC_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[Tt ](?P<time>\d{2}:\d{2}:\d{2})"
    r"(?P<fraction>\.\d+)?(?P<zone>Z|z|\+00(?::?00)?)$"
)


class CanonicalSerializationError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _normalize_utc_timestamp(value: str) -> str:
    text = value.strip()
    match = _UTC_TIMESTAMP_RE.fullmatch(text)
    if match is None:
        raise CanonicalSerializationError(
            "INVALID_UTC_TIMESTAMP",
            "UTC timestamp fields must use an ISO-8601 timestamp with an explicit zero UTC offset",
        )
    try:
        datetime.strptime(
            f"{match.group('date')}T{match.group('time')}",
            "%Y-%m-%dT%H:%M:%S",
        )
    except ValueError as exc:
        raise CanonicalSerializationError(
            "INVALID_UTC_TIMESTAMP",
            "UTC timestamp fields must contain a valid calendar date and clock time",
        ) from exc

    fraction = match.group("fraction")
    normalized_fraction = ""
    if fraction:
        digits = fraction[1:].rstrip("0")
        if digits:
            normalized_fraction = f".{digits}"
    return f"{match.group('date')}T{match.group('time')}{normalized_fraction}Z"


def _float_token(value: float) -> str:
    if not isfinite(value):
        raise CanonicalSerializationError(
            "NON_FINITE_NUMBER",
            "canonical evidence does not permit NaN or positive/negative infinity",
        )
    if value == 0.0:
        return "0"

    token = repr(value).lower()
    if "e" in token:
        mantissa, exponent = token.split("e", 1)
        if mantissa.endswith(".0"):
            mantissa = mantissa[:-2]
        sign = "-" if exponent.startswith("-") else ""
        digits = exponent.lstrip("+-").lstrip("0") or "0"
        return f"{mantissa}e{sign}{digits}"
    if token.endswith(".0"):
        token = token[:-2]
    return token


def _quoted(value: str) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CanonicalSerializationError("UNSUPPORTED_STRING", "value is not a canonical JSON string") from exc


def _encode(value: object, *, field_name: str | None = None) -> str:
    if isinstance(value, Enum):
        return _encode(value.value, field_name=field_name)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return _float_token(value)
    if isinstance(value, Number):
        raise CanonicalSerializationError(
            "UNSUPPORTED_NUMERIC_TYPE",
            f"unsupported numeric type: {type(value).__name__}",
        )
    if isinstance(value, datetime):
        offset = value.utcoffset() if value.tzinfo is not None else None
        if offset is None or offset.total_seconds() != 0:
            raise CanonicalSerializationError(
                "INVALID_UTC_TIMESTAMP",
                "datetime values must be timezone-aware and have a zero UTC offset",
            )
        return _quoted(_normalize_utc_timestamp(value.isoformat().replace("+00:00", "Z")))
    if isinstance(value, str):
        if field_name is not None and _UTC_FIELD_RE.search(field_name.lower()):
            value = _normalize_utc_timestamp(value)
        return _quoted(value)
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalSerializationError(
                    "NON_STRING_OBJECT_KEY",
                    "canonical evidence object keys must be strings",
                )
        encoded = [
            f"{_quoted(key)}:{_encode(value[key], field_name=key)}"
            for key in sorted(value)
        ]
        return "{" + ",".join(encoded) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item, field_name=field_name) for item in value) + "]"
    raise CanonicalSerializationError(
        "UNSUPPORTED_TYPE",
        f"unsupported canonical evidence type: {type(value).__name__}",
    )


def canonical_json_bytes(value: object) -> bytes:
    """Serialize evidence to versioned, deterministic UTF-8 JSON plus one LF.

    Object keys are sorted lexicographically; array order is preserved. UTC fields
    named ``utc`` or ending in ``_utc`` normalize equivalent zero-offset timestamp
    spellings without reducing fractional-second precision. Finite floats use the
    runtime's shortest round-trip decimal representation with normalized exponent
    spelling, and signed zero is canonicalized to JSON numeric zero. No domain
    rounding, imputation, unit conversion, or value correction is performed.
    """

    try:
        return (_encode(value) + "\n").encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanonicalSerializationError(
            "INVALID_UNICODE",
            "canonical evidence strings must encode as valid UTF-8",
        ) from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_contract_evidence() -> dict[str, Any]:
    return {
        "schema_version": CANONICAL_SERIALIZATION_SCHEMA_VERSION,
        "contract": CANONICAL_SERIALIZATION_CONTRACT,
        "encoding": "UTF-8",
        "terminator": "LF",
        "object_key_order": "lexicographic_unicode_codepoint",
        "array_order": "preserved",
        "utc_timestamp_fields": "utc_or_suffix__utc",
        "numeric_policy": {
            "finite_only": True,
            "float_representation": "shortest_round_trip_decimal",
            "exponent": "lowercase_e_no_plus_no_leading_zeroes",
            "signed_zero": "0",
            "domain_rounding": False,
        },
        "raw_provider_precision_preserved": True,
    }
