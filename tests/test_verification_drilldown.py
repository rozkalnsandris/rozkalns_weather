from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation
from rozkalns_weather.verification_drilldown import build_verification_drilldown, month_bounds


def _forecast(
    provider: str,
    version: str,
    *,
    init: str,
    valid: str,
    lead: float,
    variable: str = "temperature_2m",
    value: float = 10.0,
    statistic: str = "deterministic",
    revision: int = 1,
) -> dict[str, object]:
    return {
        "provider": provider,
        "model_name": provider,
        "model_version": version,
        "init_time_utc": init,
        "retrieved_at_utc": init,
        "revision": revision,
        "valid_time_utc": valid,
        "lead_hours": lead,
        "variable": variable,
        "statistic": statistic,
        "value": value,
    }


def _truth(valid: str, variable: str = "temperature_2m", value: float = 10.0) -> dict[str, object]:
    return {
        "source_provider": "DWD",
        "station_id": "10416",
        "location_id": DWD_10416.id,
        "observed_at_utc": valid,
        "variable": variable,
        "value": value,
    }


def _build(rows, truth):
    return build_verification_drilldown(
        forecast_rows=rows,
        observation_rows=truth,
        start=date(2026, 4, 1),
        end=date(2026, 4, 30),
    )


def test_april_month_clips_to_common_archive_start() -> None:
    assert month_bounds("2026-04") == (date(2026, 4, 2), date(2026, 4, 30))


def test_sparse_common_sample_exposes_missingness() -> None:
    v1 = "2026-04-10T06:00:00Z"
    v2 = "2026-04-10T07:00:00Z"
    init = "2026-04-10T00:00:00Z"
    rows = []
    for provider in ("icon_d2", "ecmwf_ifs", "ecmwf_aifs"):
        rows.append(_forecast(provider, "v1", init=init, valid=v1, lead=6, value=11.0))
    rows += [
        _forecast("icon_d2", "v1", init=init, valid=v2, lead=7, value=12.0),
        _forecast("ecmwf_ifs", "v1", init=init, valid=v2, lead=7, value=11.5),
    ]
    payload = _build(rows, [_truth(v1), _truth(v2, value=11.0)])
    slice_ = payload["deterministic"]["slices"][0]
    assert slice_["expected_n"] == 2
    assert slice_["total_common_n"] == 1
    metrics = {row["provider"]: row for row in slice_["cohorts"][0]["metrics"]}
    assert metrics["ecmwf_aifs"]["n"] == 1
    assert metrics["ecmwf_aifs"]["missingness"]["missing_n"] == 1
    assert metrics["icon_d2"]["missingness"]["excluded_non_common_n"] == 1
    assert metrics["icon_d2"]["probabilistic_metrics_eligible"] is False


def test_mixed_model_versions_are_split_into_exact_cohorts() -> None:
    init = "2026-04-11T00:00:00Z"
    valids = ["2026-04-11T06:00:00Z", "2026-04-11T07:00:00Z"]
    rows = []
    for index, valid in enumerate(valids):
        for provider in ("icon_d2", "ecmwf_ifs", "ecmwf_aifs"):
            version = "v2" if provider == "icon_d2" and index == 1 else "v1"
            rows.append(_forecast(provider, version, init=init, valid=valid, lead=6 + index))
    payload = _build(rows, [_truth(valid) for valid in valids])
    cohorts = payload["deterministic"]["slices"][0]["cohorts"]
    assert len(cohorts) == 2
    assert {cohort["comparison_cohort"]["icon_d2"] for cohort in cohorts} == {"v1", "v2"}
    assert all(len(cohort["common_sample_ids"]) == 1 for cohort in cohorts)


def test_missing_init_cycle_never_cross_matches_cycles() -> None:
    valid = "2026-04-12T12:00:00Z"
    rows = [
        _forecast("icon_d2", "v1", init="2026-04-12T06:00:00Z", valid=valid, lead=6),
        _forecast("ecmwf_ifs", "v1", init="2026-04-12T06:00:00Z", valid=valid, lead=6),
        _forecast("ecmwf_aifs", "v1", init="2026-04-12T00:00:00Z", valid=valid, lead=12),
    ]
    payload = _build(rows, [_truth(valid)])
    slices = payload["deterministic"]["slices"]
    assert {row["init_cycle_utc"] for row in slices} == {"00Z", "06Z"}
    assert all(row["total_common_n"] == 0 for row in slices)
    assert all(row["cohorts"] == [] for row in slices)


def test_genuine_ensemble_members_get_probabilistic_metrics() -> None:
    init = "2026-04-13T00:00:00Z"
    valid = "2026-04-13T06:00:00Z"
    rows = []
    for provider in ("icon_d2_eps", "ecmwf_ifs_ens", "ecmwf_aifs_ens"):
        rows += [
            _forecast(provider, "ens-v1", init=init, valid=valid, lead=6, variable="precipitation_1h", value=0.0, statistic="member_0"),
            _forecast(provider, "ens-v1", init=init, valid=valid, lead=6, variable="precipitation_1h", value=0.2, statistic="member_1"),
        ]
    rows += [
        _forecast("weathernext3", "wn3", init=init, valid=valid, lead=6, variable="precipitation_1h", value=0.1, statistic="p50"),
    ]
    payload = _build(rows, [_truth(valid, "precipitation_1h", 0.3)])
    metrics = payload["ensemble"]["slices"][0]["cohorts"][0]["metrics"]
    assert len(metrics) == 3
    assert all(row["member_input"] == "genuine_member_N_only" for row in metrics)
    assert all(row["mean_crps"] is not None for row in metrics)
    assert all(row["brier_score"] is not None for row in metrics)
    assert "weathernext3" not in payload["ensemble"]["providers"]


def test_api_and_pwa_expose_drilldown_navigation(tmp_path) -> None:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))
    valid = datetime(2026, 9, 10, 6, tzinfo=timezone.utc)
    init = datetime(2026, 9, 10, 0, tzinfo=timezone.utc)
    database.insert_observations([
        Observation(
            source_provider="DWD",
            station_id="10416",
            location_id=DWD_10416.id,
            observed_at_utc=valid,
            variable="temperature_2m",
            value=10.0,
            unit="degC",
        )
    ])
    metadata = {
        "icon_d2": ("DWD", "ICON-D2"),
        "ecmwf_ifs": ("ECMWF", "IFS HRES"),
        "ecmwf_aifs": ("ECMWF", "AIFS"),
    }
    for provider, (model_provider, model_name) in metadata.items():
        database.insert_forecast_run(
            ForecastRun(
                provider=provider,
                model_provider=model_provider,
                model_name=model_name,
                model_version="v1",
                init_time_utc=init,
                retrieved_at_utc=init,
                source_surface="fixture",
                values=(
                    ForecastValue(
                        valid_time_utc=valid,
                        lead_hours=6,
                        variable="temperature_2m",
                        statistic="deterministic",
                        value=11.0,
                        unit="degC",
                    ),
                ),
            ),
            location_id=DWD_10416.id,
        )
    response = client.get("/api/verification/drilldown?month=2026-09")
    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"] == "verification-drilldown-v1"
    assert payload["deterministic"]["slices"][0]["total_common_n"] == 1
    root = client.get("/").text
    script = client.get("/static/accuracy_v3.js").text
    assert 'id="drilldownMonth"' in root
    assert "sample_sufficiency_state" in script
    assert "missingness" in script
    assert "/api/verification/drilldown?month=" in script
