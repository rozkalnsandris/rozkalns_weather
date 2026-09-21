from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from rozkalns_weather.production_bootstrap import build_production_bootstrap_plan


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "deploy" / "dwd-10416-historical-truth-decision.json"
BOOTSTRAP_PATH = ROOT / "deploy" / "production-public-corpus-bootstrap.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_dwd_10416_historical_truth_decision_is_explicit_and_fail_closed() -> None:
    decision = _load(DECISION_PATH)
    assert decision["contract"] == "rozkalns-weather.dwd-10416-historical-truth-decision.v1"
    assert decision["state"] == "BLOCKED"
    assert decision["decision"] == "NO_VERIFIED_DWD_HISTORICAL_TRANSPORT"
    assert decision["source_authority"] == "DWD"
    assert decision["benchmark"] == {
        "location_id": "station_10416",
        "wmo_station_id": "10416",
        "frozen_window": {"start_date": "2026-04-02", "end_date": "2026-09-10"},
    }
    assert decision["station_mapping"] == {
        "wmo_station_id": "10416",
        "cdc_station_id": None,
        "status": "UNVERIFIED",
    }
    assert decision["variable_coverage"]["status"] == "NOT_VERIFIED_FOR_EXACT_STATION_AND_FROZEN_WINDOW"
    assert decision["rejected_behaviors"] == {
        "nearest_station_fallback": True,
        "station_substitution": True,
        "coordinate_nearest_lookup": True,
        "synthetic_truth": True,
        "implicit_third_party_provider_change": True,
    }
    assert decision["authority"]["source_auto_full_authorizes_production_write"] is False
    assert decision["authority"]["source_merge_authorizes_production_write"] is False


def test_official_evidence_does_not_claim_an_unproven_station_mapping() -> None:
    decision = _load(DECISION_PATH)
    evidence = decision["reviewed_official_evidence"]
    assert isinstance(evidence, list)
    assert len(evidence) == 4
    assert all(str(item["url"]).startswith("https://opendata.dwd.de/") for item in evidence)
    assert all(
        item.get("proves_cdc_station_mapping") is not True
        and item.get("proves_wmo_10416_mapping") is not True
        and item.get("proves_current_wmo_mapping") is not True
        and item.get("proves_frozen_window") is not True
        for item in evidence
    )


def test_legacy_decision_remains_audit_evidence_while_new_descriptor_pins_cdc_benchmark() -> None:
    descriptor = _load(BOOTSTRAP_PATH)
    truth = descriptor["truth_scope"]
    assert descriptor["status"] == "SOURCE_READY_REQUIRES_EXACT_LIVE_DATA_AUTHORITY"
    assert descriptor["location"]["location_id"] == "station_05480"
    assert descriptor["location"]["truth_station_id"] == "05480"
    assert truth["source_authority"] == "DWD"
    assert truth["transport"] == "DWD CDC Open Data"
    assert truth["station_id"] == "05480"
    assert truth["location_id"] == "station_05480"
    assert truth["historical_transport_status"] == "verified_frozen_window_product_coverage"
    assert truth["selected_common_window_start"] == "2026-08-13"
    assert truth["selected_common_window_end"] == "2026-08-26"
    assert truth["nearest_station_fallback_allowed"] is False
    assert truth["live_backfill_allowed"] is False
    forecast = descriptor["forecast_scope"]
    assert forecast["exact_run_transport_status"] == "VERIFIED_COMPLETE_FIXED_WINDOW"
    assert forecast["skip_unavailable_run_allowed"] is False
    preserved = descriptor["preserved_historical_evidence"]
    assert preserved["legacy_block_reason"] == "NO_COMPLETE_ICON_D2_EXACT_RUN_ARCHIVE_TRANSPORT"
    assert preserved["existing_rows_preserved"] is True
    assert preserved["existing_rows_deleted"] is False
    assert preserved["existing_rows_rewritten"] is False
    authority = descriptor["authority"]
    assert authority["source_auto_full_authorizes_production_write"] is False
    assert authority["source_merge_authorizes_production_write"] is False


def test_new_runtime_plan_preserves_cdc_truth_and_requires_separate_live_data_authority() -> None:
    plan = build_production_bootstrap_plan(
        source_sha="a" * 40,
        start=date(2026, 8, 13),
        end=date(2026, 8, 26),
        recovery_decision="verified_backup_available",
    )
    assert plan["state"] == "SOURCE_READY_REQUIRES_EXACT_LIVE_DATA_AUTHORITY"
    assert plan["block_reasons"] == []
    assert plan["identity"]["truth_station_id"] == "05480"
    assert plan["identity"]["benchmark_location_id"] == "station_05480"
    assert plan["identity"]["checkpoint_namespace"] == "fixed-window-20260813-20260826-v1"
    assert plan["production_data_authority_granted"] is False
