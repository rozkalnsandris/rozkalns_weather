from __future__ import annotations

from datetime import date
import io
import json
from pathlib import Path

import pytest

from rozkalns_weather.cli import main as cli_main
from rozkalns_weather.db import Database
from rozkalns_weather.rollout import (
    BOOTSTRAP_STAGE_ORDER,
    build_rollout_plan,
    validate_completed_stages,
    validate_post_rollout_evidence,
    validate_source_package,
    verify_sqlite_backup,
)


def test_source_package_contract_is_consistent_and_public_safe() -> None:
    result = validate_source_package()
    assert result["ok"] is True
    assert result["target_alias"] == "rozkalns-weather-public-rpi5"
    assert result["operation_id"] == "rozkalns-weather.public-runtime-release.v1"
    assert result["privacy"] == {
        "coordinates_exposed": False,
        "credentials_exposed": False,
        "host_private_paths_exposed": False,
    }


def test_rollout_plan_binds_exact_bounded_bootstrap_and_recovery() -> None:
    result = build_rollout_plan(
        source_sha="a" * 40,
        start=date(2026, 4, 2),
        end=date(2026, 4, 5),
        models="ecmwf_aifs,icon_d2,ecmwf_ifs",
        run_hours_utc="18,0,12,6",
        recovery_decision="verified_backup_available",
        completed_stages=BOOTSTRAP_STAGE_ORDER[:2],
    )
    assert result["state"] == "source_preflight_ready"
    assert result["bootstrap"]["inclusive_days"] == 4
    assert result["bootstrap"]["models"] == ["icon_d2", "ecmwf_ifs", "ecmwf_aifs"]
    assert result["bootstrap"]["run_hours_utc"] == [0, 6, 12, 18]
    assert result["bootstrap"]["truth_station_id"] == "10416"
    assert result["stage_state"]["next_stage"] == "readiness_check"
    assert result["recovery"]["automatic_restore_allowed"] is False
    assert result["live_authority_granted"] is False
    assert result["production_data_authority_granted"] is False
    serialized = json.dumps(result)
    assert "HOME_LAT" not in serialized
    assert "HOME_LON" not in serialized
    assert "/home/" not in serialized


def test_bootstrap_rejects_unbounded_or_unsupported_inputs() -> None:
    with pytest.raises(ValueError, match="180"):
        build_rollout_plan(
            source_sha="a" * 40,
            start=date(2026, 4, 2),
            end=date(2026, 10, 1),
            models="icon_d2,ecmwf_ifs,ecmwf_aifs",
            run_hours_utc="0,6,12,18",
            recovery_decision="verified_backup_available",
        )
    with pytest.raises(ValueError, match="exactly"):
        build_rollout_plan(
            source_sha="a" * 40,
            start=date(2026, 4, 2),
            end=date(2026, 4, 5),
            models="icon_d2,ecmwf_ifs",
            run_hours_utc="0,6,12,18",
            recovery_decision="verified_backup_available",
        )
    with pytest.raises(ValueError, match="exact ordered prefix"):
        validate_completed_stages(("volume_ensure", "readiness_check"))


def test_disposable_sqlite_backup_verification_is_sanitized(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    backup_path = tmp_path / "backup.db"
    database = Database(f"sqlite:///{source_path}")
    database.initialize()
    database.backup_to(backup_path)

    result = verify_sqlite_backup(backup_path)
    assert result["state"] == "verified"
    assert result["integrity_ok"] is True
    assert result["required_tables_present"] is True
    assert result["path_exposed"] is False
    assert str(tmp_path) not in json.dumps(result)


def _valid_evidence() -> dict[str, object]:
    providers = [
        {"id": "dwd_mosmix_l", "state": "ok"},
        {"id": "dwd_observations", "state": "ok"},
        {"id": "icon_d2", "state": "ok"},
        {"id": "ecmwf_ifs", "state": "ok"},
        {"id": "ecmwf_aifs", "state": "ok"},
        {
            "id": "weathernext3",
            "state": "access_pending",
            "required_for_runtime": False,
            "values_fabricated": False,
        },
    ]
    return {
        "source_sha": "b" * 40,
        "target_alias": "rozkalns-weather-public-rpi5",
        "operation_id": "rozkalns-weather.public-runtime-release.v1",
        "runtime_mode": "public-only",
        "storage_class": "docker_named_volume",
        "weather_data_retained": True,
        "endpoints": {
            "health_status": 200,
            "ready_status": 200,
            "provider_health_status": 200,
        },
        "readiness": {
            "ready": True,
            "database_state": "ready",
            "storage_class": "persistent_sqlite_file",
            "coordinates_exposed": False,
            "credentials_exposed": False,
            "database_path_exposed": False,
        },
        "providers": providers,
        "corpus_integrity": {"ok": True},
    }


def test_post_rollout_evidence_contract_passes_and_rejects_private_fields() -> None:
    result = validate_post_rollout_evidence(_valid_evidence())
    assert result["state"] == "verified"
    assert result["privacy"]["raw_logs_exposed"] is False

    bad = _valid_evidence()
    bad["raw_logs"] = "private runtime output"
    with pytest.raises(ValueError, match="forbidden private field"):
        validate_post_rollout_evidence(bad)


def test_rollout_preflight_cli_does_not_require_runtime_environment(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "rozkalns-weather",
            "rollout-preflight",
            "--source-sha",
            "c" * 40,
            "--start",
            "2026-04-02",
            "--end",
            "2026-04-03",
            "--models",
            "icon_d2,ecmwf_ifs,ecmwf_aifs",
            "--run-hours",
            "0,6,12,18",
            "--recovery-decision",
            "owner_accepts_proceeding_without_prewrite_backup",
        ],
    )
    cli_main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "source_preflight_ready"
    assert payload["privacy"]["credentials_exposed"] is False


def test_rollout_evidence_cli_reads_stdin_and_emits_only_sanitized_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["rozkalns-weather", "rollout-evidence-validate"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_valid_evidence())))
    cli_main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "verified"
    assert "endpoints" not in payload
    assert "corpus_integrity" not in payload
