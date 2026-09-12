"""Optional, network-free admission of future native WeatherNext member data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
import re
from typing import Sequence

from .models import ForecastRun, utc_iso
from .probabilistic import ensemble_crps, interval_score, brier_from_members, reliability_from_members
from .semantics import VARIABLES

CONTRACT = "weathernext3-full-ensemble-v1"


class EnsembleAdmissionError(ValueError):
    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class MemberSourceEvidence:
    """Reviewed upstream contract, supplied separately from candidate values."""
    model_version: str
    schema_fingerprint: str
    source_surface: str
    resolution: str
    member_ids: tuple[str, ...]
    evidence_sha256: str
    native_members_verified: bool


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise EnsembleAdmissionError(reason)


def admit_members(
    runs: Sequence[ForecastRun], *, evidence: MemberSourceEvidence,
    valid_time_utc: datetime, variable: str,
) -> tuple[float, ...]:
    """Admit one complete station/variable/valid-time slice; never infer members."""
    _require(evidence.native_members_verified is True, "NATIVE_MEMBERS_UNVERIFIED")
    _require(all(isinstance(x, str) and x.strip() for x in (
        evidence.model_version, evidence.source_surface, evidence.resolution,
    )), "PROVENANCE_MISSING")
    _require(all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{64}", x) for x in (
        evidence.schema_fingerprint, evidence.evidence_sha256,
    )), "PROVENANCE_MISSING")
    ids = evidence.member_ids
    _require(len(ids) >= 2 and len(set(ids)) == len(ids) and all(
        isinstance(x, str) and re.fullmatch(r"member_[A-Za-z0-9_-]+|control", x)
        for x in ids
    ), "MEMBER_ROSTER_INVALID")
    _require(variable in VARIABLES and VARIABLES[variable]["kind"] != "probability",
             "VARIABLE_UNSUPPORTED")
    _require(bool(runs), "MEMBERS_UNAVAILABLE")
    target = utc_iso(valid_time_utc)
    common_identity = None
    members: dict[str, float] = {}
    for run in runs:
        metadata = run.source_metadata
        _require(run.provider == "weathernext3" and run.status == "ok"
                 and run.init_time_quality == "provider_native", "PROVIDER_PROVENANCE_INVALID")
        _require(run.model_version == evidence.model_version, "MODEL_VERSION_DRIFT")
        _require(bool(run.model_provider) and bool(run.model_name), "PROVENANCE_MISSING")
        _require(isinstance(run.raw_payload_hash, str) and
                 re.fullmatch(r"[0-9a-f]{64}", run.raw_payload_hash) is not None,
                 "PROVENANCE_MISSING")
        _require(metadata.get("location_id") == "station_10416", "LOCATION_INCOMPATIBLE")
        _require(run.source_surface == evidence.source_surface
                 and metadata.get("resolution") == evidence.resolution
                 and metadata.get("schema_fingerprint") == evidence.schema_fingerprint,
                 "SOURCE_IDENTITY_DRIFT")
        _require(metadata.get("member_origin") == "provider_native"
                 and metadata.get("member_evidence_sha256") == evidence.evidence_sha256,
                 "NATIVE_MEMBERS_UNVERIFIED")
        _require(type(metadata.get("ensemble_size")) is int
                 and metadata["ensemble_size"] == len(ids), "ENSEMBLE_SIZE_MISMATCH")
        _require(run.retrieved_at_utc >= run.init_time_utc, "TEMPORAL_PROVENANCE_INVALID")
        identity = (run.model_provider, run.model_name, run.init_time_utc, run.retrieved_at_utc)
        _require(common_identity is None or identity == common_identity, "MIXED_RUN_PROVENANCE")
        common_identity = identity
        selected = [v for v in run.values if utc_iso(v.valid_time_utc) == target and v.variable == variable]
        _require(bool(selected), "MEMBER_SLICE_MISSING")
        for value in selected:
            _require(value.statistic in ids, "NOT_NATIVE_MEMBER")
            _require(value.statistic not in members, "MEMBER_DUPLICATE")
            _require(isfinite(value.value) and isfinite(value.lead_hours)
                     and value.lead_hours == (value.valid_time_utc - run.init_time_utc).total_seconds() / 3600,
                     "VALUE_OR_LEAD_INVALID")
            semantics = VARIABLES[variable]
            _require(value.unit == semantics["unit"] and value.accumulation_window_minutes ==
                     semantics.get("window_minutes"), "VARIABLE_SEMANTICS_INVALID")
            members[value.statistic] = value.value
    _require(set(members) == set(ids), "MEMBER_SET_INCOMPLETE")
    return tuple(members[key] for key in sorted(ids))


def verification_eligibility(runs: Sequence[ForecastRun], *, evidence: MemberSourceEvidence,
                             valid_time_utc: datetime, variable: str) -> dict[str, object]:
    """No fallback data conversion: existing summary metrics use their own validator."""
    try:
        admit_members(runs, evidence=evidence, valid_time_utc=valid_time_utc, variable=variable)
        reason = None
    except EnsembleAdmissionError as exc:
        reason = exc.reason_code
    eligible = reason is None
    return {"contract": CONTRACT, "state": "PASS" if eligible else "BLOCKED",
            "reason_code": reason, "crps": eligible, "empirical_interval": eligible,
            "event_probability": eligible and variable == "precipitation_1h",
            "brier": eligible and variable == "precipitation_1h",
            "reliability": eligible and variable == "precipitation_1h",
            "summary_quantiles": "separate_validation_required",
            "fallback": None if eligible else "summary_quantile_verification",
            "warning_authority": "DWD"}


def verify_member_slice(runs: Sequence[ForecastRun], *, evidence: MemberSourceEvidence,
                        valid_time_utc: datetime, variable: str, observed: float,
                        observation_location_id: str, observation_time_utc: datetime,
                        observation_unit: str, observation_window_minutes: int | None = None,
                        ) -> dict[str, object]:
    """Score one matched truth slice; reliability is a single sample, not a ranking."""
    members = admit_members(runs, evidence=evidence, valid_time_utc=valid_time_utc, variable=variable)
    _require(observation_location_id == "station_10416" and
             utc_iso(observation_time_utc) == utc_iso(valid_time_utc) and
             observation_unit == VARIABLES[variable]["unit"] and
             observation_window_minutes == VARIABLES[variable].get("window_minutes") and
             isfinite(observed), "TRUTH_INCOMPATIBLE")
    result = verification_eligibility(runs, evidence=evidence, valid_time_utc=valid_time_utc, variable=variable)
    result.update({"n": 1, "member_count": len(members), "model_version": evidence.model_version,
                   "crps_score": ensemble_crps(members, observed),
                   "interval": interval_score(members, observed)})
    if variable == "precipitation_1h":
        result["brier_score"] = brier_from_members([members], [observed])
        result["reliability_bins"] = reliability_from_members([members], [observed])
    return result
