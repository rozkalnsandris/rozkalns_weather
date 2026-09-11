from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

from rozkalns_weather.cli import main as cli_main
from rozkalns_weather.corpus_reporting import public_corpus_report
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation
from rozkalns_weather.providers.open_meteo import ECMWF_AIFS, ECMWF_IFS, ICON_D2, OpenMeteoModel
from rozkalns_weather.verification import LEAD_BUCKETS

UTC = timezone.utc
MODELS = (ICON_D2, ECMWF_IFS, ECMWF_AIFS)


def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'weather.db'}")
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


def _run(
    model: OpenMeteoModel,
    init: datetime,
    *,
    value: float = 10.0,
    model_version: str | None = "fixture-v1",
    retrieved_at: datetime | None = None,
    omit_lead_bucket: str | None = None,
) -> ForecastRun:
    representative_leads = tuple(
        float(lower)
        for lower, _upper, label in LEAD_BUCKETS
        if lower < model.forecast_days * 24 and label != omit_lead_bucket
    )
    return ForecastRun(
        provider=model.provider_id,
        model_provider=model.model_provider,
        model_name=model.model_name,
        model_version=model_version,
        init_time_utc=init,
        retrieved_at_utc=retrieved_at or init,
        init_time_quality="single_runs_explicit",
        source_surface="fixture-single-runs",
        values=tuple(
            ForecastValue(
                valid_time_utc=init + timedelta(hours=lead),
                lead_hours=lead,
                variable="temperature_2m",
                value=value,
                unit="degC",
            )
            for lead in representative_leads
        ),
    )


def _populate_complete_day(
    database: Database,
    *,
    omit_observation_hour: int | None = None,
    omit_forecast: tuple[str, int] | None = None,
    missing_model_version_provider: str | None = None,
    omit_lead_bucket: tuple[str, str] | None = None,
) -> None:
    for hour in (0, 6, 12, 18):
        init = datetime(2026, 4, 2, hour, tzinfo=UTC)
        for model in MODELS:
            if omit_forecast == (model.provider_id, hour):
                continue
            version = None if model.provider_id == missing_model_version_provider else "fixture-v1"
            omitted_bucket = omit_lead_bucket[1] if omit_lead_bucket and omit_lead_bucket[0] == model.provider_id else None
            database.insert_forecast_run(
                _run(model, init, model_version=version, omit_lead_bucket=omitted_bucket),
                location_id=DWD_10416.id,
            )
        if hour != omit_observation_hour:
            database.insert_observations(
                [
                    Observation(
                        source_provider="DWD",
                        station_id="10416",
                        location_id=DWD_10416.id,
                        observed_at_utc=init,
                        variable="temperature_2m",
                        value=9.5,
                        unit="degC",
                    )
                ]
            )


def test_complete_common_day_passes_and_is_read_only(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _populate_complete_day(database)
    path = Path(database.path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    report = public_corpus_report(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["state"] == "PASS"
    assert report["block_reasons"] == []
    assert report["warn_reasons"] == []
    assert report["read_only"] is True
    assert report["observations"]["missing_truth_times"]["count"] == 0
    assert all(item["expected_runs"] == 4 and item["present_runs"] == 4 for item in report["models"])
    assert all(item["by_run_hour_utc"]["00"]["expected_runs"] == 1 for item in report["models"])
    assert all(
        all(bucket["present_runs"] == 4 for bucket in item["lead_bucket_coverage"].values())
        for item in report["models"]
    )
    assert before == after


def test_missing_lead_bucket_blocks(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _populate_complete_day(database, omit_lead_bucket=("icon_d2", "24-48h"))

    report = public_corpus_report(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert report["state"] == "BLOCKED"
    assert "ICON_D2_LEAD_BUCKET_COVERAGE_GAPS" in report["block_reasons"]
    icon = next(item for item in report["models"] if item["provider"] == "icon_d2")
    assert icon["lead_bucket_coverage"]["24-48h"]["missing_runs"]["count"] == 4


def test_missing_runs_and_truth_gap_block(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _populate_complete_day(database, omit_observation_hour=18, omit_forecast=("icon_d2", 18))

    report = public_corpus_report(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert report["state"] == "BLOCKED"
    assert "ICON_D2_MISSING_EXPECTED_RUNS" in report["block_reasons"]
    assert "DWD_OBSERVATION_COVERAGE_GAPS" in report["block_reasons"]
    icon = next(item for item in report["models"] if item["provider"] == "icon_d2")
    assert icon["missing_runs"]["count"] == 1
    assert report["observations"]["missing_truth_times"]["count"] == 1


def test_revision_drift_blocks_without_rewriting_history(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _populate_complete_day(database)
    init = datetime(2026, 4, 2, 0, tzinfo=UTC)
    database.insert_forecast_run(_run(ECMWF_IFS, init, value=12.0, retrieved_at=init + timedelta(minutes=1)), location_id=DWD_10416.id)

    report = public_corpus_report(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert report["state"] == "BLOCKED"
    assert "ECMWF_IFS_REVISION_ANOMALIES" in report["block_reasons"]
    ifs = next(item for item in report["models"] if item["provider"] == "ecmwf_ifs")
    assert ifs["snapshot_count"] == 5
    assert ifs["revision_anomalies"]["count"] == 1


def test_missing_model_version_is_warn_not_fabricated(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _populate_complete_day(database, missing_model_version_provider="ecmwf_aifs")

    report = public_corpus_report(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert report["state"] == "WARN"
    assert "ECMWF_AIFS_MODEL_VERSION_MISSING" in report["warn_reasons"]
    aifs = next(item for item in report["models"] if item["provider"] == "ecmwf_aifs")
    assert aifs["provenance"]["model_version_missing_snapshots"] == 4


def test_historical_ifs_is_separate_from_common_readiness(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _populate_complete_day(database)
    historical = datetime(2026, 4, 1, 12, tzinfo=UTC)
    database.insert_forecast_run(_run(ECMWF_IFS, historical), location_id=DWD_10416.id)

    report = public_corpus_report(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert report["state"] == "PASS"
    assert report["historical_ifs_only"]["present_init_times"] == 1
    assert report["historical_ifs_only"]["excluded_from_common_readiness"] is True


def test_empty_corpus_reports_all_expected_runs_missing(tmp_path: Path) -> None:
    database = _database(tmp_path)

    report = public_corpus_report(database, start=date(2026, 4, 2), end=date(2026, 4, 2))

    assert report["state"] == "BLOCKED"
    for provider in ("icon_d2", "ecmwf_ifs", "ecmwf_aifs"):
        item = next(row for row in report["models"] if row["provider"] == provider)
        assert item["expected_runs"] == 4
        assert item["present_runs"] == 0
        assert item["missing_runs"]["count"] == 4


def test_cli_corpus_report_emits_machine_readable_pass(tmp_path: Path, monkeypatch, capsys) -> None:
    database = _database(tmp_path)
    _populate_complete_day(database)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'weather.db'}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["rozkalns-weather", "corpus-report", "--start", "2026-04-02", "--end", "2026-04-02"],
    )

    cli_main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "PASS"
    assert payload["read_only"] is True
    assert payload["authority"]["production_data_authority_granted"] is False
