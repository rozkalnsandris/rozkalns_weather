from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

CONTRACT_VERSION = "ensemble-member-completeness-v1"
METRICS = (
    "crps",
    "empirical_interval",
    "member_fraction_probability",
    "brier",
    "reliability",
)


@dataclass(frozen=True, slots=True)
class EnsembleIdentityContract:
    provider_id: str
    model_name: str
    expected_member_count: int
    control_id: str = "control"

    @property
    def expected_member_ids(self) -> tuple[str, ...]:
        if self.expected_member_count < 1:
            return ()
        return (self.control_id,) + tuple(
            f"member{index:02d}" for index in range(1, self.expected_member_count)
        )


CONTRACTS: Mapping[str, EnsembleIdentityContract] = {
    "icon_d2_eps": EnsembleIdentityContract("icon_d2_eps", "ICON-D2-EPS", 20),
    "ecmwf_ifs_ens": EnsembleIdentityContract("ecmwf_ifs_ens", "IFS ENS 0.25°", 51),
    "ecmwf_aifs_ens": EnsembleIdentityContract("ecmwf_aifs_ens", "AIFS ENS 0.25°", 51),
}


def canonical_member_id(raw_member_id: str) -> str:
    value = raw_member_id.strip().lower()
    if value == "control":
        return "control"
    if value.startswith("member_"):
        suffix = value.removeprefix("member_")
    elif value.startswith("member"):
        suffix = value.removeprefix("member")
    else:
        return value
    if suffix.isdigit():
        index = int(suffix)
        if index == 0:
            return "control"
        return f"member{index:02d}"
    return value


def _all_metrics(value: bool) -> dict[str, bool]:
    return {metric: value for metric in METRICS}


def evaluate_member_set(
    *,
    provider_id: str,
    member_ids: Sequence[str],
    model_versions: Sequence[str | None] = (),
    init_time_utc: str | None = None,
    valid_time_utc: str | None = None,
    lead_hours: float | None = None,
    variable: str | None = None,
    source_surface: str | None = None,
    declared_member_count: int | None = None,
    retention_truncated: bool = False,
) -> dict[str, object]:
    contract = CONTRACTS.get(provider_id)
    raw_ids = tuple(str(value) for value in member_ids)
    canonical_ids = tuple(canonical_member_id(value) for value in raw_ids)
    counts = Counter(canonical_ids)
    duplicate_ids = tuple(sorted(member_id for member_id, count in counts.items() if count > 1))
    versions = tuple(sorted({str(value) for value in model_versions if value is not None}))
    reasons: list[str] = []
    status = "unsupported"

    if contract is None:
        reasons.append("UNSUPPORTED_ENSEMBLE_CONTRACT")
        expected_ids: tuple[str, ...] = ()
        missing_ids: tuple[str, ...] = ()
        unexpected_ids = tuple(sorted(set(canonical_ids)))
        expected_count = None
    else:
        expected_ids = contract.expected_member_ids
        expected_set = set(expected_ids)
        observed_set = set(canonical_ids)
        missing_ids = tuple(sorted(expected_set - observed_set))
        unexpected_ids = tuple(sorted(observed_set - expected_set))
        expected_count = contract.expected_member_count

        if declared_member_count is not None and declared_member_count != expected_count:
            reasons.append("EXPECTED_SIZE_CHANGED")
        if duplicate_ids:
            reasons.append("DUPLICATE_MEMBER_ID")
        if "control" in duplicate_ids:
            reasons.append("CONTROL_MEMBER_COLLISION")
        if unexpected_ids:
            reasons.append("UNEXPECTED_MEMBER_ID")
        if len(versions) > 1:
            reasons.append("MIXED_MODEL_VERSION")
        if missing_ids:
            reasons.append("MISSING_MEMBER")
        if retention_truncated:
            reasons.append("TRUNCATED_RETENTION")

        blocking = {
            "EXPECTED_SIZE_CHANGED",
            "DUPLICATE_MEMBER_ID",
            "CONTROL_MEMBER_COLLISION",
            "UNEXPECTED_MEMBER_ID",
            "MIXED_MODEL_VERSION",
        }
        if any(reason in blocking for reason in reasons):
            status = "blocked"
        elif missing_ids or retention_truncated:
            status = "partial"
        else:
            status = "complete"
            reasons.append("COMPLETE_MEMBER_SET")

    eligible = contract is not None and status == "complete"
    return {
        "contract_version": CONTRACT_VERSION,
        "provider_id": provider_id,
        "model_name": contract.model_name if contract is not None else None,
        "expected_member_count": expected_count,
        "declared_member_count": declared_member_count,
        "expected_member_ids": list(expected_ids),
        "raw_member_ids": list(raw_ids),
        "canonical_member_ids": sorted(set(canonical_ids)),
        "observed_member_count": len(set(canonical_ids)),
        "missing_member_ids": list(missing_ids),
        "unexpected_member_ids": list(unexpected_ids),
        "duplicate_member_ids": list(duplicate_ids),
        "model_versions": list(versions),
        "init_time_utc": init_time_utc,
        "valid_time_utc": valid_time_utc,
        "lead_hours": lead_hours,
        "variable": variable,
        "source_surface": source_surface,
        "retention_truncated": bool(retention_truncated),
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "metric_eligibility": _all_metrics(eligible),
    }


def evaluate_run_stability(member_sets: Iterable[dict[str, object]]) -> dict[str, object]:
    items = list(member_sets)
    signatures = {
        tuple(str(value) for value in item.get("canonical_member_ids", []))
        for item in items
    }
    changed = len(signatures) > 1
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "blocked" if changed else ("stable" if items else "unsupported"),
        "reason_codes": ["MEMBER_SET_CHANGED"]
        if changed
        else (["MEMBER_SET_STABLE"] if items else ["NO_MEMBER_SETS"]),
        "set_count": len(items),
        "distinct_member_sets": len(signatures),
        "metric_eligibility": _all_metrics(bool(items) and not changed),
    }


def metric_eligible(evidence: Mapping[str, object], metric: str) -> bool:
    if metric not in METRICS:
        raise ValueError(f"unsupported ensemble metric: {metric}")
    eligibility = evidence.get("metric_eligibility")
    return bool(isinstance(eligibility, Mapping) and eligibility.get(metric) is True)
