from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _json(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_icon_d2_exact_run_transport_decision_fails_closed() -> None:
    decision = _json("deploy/icon-d2-exact-run-transport-decision.json")
    assert decision["status"] == "NO_COMPLETE_ICON_D2_EXACT_RUN_ARCHIVE_TRANSPORT"
    assert decision["provider"] == "icon_d2"
    assert decision["benchmark_location_id"] == "station_05480"
    assert decision["frozen_window"]["run_hours_utc"] == [0, 6, 12, 18]
    assert decision["frozen_window"]["expected_runs"] == 648
    prefix = decision["preserved_production_prefix"]
    assert prefix["completed_runs"] == 279
    assert prefix["last_completed_init_time_utc"] == "2026-06-10T12:00:00Z"
    assert prefix["next_required_init_time_utc"] == "2026-06-10T18:00:00Z"
    assert prefix["skip_ahead_allowed"] is False


def test_decision_rejects_approximation_and_preserves_integrity() -> None:
    decision = _json("deploy/icon-d2-exact-run-transport-decision.json")
    alternatives = {item["transport"]: item for item in decision["alternatives"]}
    assert alternatives["Open-Meteo Historical Forecast API"]["decision"] == "REJECTED"
    assert alternatives["Open-Meteo Previous Runs API"]["decision"] == "REJECTED"
    assert alternatives["Open-Meteo AWS data_run objects"]["decision"] == "REJECTED_FOR_FROZEN_WINDOW"
    assert alternatives["Open-Meteo AWS data_spatial objects"]["decision"] == "REJECTED_FOR_FROZEN_WINDOW"
    assert alternatives["Open-Meteo rolling timeseries objects"]["decision"] == "REJECTED"
    integrity = decision["integrity"]
    assert integrity["missing_runs_allowed"] is False
    assert integrity["synthetic_or_imputed_values_allowed"] is False
    assert integrity["alternate_model_substitution_allowed"] is False
    assert integrity["provider_relabelling_allowed"] is False
    assert integrity["ordered_checkpoint_prefix_required"] is True
    authority = decision["authority"]
    assert authority["source_merge_authorizes_live_retry"] is False
    assert authority["production_resume_allowed"] is False
    assert authority["production_corpus_write_authority"] is False


def test_production_bootstrap_descriptor_preserves_legacy_blocker_but_uses_verified_fixed_window() -> None:
    descriptor = _json("deploy/production-public-corpus-bootstrap.json")
    assert descriptor["status"] == "SOURCE_READY_REQUIRES_EXACT_LIVE_DATA_AUTHORITY"
    scope = descriptor["forecast_scope"]
    assert scope["exact_run_transport_decision_contract"] == "deploy/exact-run-common-window.json"
    assert scope["exact_run_transport_status"] == "VERIFIED_COMPLETE_FIXED_WINDOW"
    assert scope["exact_init_required"] is True
    assert scope["full_horizon_required"] is True
    assert scope["live_backfill_allowed"] is False
    assert scope["skip_unavailable_run_allowed"] is False
    assert scope["synthetic_or_imputed_run_allowed"] is False
    preserved = descriptor["preserved_historical_evidence"]
    assert preserved["legacy_exact_run_decision_contract"] == "deploy/icon-d2-exact-run-transport-decision.json"
    assert preserved["legacy_block_reason"] == "NO_COMPLETE_ICON_D2_EXACT_RUN_ARCHIVE_TRANSPORT"
    assert preserved["icon_d2_completed_runs"] == 279
    assert preserved["legacy_checkpoint_reusable_for_new_window"] is False
