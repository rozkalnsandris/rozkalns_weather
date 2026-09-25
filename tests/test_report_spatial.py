from __future__ import annotations

from copy import deepcopy

import pytest

from rozkalns_weather.canonical_serialization import canonical_sha256
from rozkalns_weather.report_spatial import ReportSpatialError, bind_spatial_sample_to_report_lineage
from rozkalns_weather.spatial_provenance import build_spatial_receipt, validate_common_sample_spatial


def _lineage() -> dict[str, object]:
    configuration = {
        "lead_filters": {"max_hours": 48},
        "sample_filters": {"location_id": "station_05480"},
        "metric_configuration": {"metric": "mae"},
        "metric_eligibility": {
            "deterministic": ["mae"],
            "ensemble_members": [],
            "weathernext_summary_quantiles": [],
        },
    }
    core = {
        "schema_version": 1,
        "contract": "verification-report-lineage-v1",
        "source_sha": "a" * 40,
        "report_schema": {"name": "verification-report", "version": 1},
        "window": {"start": "2026-09-01", "end": "2026-09-30"},
        "corpus_manifest": {"manifest_checksum_sha256": "b" * 64},
        "truth_revision_set": {"truth_revision_set_sha256": "c" * 64},
        "provider_models": [{"provider": "icon_d2", "model_name": "ICON-D2", "model_version": "2026-09"}],
        "configuration": configuration,
        "configuration_sha256": canonical_sha256(configuration),
        "sample_evidence": {"common_sample_identity_sha256": "d" * 64, "sample_counts": {"icon_d2": 100}},
        "artifact": {"machine_readable_checksum_sha256": "e" * 64, "human_readable_reference": "reports/2026-09.md"},
    }
    return {
        **core,
        "lineage_identity_sha256": canonical_sha256(core),
        "reproducible": True,
        "privacy": {"coordinates_exposed": False},
    }


def _spatial_sample() -> dict[str, object]:
    truth = build_spatial_receipt(
        kind="truth", location_id="station_05480", station_id="05480", provider="DWD",
        model_name="DWD CDC observation", source_surface="DWD CDC station observation",
        variable="temperature_2m", native_resolution="point_station", grid_role="observation_station",
        sampling_mode="exact_station", interpolation_mode="none_station_observation", transport_provider="DWD CDC",
    )
    forecast = build_spatial_receipt(
        kind="forecast", location_id="station_05480", provider="icon_d2", model_name="ICON-D2",
        source_surface="Open-Meteo Single Runs API", variable="temperature_2m",
        native_resolution="provider_native_not_exposed", grid_role="provider_grid",
        sampling_mode="transport_point", interpolation_mode="transport_interpolated_or_resampled",
        transport_provider="Open-Meteo",
    )
    return validate_common_sample_spatial([forecast], truth_receipt=truth)


def test_report_lineage_binds_privacy_safe_spatial_common_sample() -> None:
    base = _lineage()
    result = bind_spatial_sample_to_report_lineage(base, spatial_sample=_spatial_sample())
    spatial = result["configuration"]["spatial_collocation"]

    assert result["contract"] == "verification-report-lineage-v1"
    assert result["lineage_identity_sha256"] != base["lineage_identity_sha256"]
    assert spatial["benchmark_location"]["id"] == "station_05480"
    assert spatial["benchmark_location"]["coordinates_exposed"] is False
    assert len(spatial["spatial_common_sample_identity_sha256"]) == 64
    assert result["privacy"]["coordinates_exposed"] is False


def test_report_lineage_rejects_tampered_base_identity() -> None:
    base = _lineage()
    base["configuration"]["sample_filters"] = {"location_id": "home"}
    with pytest.raises(ReportSpatialError) as exc:
        bind_spatial_sample_to_report_lineage(base, spatial_sample=_spatial_sample())
    assert exc.value.reason_code == "REPORT_LINEAGE_IDENTITY_MISMATCH"


def test_report_lineage_rejects_noncanonical_or_private_spatial_sample() -> None:
    sample = deepcopy(_spatial_sample())
    sample["benchmark_location"]["id"] = "station_10416"
    with pytest.raises(ReportSpatialError) as exc:
        bind_spatial_sample_to_report_lineage(_lineage(), spatial_sample=sample)
    assert exc.value.reason_code == "SPATIAL_SAMPLE_LOCATION_MISMATCH"

    private = deepcopy(_spatial_sample())
    private["privacy"]["coordinates_exposed"] = True
    with pytest.raises(ReportSpatialError) as exc:
        bind_spatial_sample_to_report_lineage(_lineage(), spatial_sample=private)
    assert exc.value.reason_code == "SPATIAL_SAMPLE_PRIVACY_VIOLATION"


def test_report_lineage_spatial_binding_is_single_assignment() -> None:
    first = bind_spatial_sample_to_report_lineage(_lineage(), spatial_sample=_spatial_sample())
    with pytest.raises(ReportSpatialError) as exc:
        bind_spatial_sample_to_report_lineage(first, spatial_sample=_spatial_sample())
    assert exc.value.reason_code == "SPATIAL_LINEAGE_ALREADY_BOUND"
