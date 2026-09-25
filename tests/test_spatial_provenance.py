from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from rozkalns_weather.spatial_provenance import (
    SPATIAL_CONTRACT,
    SpatialProvenanceError,
    build_spatial_receipt,
    spatial_evidence,
    validate_common_sample_spatial,
    validate_spatial_receipt,
)

FIXTURE = Path(__file__).parent / "fixtures" / "spatial_collocation_cases.json"


def _cases() -> dict[str, dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _receipt(name: str, **changes: object) -> dict[str, object]:
    values = deepcopy(_cases()[name])
    values.update(changes)
    return build_spatial_receipt(**values)


def test_exact_station_05480_and_declared_grid_mapping_are_compatible() -> None:
    truth = _receipt("truth_05480")
    icon = _receipt("icon_d2")
    result = validate_common_sample_spatial([icon], truth_receipt=truth)

    assert result["contract"] == SPATIAL_CONTRACT
    assert result["state"] == "PASS"
    assert result["benchmark_location"] == {
        "id": "station_05480",
        "station_id": "05480",
        "coordinates_exposed": False,
    }
    assert result["forecasts"][0]["source"]["provider"] == "icon_d2"
    assert result["forecasts"][0]["collocation"]["interpolation_mode"] == "transport_interpolated_or_resampled"
    assert result["privacy"]["coordinates_exposed"] is False


def test_weathernext_preserves_station_head_and_surface_resolution_distinction() -> None:
    station_head = _receipt("weathernext_005")
    surface = _receipt("weathernext_01")

    assert station_head["source"]["source_surface"] == "BigQuery WeatherNext 3 0p05"
    assert station_head["grid"] == {"native_resolution": "0p05deg", "role": "station_head"}
    assert station_head["collocation"] == {"sampling_mode": "station_head", "interpolation_mode": "station_head"}
    assert surface["source"]["source_surface"] == "BigQuery WeatherNext 3 0p1"
    assert surface["grid"] == {"native_resolution": "0p1deg", "role": "surface"}
    assert surface["collocation"] == {"sampling_mode": "surface_grid_cell", "interpolation_mode": "surface_grid_cell"}
    assert station_head["spatial_identity_sha256"] != surface["spatial_identity_sha256"]


def test_weathernext_resolution_drift_is_rejected() -> None:
    with pytest.raises(SpatialProvenanceError) as exc:
        _receipt("weathernext_005", native_resolution="0p1deg")
    assert exc.value.reason_code == "GRID_RESOLUTION_DRIFT"


def test_weathernext_interpolation_drift_is_rejected() -> None:
    with pytest.raises(SpatialProvenanceError) as exc:
        _receipt("weathernext_005", interpolation_mode="surface_grid_cell")
    assert exc.value.reason_code == "INTERPOLATION_MODE_DRIFT"


def test_public_transport_interpolation_identity_must_be_explicit() -> None:
    with pytest.raises(SpatialProvenanceError) as exc:
        _receipt("icon_d2", interpolation_mode="unknown")
    assert exc.value.reason_code == "UNKNOWN_INTERPOLATION_IDENTITY"


def test_common_sample_detects_resolution_and_source_surface_drift() -> None:
    truth = _receipt("truth_05480")
    first = _receipt("icon_d2")
    second = _receipt("icon_d2", native_resolution="0p1deg")
    with pytest.raises(SpatialProvenanceError) as exc:
        validate_common_sample_spatial([first, second], truth_receipt=truth)
    assert exc.value.reason_code == "GRID_RESOLUTION_DRIFT"

    other_surface = _receipt("icon_d2", source_surface="provider_native_surface", interpolation_mode="native_grid_point")
    with pytest.raises(SpatialProvenanceError) as exc:
        validate_common_sample_spatial([first, other_surface], truth_receipt=truth)
    assert exc.value.reason_code == "SOURCE_SURFACE_DRIFT"


def test_common_sample_detects_interpolation_mode_drift() -> None:
    truth = _receipt("truth_05480")
    first = build_spatial_receipt(
        kind="forecast", location_id="station_05480", provider="custom_public", model_name="model-x",
        source_surface="public-grid", variable="temperature_2m", native_resolution="0p1deg",
        grid_role="provider_grid", sampling_mode="native_grid_point", interpolation_mode="native_grid_point",
    )
    second = build_spatial_receipt(
        kind="forecast", location_id="station_05480", provider="custom_public", model_name="model-x",
        source_surface="public-grid", variable="temperature_2m", native_resolution="0p1deg",
        grid_role="provider_grid", sampling_mode="transport_point", interpolation_mode="transport_interpolated_or_resampled",
    )
    with pytest.raises(SpatialProvenanceError) as exc:
        validate_common_sample_spatial([first, second], truth_receipt=truth)
    assert exc.value.reason_code == "INTERPOLATION_MODE_DRIFT"


def test_home_and_legacy_station_cannot_enter_measured_benchmark() -> None:
    with pytest.raises(SpatialProvenanceError) as exc:
        _receipt("home_forecast")
    assert exc.value.reason_code == "PRIVATE_HOME_BENCHMARK_FORBIDDEN"

    with pytest.raises(SpatialProvenanceError) as exc:
        _receipt("legacy_10416")
    assert exc.value.reason_code == "LEGACY_LOCATION_NOT_CANONICAL"


def test_blocked_evidence_is_machine_readable_and_coordinate_free() -> None:
    truth = _receipt("truth_05480")
    bad = deepcopy(_cases()["home_forecast"])
    try:
        home = build_spatial_receipt(**bad)
    except SpatialProvenanceError:
        home = build_spatial_receipt(
            kind="forecast", location_id="station_05480", provider="icon_d2", model_name="ICON-D2",
            source_surface="Open-Meteo Single Runs API", variable="temperature_2m",
            native_resolution="provider_native_not_exposed", grid_role="provider_grid",
            sampling_mode="transport_point", interpolation_mode="transport_interpolated_or_resampled",
        )
        home["location"]["id"] = "home"
    evidence = spatial_evidence(forecast_receipts=[home], truth_receipt=truth)
    assert evidence["state"] == "BLOCKED"
    assert evidence["reason_codes"] == ["SPATIAL_RECEIPT_IDENTITY_MISMATCH"]
    serialized = json.dumps(evidence, sort_keys=True).lower()
    assert "home_lat" not in serialized
    assert "home_lon" not in serialized
    assert '"latitude"' not in serialized
    assert '"longitude"' not in serialized


def test_spatial_receipt_tampering_is_detected() -> None:
    receipt = _receipt("icon_d2")
    receipt["grid"]["native_resolution"] = "0p1deg"
    with pytest.raises(SpatialProvenanceError) as exc:
        validate_spatial_receipt(receipt)
    assert exc.value.reason_code == "SPATIAL_RECEIPT_IDENTITY_MISMATCH"
