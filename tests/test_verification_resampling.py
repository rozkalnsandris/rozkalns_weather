from __future__ import annotations

import json
from pathlib import Path

import pytest

from rozkalns_weather.verification_resampling import (
    ResamplingError,
    build_resampling_receipt,
    resampling_lineage_binding,
)


def _samples(n: int = 30) -> list[dict[str, object]]:
    return [
        {"sample_id": f"valid-2026-09-{index:02d}", "value": float((index % 7) - 3)}
        for index in range(n)
    ]


def _binding() -> dict[str, object]:
    return {
        "provider": "weathernext3",
        "model_name": "WeatherNext 3",
        "model_version": "3.0.0",
        "lead_bucket": "6-12h",
        "variable": "temperature_2m",
        "comparison_mode": "monthly_common_valid_time",
    }


def _metric_configuration() -> dict[str, object]:
    return {
        "metric_id": "bias",
        "sample_semantics": "forecast_minus_observed",
        "truth_source": "DWD CDC 05480",
    }


def _receipt(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "samples": _samples(),
        "binding": _binding(),
        "metric_configuration": _metric_configuration(),
        "statistic": "mean",
        "confidence_level": 0.95,
        "resample_count": 200,
    }
    kwargs.update(overrides)
    return build_resampling_receipt(**kwargs)


def test_contract_freezes_deterministic_non_ranking_semantics() -> None:
    payload = json.loads(Path("contracts/verification-resampling-v1.json").read_text())
    assert payload["contract"] == "verification-resampling-v1"
    assert payload["algorithm"]["method"] == "sha256-index-bootstrap"
    assert payload["algorithm"]["version"] == 1
    assert payload["sample_sufficiency"]["source"] == "rozkalns_weather.verification.sample_confidence"
    assert payload["determinism"]["sample_order_affects_identity"] is False
    assert payload["determinism"]["outcome_driven_seed_selection_allowed"] is False
    assert payload["interpretation"]["ranking_verdict_allowed"] is False
    assert payload["authority"]["runtime_live_authority_granted"] is False


def test_identical_inputs_reproduce_identical_receipt_and_interval() -> None:
    first = _receipt()
    second = _receipt()

    assert first == second
    assert first["sample_count"] == 30
    assert first["sample_sufficiency_state"] == "limited_sample"
    assert first["algorithm"]["method"] == "sha256-index-bootstrap"
    assert first["algorithm"]["version"] == 1
    assert first["interval"] == second["interval"]
    assert first["resampling_receipt_identity_sha256"] == second["resampling_receipt_identity_sha256"]
    assert first["ranking_verdict"] is False
    assert first["interpretation"] == "uncertainty_interval_only"
    assert first["privacy"]["raw_samples_exposed"] is False


def test_reordered_identical_samples_keep_identity_seed_and_interval() -> None:
    original = _receipt()
    reordered = _receipt(samples=list(reversed(_samples())))

    assert reordered["sample_identity_sha256"] == original["sample_identity_sha256"]
    assert reordered["seed_identity_sha256"] == original["seed_identity_sha256"]
    assert reordered["interval"] == original["interval"]
    assert reordered["resampling_receipt_identity_sha256"] == original["resampling_receipt_identity_sha256"]


def test_changed_sample_changes_sample_seed_and_receipt_identity() -> None:
    original = _receipt()
    changed_samples = _samples()
    changed_samples[7] = {**changed_samples[7], "value": 9.0}
    changed = _receipt(samples=changed_samples)

    assert changed["sample_identity_sha256"] != original["sample_identity_sha256"]
    assert changed["seed_identity_sha256"] != original["seed_identity_sha256"]
    assert changed["resampling_receipt_identity_sha256"] != original["resampling_receipt_identity_sha256"]


def test_changed_metric_configuration_changes_seed_and_receipt_identity() -> None:
    original = _receipt()
    config = _metric_configuration()
    config["metric_id"] = "mae"
    config["sample_semantics"] = "absolute_error"
    changed = _receipt(metric_configuration=config)

    assert changed["metric_configuration_sha256"] != original["metric_configuration_sha256"]
    assert changed["seed_identity_sha256"] != original["seed_identity_sha256"]
    assert changed["resampling_receipt_identity_sha256"] != original["resampling_receipt_identity_sha256"]


def test_changed_seed_namespace_changes_seed_and_receipt_but_not_sample_identity() -> None:
    original = _receipt()
    changed = _receipt(seed_namespace="methodology-revision-b")

    assert changed["sample_identity_sha256"] == original["sample_identity_sha256"]
    assert changed["seed_identity_sha256"] != original["seed_identity_sha256"]
    assert changed["resampling_receipt_identity_sha256"] != original["resampling_receipt_identity_sha256"]


def test_changed_or_unsupported_algorithm_version_fails_closed() -> None:
    with pytest.raises(ResamplingError) as error:
        _receipt(algorithm_version=2)
    assert error.value.reason_code == "UNSUPPORTED_ALGORITHM_VERSION"


def test_insufficient_or_ineligible_samples_fail_closed_using_existing_sufficiency_rule() -> None:
    with pytest.raises(ResamplingError) as insufficient:
        _receipt(samples=_samples(29))
    assert insufficient.value.reason_code == "INSUFFICIENT_SAMPLE_COUNT"

    with pytest.raises(ResamplingError) as ineligible:
        _receipt(eligible=False)
    assert ineligible.value.reason_code == "SAMPLE_NOT_ELIGIBLE"


def test_duplicate_or_invalid_samples_fail_closed() -> None:
    duplicated = _samples()
    duplicated[-1] = dict(duplicated[0])
    with pytest.raises(ResamplingError) as duplicate:
        _receipt(samples=duplicated)
    assert duplicate.value.reason_code == "DUPLICATE_SAMPLE_IDENTITY"

    invalid = _samples()
    invalid[0] = {"sample_id": "valid-2026-09-00", "value": float("nan")}
    with pytest.raises(ResamplingError) as invalid_value:
        _receipt(samples=invalid)
    assert invalid_value.value.reason_code == "INVALID_SAMPLE_VALUE"


def test_root_mean_square_statistic_is_supported_without_ranking_semantics() -> None:
    config = _metric_configuration()
    config["metric_id"] = "rmse"
    config["sample_semantics"] = "forecast_minus_observed"
    receipt = _receipt(metric_configuration=config, statistic="root_mean_square")

    assert receipt["statistic"] == "root_mean_square"
    assert receipt["point_estimate"] >= 0.0
    assert receipt["interval"]["lower"] >= 0.0
    assert receipt["ranking_verdict"] is False


def test_lineage_binding_exposes_method_version_seed_and_exact_context_without_raw_samples() -> None:
    receipt = _receipt()
    lineage = resampling_lineage_binding(receipt)

    assert lineage["algorithm"]["method"] == "sha256-index-bootstrap"
    assert lineage["algorithm"]["version"] == 1
    assert lineage["seed_identity_sha256"] == receipt["seed_identity_sha256"]
    assert lineage["sample_identity_sha256"] == receipt["sample_identity_sha256"]
    assert lineage["binding"] == _binding()
    assert lineage["sample_count"] == 30
    assert lineage["ranking_verdict"] is False
    assert "samples" not in lineage
    assert "interval" not in lineage


def test_lineage_binding_rejects_ranking_semantics() -> None:
    receipt = _receipt()
    receipt["ranking_verdict"] = True
    with pytest.raises(ResamplingError) as error:
        resampling_lineage_binding(receipt)
    assert error.value.reason_code == "RESAMPLING_RECEIPT_CONTRACT_MISMATCH"
