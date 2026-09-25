from __future__ import annotations

from copy import deepcopy

from rozkalns_weather.observation_revisions import build_dwd_observation_revision_evidence


def _row(*, value: float = 20.0, quality: str = "observed", retrieved: str = "2026-09-10T00:00:00Z") -> dict[str, object]:
    return {
        "source_provider": "DWD",
        "station_id": "05480",
        "location_id": "station_05480",
        "observed_at_utc": "2026-09-08T00:00:00Z",
        "variable": "temperature_2m",
        "value": value,
        "unit": "degC",
        "quality_status": quality,
        "source_metadata": {
            "source_authority": "DWD",
            "transport": "DWD CDC Open Data",
            "cdc_product_family": "air_temperature",
            "cdc_archive_code": "TU",
            "cdc_value_column": "TT_TU",
            "source_url": "https://opendata.dwd.de/example.zip",
            "retrieved_at_utc": retrieved,
        },
    }


def _snapshot(at: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {"retrieved_at_utc": at, "observations": rows}


def test_unchanged_reretrieval_becomes_stable_without_exposing_values() -> None:
    first = _row(retrieved="2026-09-10T00:00:00Z")
    second = _row(retrieved="2026-09-12T00:00:00Z")

    evidence = build_dwd_observation_revision_evidence(
        [
            _snapshot("2026-09-10T00:00:00Z", [first]),
            _snapshot("2026-09-12T00:00:00Z", [second]),
        ]
    )

    assert evidence["state"] == "PASS"
    assert evidence["verification_ready"] is True
    assert evidence["finality_counts"] == {"provisional": 0, "revised": 0, "stable": 1}
    assert evidence["reason_codes"] == []
    assert len(evidence["truth_revision_set_sha256"]) == 64
    assert evidence["privacy"]["raw_values_exposed"] is False
    assert evidence["privacy"]["source_urls_exposed"] is False
    assert "20.0" not in str(evidence)
    assert "example.zip" not in str(evidence)


def test_legitimate_revision_is_explicit_and_not_fabricated_as_final() -> None:
    first = _row(value=20.0, retrieved="2026-09-10T00:00:00Z")
    second = _row(value=20.4, retrieved="2026-09-10T12:00:00Z")

    evidence = build_dwd_observation_revision_evidence(
        [
            _snapshot("2026-09-10T00:00:00Z", [first]),
            _snapshot("2026-09-10T12:00:00Z", [second]),
        ]
    )

    assert evidence["state"] == "WARN"
    assert evidence["verification_ready"] is False
    assert evidence["finality_counts"]["revised"] == 1
    assert "OBSERVATION_REVISED" in evidence["reason_codes"]
    assert "official DWD" in evidence["contract_finality"]


def test_conflicting_revision_inside_one_retrieval_blocks() -> None:
    first = _row(value=20.0)
    conflicting = _row(value=21.0)

    evidence = build_dwd_observation_revision_evidence(
        [_snapshot("2026-09-10T00:00:00Z", [first, conflicting])]
    )

    assert evidence["state"] == "BLOCKED"
    assert evidence["verification_ready"] is False
    assert "CONFLICTING_REVISION" in evidence["reason_codes"]


def test_late_revision_outside_declared_window_blocks() -> None:
    first = _row(value=20.0, retrieved="2026-09-02T00:00:00Z")
    first["observed_at_utc"] = "2026-09-01T00:00:00Z"
    second = _row(value=20.5, retrieved="2026-09-10T00:00:00Z")
    second["observed_at_utc"] = "2026-09-01T00:00:00Z"

    evidence = build_dwd_observation_revision_evidence(
        [
            _snapshot("2026-09-02T00:00:00Z", [first]),
            _snapshot("2026-09-10T00:00:00Z", [second]),
        ],
        revision_window_hours=168.0,
    )

    assert evidence["state"] == "BLOCKED"
    assert "OBSERVATION_REVISED" in evidence["reason_codes"]
    assert "LATE_REVISION_OUTSIDE_WINDOW" in evidence["reason_codes"]


def test_disappearing_sample_blocks() -> None:
    evidence = build_dwd_observation_revision_evidence(
        [
            _snapshot("2026-09-10T00:00:00Z", [_row(retrieved="2026-09-10T00:00:00Z")]),
            _snapshot("2026-09-10T12:00:00Z", []),
        ]
    )

    assert evidence["state"] == "BLOCKED"
    assert "SAMPLE_DISAPPEARED" in evidence["reason_codes"]


def test_provenance_loss_and_retroactive_quality_change_are_detected() -> None:
    first = _row(quality="observed", retrieved="2026-09-10T00:00:00Z")
    second = _row(quality="revised", retrieved="2026-09-10T12:00:00Z")
    second_metadata = deepcopy(second["source_metadata"])
    del second_metadata["source_url"]
    second["source_metadata"] = second_metadata

    evidence = build_dwd_observation_revision_evidence(
        [
            _snapshot("2026-09-10T00:00:00Z", [first]),
            _snapshot("2026-09-10T12:00:00Z", [second]),
        ]
    )

    assert evidence["state"] == "BLOCKED"
    assert "SOURCE_PROVENANCE_LOST" in evidence["reason_codes"]
    assert "QUALITY_STATUS_CHANGED" in evidence["reason_codes"]
    assert "OBSERVATION_REVISED" in evidence["reason_codes"]


def test_same_inputs_reproduce_same_truth_revision_set_identity() -> None:
    retrievals = [
        _snapshot("2026-09-10T00:00:00Z", [_row(retrieved="2026-09-10T00:00:00Z")]),
        _snapshot("2026-09-12T00:00:00Z", [_row(retrieved="2026-09-12T00:00:00Z")]),
    ]

    first = build_dwd_observation_revision_evidence(deepcopy(retrievals))
    second = build_dwd_observation_revision_evidence(deepcopy(retrievals))

    assert first["truth_revision_set_sha256"] == second["truth_revision_set_sha256"]
    assert first == second
