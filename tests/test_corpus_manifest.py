from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

from rozkalns_weather.corpus_manifest import build_corpus_provenance_manifest, main as manifest_main
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation
from rozkalns_weather.providers.open_meteo import ECMWF_AIFS, ECMWF_IFS, ICON_D2, OpenMeteoModel

UTC = timezone.utc
MODELS = (ICON_D2, ECMWF_IFS, ECMWF_AIFS)


def _database(tmp_path: Path, name: str = "weather.db") -> Database:
    database = Database(f"sqlite:///{tmp_path / name}")
    database.initialize()
    database.ensure_location(
        location_id=DWD_10416.id,
        label=DWD_10416.label,
        lat=DWD_10416.lat,
        lon=DWD_10416.lon,
        elevation_m=DWD_10416.elevation_m,
        timezone=DWD_10416.timezone,
    )
    return database


def _run(model: OpenMeteoModel, init: datetime, *, value: float = 10.0, model_version: str | None = "fixture-v1") -> ForecastRun:
    return ForecastRun(
        provider=model.provider_id,
        model_provider=model.model_provider,
        model_name=model.model_name,
        model_version=model_version,
        init_time_utc=init,
        retrieved_at_utc=init + timedelta(minutes=5),
        init_time_quality="single_runs_explicit",
        source_surface="fixture-single-runs",
        values=(
            ForecastValue(
                valid_time_utc=init + timedelta(hours=6),
                lead_hours=6.0,
                variable="temperature_2m",
                value=value,
                unit="degC",
            ),
        ),
    )


def _observation(at: datetime) -> Observation:
    return Observation(
        source_provider="DWD",
        station_id="10416",
        location_id=DWD_10416.id,
        observed_at_utc=at,
        variable="temperature_2m",
        value=9.5,
        unit="degC",
        quality_status="fixture",
    )


def _populate(database: Database, *, reverse: bool = False) -> None:
    items = list(MODELS)
    if reverse:
        items.reverse()
    init = datetime(2026, 4, 2, 0, tzinfo=UTC)
    for model in items:
        database.insert_forecast_run(_run(model, init), location_id=DWD_10416.id)
    database.insert_observations([_observation(init + timedelta(hours=6))])


def test_manifest_passes_is_stable_and_read_only(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _populate(database)
    path = Path(database.path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    first = build_corpus_provenance_manifest(database, start=date(2026, 4, 2), end=date(2026, 4, 2))
    second = build_corpus_provenance_manifest(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert first["state"] == "PASS"
    assert first["read_only"] is True
    assert first["aggregate_checksum_sha256"] == second["aggregate_checksum_sha256"]
    assert first["common_window"]["forecast_snapshots"]["count"] == 3
    assert first["common_window"]["observations"]["count"] == 1
    assert first["privacy"]["coordinates_exposed"] is False
    assert before == after


def test_manifest_checksum_is_independent_of_insertion_order(tmp_path: Path) -> None:
    first_db = _database(tmp_path, "first.db")
    second_db = _database(tmp_path, "second.db")
    _populate(first_db, reverse=False)
    _populate(second_db, reverse=True)

    first = build_corpus_provenance_manifest(first_db, start=date(2026, 4, 2), end=date(2026, 4, 2))
    second = build_corpus_provenance_manifest(second_db, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert first["aggregate_checksum_sha256"] == second["aggregate_checksum_sha256"]
    assert first["common_window"]["forecast_snapshots"]["entries"] == second["common_window"]["forecast_snapshots"]["entries"]


def test_broken_revision_chain_blocks(tmp_path: Path) -> None:
    database = _database(tmp_path)
    init = datetime(2026, 4, 2, 0, tzinfo=UTC)
    database.insert_forecast_run(_run(ECMWF_IFS, init), location_id=DWD_10416.id)
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO forecast_runs (
                provider,model_provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,
                init_time_quality,source_surface,raw_payload_hash,revision,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ECMWF_IFS.provider_id,
                ECMWF_IFS.model_provider,
                ECMWF_IFS.model_name,
                "fixture-v1",
                DWD_10416.id,
                "2026-04-02T00:00:00Z",
                "2026-04-02T00:10:00Z",
                "single_runs_explicit",
                "fixture-single-runs",
                "b" * 64,
                3,
                "ok",
            ),
        )

    manifest = build_corpus_provenance_manifest(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert manifest["state"] == "BLOCKED"
    assert "BROKEN_REVISION_CHAIN" in manifest["block_reasons"]


def test_duplicate_revision_identity_blocks(tmp_path: Path) -> None:
    database = _database(tmp_path)
    init = datetime(2026, 4, 2, 0, tzinfo=UTC)
    database.insert_forecast_run(_run(ICON_D2, init), location_id=DWD_10416.id)
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO forecast_runs (
                provider,model_provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,
                init_time_quality,source_surface,raw_payload_hash,revision,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ICON_D2.provider_id,
                ICON_D2.model_provider,
                ICON_D2.model_name,
                "fixture-v1",
                DWD_10416.id,
                "2026-04-02T00:00:00Z",
                "2026-04-02T00:11:00Z",
                "single_runs_explicit",
                "fixture-single-runs",
                "c" * 64,
                1,
                "ok",
            ),
        )

    manifest = build_corpus_provenance_manifest(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert manifest["state"] == "BLOCKED"
    assert "DUPLICATE_SNAPSHOT_IDENTITY" in manifest["block_reasons"]


def test_missing_provenance_and_unexpected_provider_block(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO forecast_runs (
                provider,model_provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,
                init_time_quality,source_surface,raw_payload_hash,revision,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "mystery_model",
                "Mystery",
                "Mystery Model",
                "v1",
                DWD_10416.id,
                "2026-04-02T00:00:00Z",
                "2026-04-02T00:05:00Z",
                "explicit",
                "fixture",
                "d" * 64,
                1,
                "ok",
            ),
        )
        connection.execute(
            """INSERT INTO forecast_runs (
                provider,model_provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,
                init_time_quality,source_surface,raw_payload_hash,revision,status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ECMWF_AIFS.provider_id,
                ECMWF_AIFS.model_provider,
                ECMWF_AIFS.model_name,
                "v1",
                DWD_10416.id,
                "2026-04-02T06:00:00Z",
                "2026-04-02T06:05:00Z",
                "single_runs_explicit",
                "fixture-single-runs",
                None,
                1,
                "ok",
            ),
        )

    manifest = build_corpus_provenance_manifest(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert manifest["state"] == "BLOCKED"
    assert "UNEXPECTED_PROVIDER_IDENTITY" in manifest["block_reasons"]
    assert "MISSING_FORECAST_PROVENANCE" in manifest["block_reasons"]


def test_unexpected_schema_blocks(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.connect() as connection:
        connection.execute("CREATE TABLE unexpected_fixture_table (id INTEGER PRIMARY KEY)")

    manifest = build_corpus_provenance_manifest(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert manifest["state"] == "BLOCKED"
    assert "SCHEMA_TABLE_SET_MISMATCH" in manifest["block_reasons"]
    assert "SCHEMA_COLUMNS_MISMATCH:unexpected_fixture_table" in manifest["block_reasons"]


def test_historical_ifs_is_separate_from_common_window(tmp_path: Path) -> None:
    database = _database(tmp_path)
    historical = datetime(2026, 4, 1, 12, tzinfo=UTC)
    common = datetime(2026, 4, 2, 0, tzinfo=UTC)
    database.insert_forecast_run(_run(ECMWF_IFS, historical), location_id=DWD_10416.id)
    database.insert_forecast_run(_run(ECMWF_IFS, common), location_id=DWD_10416.id)

    manifest = build_corpus_provenance_manifest(database, start=date(2026, 4, 1), end=date(2026, 4, 2))

    assert manifest["state"] == "PASS"
    assert manifest["historical_ifs_only"]["forecast_snapshots"]["count"] == 1
    assert manifest["historical_ifs_only"]["excluded_from_common_readiness"] is True
    assert manifest["common_window"]["forecast_snapshots"]["count"] == 1


def test_pre_common_non_ifs_provider_blocks(tmp_path: Path) -> None:
    database = _database(tmp_path)
    historical = datetime(2026, 4, 1, 12, tzinfo=UTC)
    database.insert_forecast_run(_run(ICON_D2, historical), location_id=DWD_10416.id)

    manifest = build_corpus_provenance_manifest(database, start=date(2026, 4, 1), end=date(2026, 4, 2))

    assert manifest["state"] == "BLOCKED"
    assert "NON_IFS_PRE_COMMON_PROVIDER" in manifest["block_reasons"]


def test_cli_corpus_manifest_emits_machine_readable_pass(tmp_path: Path, monkeypatch, capsys) -> None:
    database = _database(tmp_path)
    _populate(database)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'weather.db'}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["python -m rozkalns_weather.corpus_manifest", "--start", "2026-04-02", "--end", "2026-04-02"],
    )

    manifest_main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "PASS"
    assert payload["contract"] == "corpus-provenance-manifest-v1"
    assert payload["read_only"] is True
    assert payload["authority"]["production_data_authority_granted"] is False
