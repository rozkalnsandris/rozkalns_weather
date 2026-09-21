from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.production_bootstrap import build_production_bootstrap_plan


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "deploy" / "dwd-10416-historical-truth-decision.json"
BOOTSTRAP_PATH = ROOT / "deploy" / "production-public-corpus-bootstrap.json"
BENCHMARK_PATH = ROOT / "deploy" / "dwd-cdc-benchmark-station.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_dwd_10416_historical_truth_decision_remains_as_audit_evidence() -> None:
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
    assert decision["station_mapping"] == {"wmo_station_id": "10416", "cdc_station_id": None, "status": "UNVERIFIED"}
    assert decision["rejected_behaviors"]["nearest_station_fallback"] is True
    assert decision["authority"]["source_auto_full_authorizes_production_write"] is False


def test_official_10416_evidence_still_does_not_claim_an_unproven_mapping() -> None:
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


def test_new_production_descriptor_explicitly_supersedes_10416_as_benchmark() -> None:
    descriptor = _load(BOOTSTRAP_PATH)
    benchmark = _load(BENCHMARK_PATH)
    assert descriptor["status"] == "SOURCE_READY_REQUIRES_EXPLICIT_LIVE_DATA_AUTHORIZATION"
    assert descriptor["location"]["location_id"] == "station_dwd_cdc_01303"
    assert descriptor["location"]["truth_station_id"] == "01303"
    assert descriptor["location"]["benchmark_decision_contract"] == "deploy/dwd-cdc-benchmark-station.json"
    assert benchmark["decision"] == "VERIFIED_DWD_CDC_BENCHMARK_STATION"
    assert benchmark["station"]["dwd_station_id"] == "01303"
    assert descriptor["truth_scope"]["nearest_station_fallback_allowed"] is False
    assert descriptor["truth_scope"]["third_party_truth_allowed"] is False
    assert descriptor["truth_scope"]["live_backfill_authorized"] is False
    assert descriptor["authority"]["source_merge_authorizes_production_write"] is False


def test_runtime_plan_is_source_ready_but_never_grants_live_data_authority() -> None:
    from datetime import date

    plan = build_production_bootstrap_plan(
        source_sha="a" * 40,
        start=date(2026, 4, 2),
        end=date(2026, 4, 3),
        recovery_decision="verified_backup_available",
    )
    assert plan["state"] == "READY_FOR_EXPLICIT_LIVE_DATA_AUTHORIZATION"
    assert plan["block_reasons"] == []
    assert plan["identity"]["truth_station_id"] == "01303"
    assert plan["identity"]["benchmark_location_id"] == "station_dwd_cdc_01303"
    assert plan["production_data_authority_granted"] is False
