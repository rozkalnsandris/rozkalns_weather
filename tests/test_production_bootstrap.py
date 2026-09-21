from __future__ import annotations
from datetime import date,timedelta
import json
import pytest
from rozkalns_weather.cli import main as cli_main
from rozkalns_weather.locations import PUBLIC_BENCHMARK_LOCATION
from rozkalns_weather.production_bootstrap import build_production_bootstrap_plan,evaluate_resume_evidence

def _plan():
    return build_production_bootstrap_plan(source_sha="a"*40,start=date(2026,4,2),end=date(2026,4,15),recovery_decision="verified_backup_available")

def _runs(start,end):
    out=[]; cur=start
    while cur<=end:
        for h in (0,6,12,18): out.append(f"{cur.isoformat()}T{h:02d}:00:00Z")
        cur+=timedelta(days=1)
    return out

def _complete():
    plan=_plan(); runs=_runs(date(2026,4,2),date(2026,4,15))
    def model(): return {"completed_runs":list(runs),"revision_drift_runs":[],"unexpected_runs":[],"database_ahead_of_checkpoint":False}
    return {"bootstrap_fingerprint":plan["bootstrap_fingerprint"],"recovery_decision":"verified_backup_available",
      "schema":{"state":"ready","implicit_migration_performed":False},
      "truth":{"station_id":"05480","location_id":PUBLIC_BENCHMARK_LOCATION.id,"completed_chunks":["2026-04-02..2026-04-15"],"database_ahead_of_checkpoint":False},
      "forecasts":{"icon_d2":model(),"ecmwf_ifs":model(),"ecmwf_aifs":model()},"integrity":{"ok":True}}

def test_plan_is_source_ready_for_explicit_dwd_cdc_05480_without_granting_data_authority():
    p=_plan()
    assert p["state"]=="SOURCE_READY" and p["block_reasons"]==[]
    assert p["identity"]["truth_station_id"]=="05480"
    assert p["identity"]["benchmark_location_id"]==PUBLIC_BENCHMARK_LOCATION.id
    assert p["identity"]["truth_variables"]==["temperature_2m","precipitation_1h","wind_gust_10m"]
    assert p["truth_transport"]["transport"]=="DWD CDC Open Data"
    assert p["truth_transport"]["nearest_station_fallback_allowed"] is False
    assert p["truth_transport"]["third_party_truth_allowed"] is False
    assert p["truth_transport"]["live_backfill_allowed"] is False
    assert p["production_data_authority_granted"] is False

def test_complete_evidence_can_pass_source_resume_validation_but_never_grants_write_authority():
    r=evaluate_resume_evidence(_plan(),_complete())
    assert r["state"]=="PASS" and r["block_reasons"]==[]
    assert r["production_data_authority_granted"] is False

def test_station_substitution_fails_closed():
    e=_complete(); e["truth"]["station_id"]="05481"
    assert "TRUTH_STATION_MISMATCH" in evaluate_resume_evidence(_plan(),e)["block_reasons"]

def test_plan_rejects_unbounded_window_and_unsupported_recovery():
    with pytest.raises(ValueError,match="180"):
        build_production_bootstrap_plan(source_sha="a"*40,start=date(2026,4,2),end=date(2026,10,1),recovery_decision="verified_backup_available")
    with pytest.raises(ValueError,match="unsupported recovery"):
        build_production_bootstrap_plan(source_sha="a"*40,start=date(2026,4,2),end=date(2026,4,3),recovery_decision="auto_restore")

def test_resume_evidence_rejects_private_fields():
    e=_complete(); e["database_path"]="/private/weather.db"
    with pytest.raises(ValueError,match="forbidden private field"): evaluate_resume_evidence(_plan(),e)

def test_production_bootstrap_plan_cli_is_source_ready_but_data_authority_false(monkeypatch,capsys):
    monkeypatch.setattr("sys.argv",["rozkalns-weather","production-bootstrap-plan","--source-sha","d"*40,"--start","2026-04-02","--end","2026-04-03","--recovery-decision","owner_accepts_proceeding_without_prewrite_backup"])
    cli_main(); payload=json.loads(capsys.readouterr().out)
    assert payload["state"]=="SOURCE_READY"
    assert payload["production_data_authority_granted"] is False
