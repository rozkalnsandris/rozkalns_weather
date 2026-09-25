from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from math import floor, isfinite, sqrt
from typing import Any

from .canonical_serialization import CanonicalSerializationError, canonical_sha256
from .verification import sample_confidence


RESAMPLING_SCHEMA_VERSION = 1
RESAMPLING_CONTRACT = "verification-resampling-v1"
ALGORITHM_METHOD = "sha256-index-bootstrap"
ALGORITHM_VERSION = 1
SEED_DERIVATION = "canonical-sha256-v1"
PERCENTILE_METHOD = "linear-interpolation-v1"
MIN_RESAMPLE_COUNT = 100
MAX_RESAMPLE_COUNT = 100_000
_SUPPORTED_STATISTICS = {"mean", "root_mean_square"}


class ResamplingError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _sha256(value: object) -> str:
    try:
        return canonical_sha256(value)
    except CanonicalSerializationError as exc:
        raise ResamplingError(
            "INVALID_SAMPLE_VALUE",
            "resampling inputs must be canonical finite JSON values",
        ) from exc


def _normalize_samples(samples: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for sample in samples:
        sample_id = str(sample.get("sample_id") or "").strip()
        if not sample_id:
            raise ResamplingError("MISSING_SAMPLE_IDENTITY", "every sample requires a stable sample_id")
        if sample_id in seen:
            raise ResamplingError("DUPLICATE_SAMPLE_IDENTITY", f"duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        value = sample.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise ResamplingError("INVALID_SAMPLE_VALUE", f"sample {sample_id} must have one finite numeric value")
        normalized.append({"sample_id": sample_id, "value": float(value)})
    normalized.sort(key=lambda item: str(item["sample_id"]))
    return normalized


def _normalize_binding(binding: Mapping[str, object]) -> dict[str, object]:
    required_text = ("provider", "model_name", "lead_bucket", "variable", "comparison_mode")
    normalized: dict[str, object] = {}
    for field in required_text:
        value = str(binding.get(field) or "").strip()
        if not value:
            raise ResamplingError("MISSING_RESAMPLING_BINDING", f"{field} is required")
        normalized[field] = value
    if "model_version" not in binding:
        raise ResamplingError("MISSING_RESAMPLING_BINDING", "model_version must be explicit, including null")
    normalized["model_version"] = binding.get("model_version")
    return normalized


def _aggregate(values: Sequence[float], statistic: str) -> float:
    if statistic == "mean":
        return sum(values) / len(values)
    if statistic == "root_mean_square":
        return sqrt(sum(value * value for value in values) / len(values))
    raise ResamplingError("UNSUPPORTED_STATISTIC", f"unsupported statistic: {statistic}")


def _linear_quantile(sorted_values: Sequence[float], probability: float) -> float:
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * probability
    lower_index = floor(position)
    upper_index = min(len(sorted_values) - 1, lower_index + 1)
    fraction = position - lower_index
    lower = float(sorted_values[lower_index])
    upper = float(sorted_values[upper_index])
    return lower + (upper - lower) * fraction


def _draw_index(*, seed_identity: str, replicate: int, draw: int, sample_count: int) -> int:
    payload = f"{seed_identity}:{replicate}:{draw}".encode("ascii")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big", signed=False) % sample_count


def _require_sha256(value: object, *, reason_code: str, field: str) -> str:
    text = str(value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ResamplingError(reason_code, f"{field} must be a lowercase SHA-256 digest")
    return text


def build_resampling_receipt(
    *,
    samples: Sequence[Mapping[str, object]],
    binding: Mapping[str, object],
    metric_configuration: Mapping[str, object],
    statistic: str,
    confidence_level: float = 0.95,
    resample_count: int = 2_000,
    seed_namespace: str = "default",
    algorithm_version: int = ALGORITHM_VERSION,
    eligible: bool = True,
) -> dict[str, Any]:
    """Build deterministic non-ranking bootstrap confidence-interval evidence.

    Samples are canonicalized by stable ``sample_id``. Bootstrap draw indices are
    derived directly from SHA-256, so reproducibility does not depend on process
    RNG state or the implementation details of Python's ``random`` module.
    """

    if not eligible:
        raise ResamplingError("SAMPLE_NOT_ELIGIBLE", "upstream verification sample is not eligible for resampling")
    if algorithm_version != ALGORITHM_VERSION:
        raise ResamplingError(
            "UNSUPPORTED_ALGORITHM_VERSION",
            f"only {ALGORITHM_METHOD} version {ALGORITHM_VERSION} is supported",
        )
    if statistic not in _SUPPORTED_STATISTICS:
        raise ResamplingError("UNSUPPORTED_STATISTIC", f"unsupported statistic: {statistic}")
    if not isinstance(confidence_level, (int, float)) or isinstance(confidence_level, bool):
        raise ResamplingError("INVALID_CONFIDENCE_LEVEL", "confidence_level must be numeric")
    confidence = float(confidence_level)
    if not 0.0 < confidence < 1.0:
        raise ResamplingError("INVALID_CONFIDENCE_LEVEL", "confidence_level must be strictly between 0 and 1")
    if (
        not isinstance(resample_count, int)
        or isinstance(resample_count, bool)
        or not MIN_RESAMPLE_COUNT <= resample_count <= MAX_RESAMPLE_COUNT
    ):
        raise ResamplingError(
            "INVALID_RESAMPLE_COUNT",
            f"resample_count must be between {MIN_RESAMPLE_COUNT} and {MAX_RESAMPLE_COUNT}",
        )
    namespace = str(seed_namespace).strip()
    if not namespace:
        raise ResamplingError("MISSING_RESAMPLING_BINDING", "seed_namespace must be non-empty")
    if not metric_configuration:
        raise ResamplingError("MISSING_METRIC_CONFIGURATION", "metric_configuration is required")

    normalized_samples = _normalize_samples(samples)
    sample_count = len(normalized_samples)
    sufficiency = sample_confidence(sample_count)
    if sufficiency == "insufficient_sample":
        raise ResamplingError(
            "INSUFFICIENT_SAMPLE_COUNT",
            "existing verification sample-sufficiency contract requires at least 30 samples",
        )

    normalized_binding = _normalize_binding(binding)
    sample_identity = _sha256(normalized_samples)
    metric_configuration_normalized = dict(metric_configuration)
    metric_configuration_identity = _sha256(metric_configuration_normalized)
    seed_core = {
        "seed_derivation": SEED_DERIVATION,
        "algorithm_method": ALGORITHM_METHOD,
        "algorithm_version": ALGORITHM_VERSION,
        "sample_identity_sha256": sample_identity,
        "binding": normalized_binding,
        "metric_configuration_sha256": metric_configuration_identity,
        "statistic": statistic,
        "seed_namespace": namespace,
    }
    seed_identity = _sha256(seed_core)

    values = [float(item["value"]) for item in normalized_samples]
    point_estimate = _aggregate(values, statistic)
    bootstrap_statistics: list[float] = []
    for replicate in range(resample_count):
        replicate_values = [
            values[
                _draw_index(
                    seed_identity=seed_identity,
                    replicate=replicate,
                    draw=draw,
                    sample_count=sample_count,
                )
            ]
            for draw in range(sample_count)
        ]
        bootstrap_statistics.append(_aggregate(replicate_values, statistic))
    bootstrap_statistics.sort()
    tail = (1.0 - confidence) / 2.0
    lower = _linear_quantile(bootstrap_statistics, tail)
    upper = _linear_quantile(bootstrap_statistics, 1.0 - tail)

    receipt_core: dict[str, object] = {
        "schema_version": RESAMPLING_SCHEMA_VERSION,
        "contract": RESAMPLING_CONTRACT,
        "algorithm": {
            "method": ALGORITHM_METHOD,
            "version": ALGORITHM_VERSION,
            "seed_derivation": SEED_DERIVATION,
            "percentile_method": PERCENTILE_METHOD,
            "resample_count": resample_count,
        },
        "seed_identity_sha256": seed_identity,
        "sample_identity_sha256": sample_identity,
        "binding": normalized_binding,
        "sample_count": sample_count,
        "sample_sufficiency_state": sufficiency,
        "metric_configuration": metric_configuration_normalized,
        "metric_configuration_sha256": metric_configuration_identity,
        "statistic": statistic,
        "confidence_level": confidence,
        "point_estimate": point_estimate,
        "interval": {"lower": lower, "upper": upper},
        "interpretation": "uncertainty_interval_only",
        "ranking_verdict": False,
    }
    receipt_identity = _sha256(receipt_core)
    return {
        **receipt_core,
        "resampling_receipt_identity_sha256": receipt_identity,
        "reproducible": True,
        "authority": {
            "production_corpus_mutation_granted": False,
            "runtime_live_authority_granted": False,
            "artifact_publication_authority_granted": False,
        },
        "privacy": {
            "raw_samples_exposed": False,
            "coordinates_exposed": False,
            "credentials_exposed": False,
        },
    }


def resampling_lineage_binding(receipt: Mapping[str, object]) -> dict[str, object]:
    """Validate and reduce a resampling receipt to privacy-safe report lineage."""

    if receipt.get("contract") != RESAMPLING_CONTRACT or receipt.get("schema_version") != RESAMPLING_SCHEMA_VERSION:
        raise ResamplingError(
            "RESAMPLING_RECEIPT_CONTRACT_MISMATCH",
            "unsupported resampling receipt contract",
        )
    receipt_identity = _require_sha256(
        receipt.get("resampling_receipt_identity_sha256"),
        reason_code="INVALID_RESAMPLING_RECEIPT_IDENTITY",
        field="resampling_receipt_identity_sha256",
    )
    sample_identity = _require_sha256(
        receipt.get("sample_identity_sha256"),
        reason_code="INVALID_RESAMPLING_RECEIPT_IDENTITY",
        field="sample_identity_sha256",
    )
    seed_identity = _require_sha256(
        receipt.get("seed_identity_sha256"),
        reason_code="INVALID_RESAMPLING_RECEIPT_IDENTITY",
        field="seed_identity_sha256",
    )
    metric_identity = _require_sha256(
        receipt.get("metric_configuration_sha256"),
        reason_code="INVALID_RESAMPLING_RECEIPT_IDENTITY",
        field="metric_configuration_sha256",
    )
    algorithm = receipt.get("algorithm")
    binding = receipt.get("binding")
    if not isinstance(algorithm, Mapping) or not isinstance(binding, Mapping):
        raise ResamplingError("MISSING_RESAMPLING_LINEAGE", "algorithm and binding are required")
    if algorithm.get("method") != ALGORITHM_METHOD or algorithm.get("version") != ALGORITHM_VERSION:
        raise ResamplingError("UNSUPPORTED_ALGORITHM_VERSION", "resampling lineage uses an unsupported algorithm")
    normalized_binding = _normalize_binding(binding)
    sample_count = receipt.get("sample_count")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 30:
        raise ResamplingError("INSUFFICIENT_SAMPLE_COUNT", "resampling lineage requires at least 30 samples")
    if receipt.get("ranking_verdict") is not False or receipt.get("interpretation") != "uncertainty_interval_only":
        raise ResamplingError("RESAMPLING_RECEIPT_CONTRACT_MISMATCH", "resampling lineage must remain non-ranking uncertainty evidence")
    return {
        "contract": RESAMPLING_CONTRACT,
        "resampling_receipt_identity_sha256": receipt_identity,
        "algorithm": {
            "method": ALGORITHM_METHOD,
            "version": ALGORITHM_VERSION,
            "seed_derivation": str(algorithm.get("seed_derivation") or ""),
            "percentile_method": str(algorithm.get("percentile_method") or ""),
            "resample_count": algorithm.get("resample_count"),
        },
        "seed_identity_sha256": seed_identity,
        "sample_identity_sha256": sample_identity,
        "binding": normalized_binding,
        "sample_count": sample_count,
        "metric_configuration_sha256": metric_identity,
        "statistic": str(receipt.get("statistic") or ""),
        "confidence_level": receipt.get("confidence_level"),
        "interpretation": "uncertainty_interval_only",
        "ranking_verdict": False,
    }
