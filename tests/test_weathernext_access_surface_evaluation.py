import json
from pathlib import Path


def _evaluation() -> dict:
    return json.loads(Path("deploy/weathernext-access-surface-evaluation.json").read_text())


def test_bigquery_real_query_remains_blocked_at_existing_guard() -> None:
    evaluation = _evaluation()
    assert evaluation["issue"] == 122
    assert evaluation["canonical_location_id"] == "station_05480"
    constraints = evaluation["constraints"]
    assert constraints["bigquery_real_query_maximum_bytes_billed"] == 1_073_741_824
    assert constraints["bigquery_real_query_blocked"] is True
    assert constraints["private_google_access_authorized"] is False
    assert constraints["production_sqlite_write_authorized"] is False
    assert constraints["credential_iam_quota_mutation_authorized"] is False

    bigquery = evaluation["surfaces"]["bigquery"]
    assert bigquery["status"] == "BLOCKED_COST_GUARD"
    assert bigquery["real_query_allowed"] is False
    assert bigquery["alternate_query_retry_allowed"] is False


def test_gcs_statistics_is_candidate_without_requester_billing_or_live_authority() -> None:
    evaluation = _evaluation()
    gcs = evaluation["surfaces"]["gcs_statistics_zarr"]
    assert gcs["status"] == "PREFERRED_SOURCE_CANDIDATE"
    assert gcs["bucket"] == "gs://weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr/"
    assert gcs["requester_pays"] is False
    assert gcs["billing_project_header_required"] is False
    assert gcs["statistics"] == ["mean", "p10", "p25", "p50", "p75", "p90"]
    assert gcs["lead_time_axis"] == "continuous_1_hour"
    assert gcs["supports_0p05_station_surface"] is True
    assert gcs["supports_0p1_gridded_surface"] is True
    assert gcs["full_ensemble_bucket_allowed_for_first_access"] is False
    assert gcs["live_access_authorized"] is False

    decision = evaluation["decision"]
    assert decision["preferred_candidate"] == "gcs_statistics_zarr"
    assert decision["runtime_transport_changed_by_this_contract"] is False
    assert decision["live_probe_authorized"] is False


def test_earth_engine_remains_secondary_and_requires_new_control_plane_gate() -> None:
    ee = _evaluation()["surfaces"]["earth_engine"]
    assert ee["status"] == "SECONDARY_CANDIDATE_NEW_GATE_REQUIRED"
    assert ee["requires_registered_cloud_project"] is True
    assert ee["requires_earth_engine_api"] is True
    assert ee["has_separate_eecu_quota_model"] is True
    assert ee["live_access_authorized"] is False


def test_docs_preserve_authority_and_candidate_semantics() -> None:
    evaluation_doc = Path("docs/WEATHERNEXT_ACCESS_SURFACES.md").read_text()
    first_access_doc = Path("docs/WEATHERNEXT_FIRST_ACCESS.md").read_text()
    overview_doc = Path("docs/WEATHERNEXT3.md").read_text()

    assert "GCS precomputed statistics Zarr" in evaluation_doc
    assert "BigQuery **real query is blocked**" in evaluation_doc
    assert "source-only" in evaluation_doc
    assert "BigQuery real-query path remains blocked" in first_access_doc
    assert "Preferred source candidate: **GCS precomputed statistics Zarr**" in first_access_doc
    assert "station_05480" in overview_doc
    assert "MVP izvēle: **BigQuery**" not in overview_doc
