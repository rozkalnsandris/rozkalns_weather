from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .canonical_serialization import CanonicalSerializationError, canonical_sha256

SPATIAL_CONTRACT = "spatial-collocation-provenance-v1"
SPATIAL_SCHEMA_VERSION = 1
CANONICAL_BENCHMARK_LOCATION = "station_05480"
CANONICAL_BENCHMARK_STATION = "05480"
LEGACY_LOCATION = "station_10416"

_WEATHERNEXT_SURFACES: dict[str, dict[str, str]] = {
    "BigQuery WeatherNext 3 0p05": {
        "native_resolution": "0p05deg",
        "grid_role": "station_head",
        "sampling_mode": "station_head",
        "interpolation_mode": "station_head",
    },
    "BigQuery WeatherNext 3 0p1": {
        "native_resolution": "0p1deg",
        "grid_role": "surface",
        "sampling_mode": "surface_grid_cell",
        "interpolation_mode": "surface_grid_cell",
    },
}
_UNKNOWN_RESOLUTIONS = {"", "unknown", "unspecified", "none"}
_UNKNOWN_INTERPOLATION = {"", "unknown", "unspecified"}


class SpatialProvenanceError(ValueError):
    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code


def _sha256(value: object) -> str:
    try:
        return canonical_sha256(value)
    except CanonicalSerializationError as exc:
        raise SpatialProvenanceError(
            "MISSING_SPATIAL_IDENTITY",
            "spatial provenance must contain canonical finite JSON values",
        ) from exc


def _text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SpatialProvenanceError("MISSING_SPATIAL_IDENTITY", f"{field} is required")
    return text


def _location_identity(location_id: str, station_id: str | None) -> dict[str, object]:
    if location_id == "home":
        raise SpatialProvenanceError(
            "PRIVATE_HOME_BENCHMARK_FORBIDDEN",
            "private home identity is not admissible in measured benchmark spatial provenance",
        )
    if location_id == LEGACY_LOCATION:
        raise SpatialProvenanceError(
            "LEGACY_LOCATION_NOT_CANONICAL",
            "station_10416 is legacy compatibility evidence, not the canonical measured benchmark",
        )
    if location_id != CANONICAL_BENCHMARK_LOCATION:
        raise SpatialProvenanceError(
            "LOCATION_IDENTITY_MISMATCH",
            f"canonical verification requires {CANONICAL_BENCHMARK_LOCATION}",
        )
    if station_id not in (None, "", CANONICAL_BENCHMARK_STATION):
        raise SpatialProvenanceError(
            "STATION_IDENTITY_MISMATCH",
            "station id does not match canonical station_05480 benchmark identity",
        )
    return {
        "id": CANONICAL_BENCHMARK_LOCATION,
        "scope": "public_benchmark",
        "station_id": CANONICAL_BENCHMARK_STATION,
        "coordinates_exposed": False,
    }


def _validate_provider_surface(
    *,
    provider: str,
    source_surface: str,
    native_resolution: str,
    grid_role: str,
    sampling_mode: str,
    interpolation_mode: str,
) -> None:
    if native_resolution.casefold() in _UNKNOWN_RESOLUTIONS:
        raise SpatialProvenanceError(
            "UNKNOWN_GRID_RESOLUTION",
            "native grid resolution must be explicitly declared or explicitly provider-native-not-exposed",
        )
    if interpolation_mode.casefold() in _UNKNOWN_INTERPOLATION:
        raise SpatialProvenanceError(
            "UNKNOWN_INTERPOLATION_IDENTITY",
            "sampling/interpolation identity must be explicit",
        )

    if provider == "weathernext3":
        expected = _WEATHERNEXT_SURFACES.get(source_surface)
        if expected is None:
            raise SpatialProvenanceError(
                "WEATHERNEXT_SURFACE_MISMATCH",
                "WeatherNext source surface must preserve the 0.05 degree station-head or 0.1 degree surface identity",
            )
        actual = {
            "native_resolution": native_resolution,
            "grid_role": grid_role,
            "sampling_mode": sampling_mode,
            "interpolation_mode": interpolation_mode,
        }
        if actual != expected:
            if native_resolution != expected["native_resolution"]:
                reason = "GRID_RESOLUTION_DRIFT"
            elif interpolation_mode != expected["interpolation_mode"] or sampling_mode != expected["sampling_mode"]:
                reason = "INTERPOLATION_MODE_DRIFT"
            else:
                reason = "WEATHERNEXT_SURFACE_MISMATCH"
            raise SpatialProvenanceError(reason, "WeatherNext spatial identity drifted from its declared product surface")

    if source_surface == "Open-Meteo Single Runs API":
        if interpolation_mode != "transport_interpolated_or_resampled":
            raise SpatialProvenanceError(
                "UNKNOWN_INTERPOLATION_IDENTITY",
                "Open-Meteo transport values must retain the interpolation/resampling caveat",
            )
        if native_resolution not in {"provider_native_not_exposed", "0p02deg", "0p025deg", "0p1deg", "0p25deg"}:
            raise SpatialProvenanceError(
                "COLLOCATION_INCOMPATIBLE",
                "Open-Meteo native resolution must be explicit or marked provider_native_not_exposed",
            )


def build_spatial_receipt(
    *,
    kind: str,
    location_id: str,
    provider: str,
    model_name: str,
    source_surface: str,
    variable: str,
    native_resolution: str,
    grid_role: str,
    sampling_mode: str,
    interpolation_mode: str,
    transport_provider: str | None = None,
    station_id: str | None = None,
) -> dict[str, Any]:
    if kind not in {"forecast", "truth"}:
        raise SpatialProvenanceError("MISSING_SPATIAL_IDENTITY", "kind must be forecast or truth")
    location = _location_identity(_text(location_id, "location_id"), station_id)
    provider_text = _text(provider, "provider")
    model_text = _text(model_name, "model_name")
    surface_text = _text(source_surface, "source_surface")
    variable_text = _text(variable, "variable")
    resolution_text = _text(native_resolution, "native_resolution")
    role_text = _text(grid_role, "grid_role")
    sampling_text = _text(sampling_mode, "sampling_mode")
    interpolation_text = _text(interpolation_mode, "interpolation_mode")

    if kind == "truth":
        if station_id != CANONICAL_BENCHMARK_STATION:
            raise SpatialProvenanceError("STATION_IDENTITY_MISMATCH", "truth must bind exact DWD station 05480")
        if resolution_text != "point_station" or role_text != "observation_station":
            raise SpatialProvenanceError("COLLOCATION_INCOMPATIBLE", "truth must be an exact station observation identity")
        if sampling_text != "exact_station" or interpolation_text != "none_station_observation":
            raise SpatialProvenanceError("INTERPOLATION_MODE_DRIFT", "truth station observations cannot use grid interpolation")
    else:
        _validate_provider_surface(
            provider=provider_text,
            source_surface=surface_text,
            native_resolution=resolution_text,
            grid_role=role_text,
            sampling_mode=sampling_text,
            interpolation_mode=interpolation_text,
        )

    core: dict[str, object] = {
        "schema_version": SPATIAL_SCHEMA_VERSION,
        "contract": SPATIAL_CONTRACT,
        "kind": kind,
        "location": location,
        "source": {
            "provider": provider_text,
            "model_name": model_text,
            "source_surface": surface_text,
            "transport_provider": transport_provider,
        },
        "variable": variable_text,
        "grid": {
            "native_resolution": resolution_text,
            "role": role_text,
        },
        "collocation": {
            "sampling_mode": sampling_text,
            "interpolation_mode": interpolation_text,
        },
        "privacy": {
            "coordinates_exposed": False,
            "private_home_identity_exposed": False,
        },
    }
    return {
        **core,
        "spatial_identity_sha256": _sha256(core),
        "state": "PASS",
        "reason_codes": [],
    }


def validate_spatial_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    if receipt.get("contract") != SPATIAL_CONTRACT or receipt.get("schema_version") != SPATIAL_SCHEMA_VERSION:
        raise SpatialProvenanceError("MISSING_SPATIAL_IDENTITY", "unsupported spatial provenance contract")
    identity = str(receipt.get("spatial_identity_sha256") or "")
    core = {
        key: value
        for key, value in receipt.items()
        if key not in {"spatial_identity_sha256", "state", "reason_codes"}
    }
    if identity != _sha256(core):
        raise SpatialProvenanceError(
            "SPATIAL_RECEIPT_IDENTITY_MISMATCH",
            "spatial receipt identity does not reproduce from its canonical payload",
        )
    if receipt.get("state") != "PASS":
        raise SpatialProvenanceError("COLLOCATION_INCOMPATIBLE", "spatial receipt must be PASS")
    privacy = receipt.get("privacy")
    if not isinstance(privacy, Mapping) or privacy.get("coordinates_exposed") is not False:
        raise SpatialProvenanceError("COLLOCATION_INCOMPATIBLE", "spatial receipt must remain coordinate-free")
    return spatial_lineage_binding(receipt)


def spatial_lineage_binding(receipt: Mapping[str, object]) -> dict[str, object]:
    location = receipt.get("location")
    source = receipt.get("source")
    grid = receipt.get("grid")
    collocation = receipt.get("collocation")
    if not all(isinstance(item, Mapping) for item in (location, source, grid, collocation)):
        raise SpatialProvenanceError("MISSING_SPATIAL_IDENTITY", "spatial receipt structure is incomplete")
    return {
        "spatial_identity_sha256": str(receipt.get("spatial_identity_sha256") or ""),
        "kind": receipt.get("kind"),
        "location": {
            "id": location.get("id"),
            "scope": location.get("scope"),
            "station_id": location.get("station_id"),
            "coordinates_exposed": False,
        },
        "source": {
            "provider": source.get("provider"),
            "model_name": source.get("model_name"),
            "source_surface": source.get("source_surface"),
            "transport_provider": source.get("transport_provider"),
        },
        "variable": receipt.get("variable"),
        "grid": dict(grid),
        "collocation": dict(collocation),
    }


def validate_common_sample_spatial(
    forecast_receipts: Sequence[Mapping[str, object]],
    *,
    truth_receipt: Mapping[str, object],
) -> dict[str, Any]:
    if not forecast_receipts:
        raise SpatialProvenanceError("EMPTY_SPATIAL_SAMPLE", "at least one forecast spatial receipt is required")

    truth_binding = validate_spatial_receipt(truth_receipt)
    if truth_binding["kind"] != "truth":
        raise SpatialProvenanceError("COLLOCATION_INCOMPATIBLE", "truth receipt must have kind=truth")
    truth_location = truth_binding["location"]
    if truth_location["id"] != CANONICAL_BENCHMARK_LOCATION or truth_location["station_id"] != CANONICAL_BENCHMARK_STATION:
        raise SpatialProvenanceError("STATION_IDENTITY_MISMATCH", "truth receipt is not canonical station_05480")

    bindings: list[dict[str, object]] = []
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for receipt in forecast_receipts:
        binding = validate_spatial_receipt(receipt)
        if binding["kind"] != "forecast":
            raise SpatialProvenanceError("COLLOCATION_INCOMPATIBLE", "forecast sample contains non-forecast spatial receipt")
        location = binding["location"]
        if location["id"] != truth_location["id"]:
            raise SpatialProvenanceError("LOCATION_IDENTITY_MISMATCH", "forecast and truth benchmark locations differ")
        source = binding["source"]
        key = (str(source["provider"]), str(source["model_name"]), str(binding["variable"]))
        groups[key].append(binding)
        bindings.append(binding)

    for key, group in groups.items():
        surfaces = {str(item["source"]["source_surface"]) for item in group}
        resolutions = {str(item["grid"]["native_resolution"]) for item in group}
        modes = {
            (str(item["collocation"]["sampling_mode"]), str(item["collocation"]["interpolation_mode"]))
            for item in group
        }
        if len(surfaces) > 1:
            raise SpatialProvenanceError("SOURCE_SURFACE_DRIFT", f"source surface drift for {key}")
        if len(resolutions) > 1:
            raise SpatialProvenanceError("GRID_RESOLUTION_DRIFT", f"grid resolution drift for {key}")
        if len(modes) > 1:
            raise SpatialProvenanceError("INTERPOLATION_MODE_DRIFT", f"sampling/interpolation drift for {key}")

    bindings.sort(key=lambda item: str(item["spatial_identity_sha256"]))
    identity_core = {
        "benchmark_location_id": CANONICAL_BENCHMARK_LOCATION,
        "truth_spatial_identity_sha256": truth_binding["spatial_identity_sha256"],
        "forecast_spatial_identities_sha256": [item["spatial_identity_sha256"] for item in bindings],
    }
    return {
        "schema_version": SPATIAL_SCHEMA_VERSION,
        "contract": SPATIAL_CONTRACT,
        "state": "PASS",
        "benchmark_location": {
            "id": CANONICAL_BENCHMARK_LOCATION,
            "station_id": CANONICAL_BENCHMARK_STATION,
            "coordinates_exposed": False,
        },
        "truth": truth_binding,
        "forecasts": bindings,
        "spatial_common_sample_identity_sha256": _sha256(identity_core),
        "complete": True,
        "reason_codes": [],
        "privacy": {
            "coordinates_exposed": False,
            "private_home_identity_exposed": False,
        },
    }


def spatial_evidence(
    *,
    forecast_receipts: Sequence[Mapping[str, object]],
    truth_receipt: Mapping[str, object],
) -> dict[str, object]:
    try:
        return validate_common_sample_spatial(forecast_receipts, truth_receipt=truth_receipt)
    except SpatialProvenanceError as exc:
        return {
            "schema_version": SPATIAL_SCHEMA_VERSION,
            "contract": SPATIAL_CONTRACT,
            "state": "BLOCKED",
            "reason_codes": [exc.reason_code],
            "complete": False,
            "privacy": {
                "coordinates_exposed": False,
                "private_home_identity_exposed": False,
            },
        }
