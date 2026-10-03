from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from rozkalns_weather import weathernext_canary


def _credential_file(tmp_path: Path) -> Path:
    credential = tmp_path / "weathernext-google.json"
    credential.write_text('{"fixture":"only"}', encoding="utf-8")
    credential.chmod(0o600)
    return credential


def test_init_is_exact_utc_hour() -> None:
    parsed = weathernext_canary.parse_init_utc("2026-10-03T18:00:00Z")
    assert parsed == datetime(2026, 10, 3, 18, tzinfo=timezone.utc)

    with pytest.raises(weathernext_canary.WeatherNextGCSCanaryError):
        weathernext_canary.parse_init_utc("2026-10-03T18:15:00Z")
    with pytest.raises(weathernext_canary.WeatherNextGCSCanaryError):
        weathernext_canary.parse_init_utc("2026-10-03T18:00:00+00:00")


def test_credential_mount_is_one_fixed_bounded_no_follow_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = _credential_file(tmp_path)
    monkeypatch.setattr(weathernext_canary, "FIXED_CREDENTIAL_PATH", credential)

    observed = weathernext_canary._require_fixed_credential(
        expected_uid=os.getuid()
    )
    assert observed == credential

    credential.unlink()
    credential.symlink_to(tmp_path / "missing.json")
    with pytest.raises(
        weathernext_canary.WeatherNextGCSCanaryError,
        match="metadata drifted",
    ):
        weathernext_canary._require_fixed_credential(expected_uid=os.getuid())


def test_canary_returns_only_sanitized_transport_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = {
        "state": "gcs_canary_complete",
        "location_id": "station_05480",
        "lead_count": 6,
        "materialized_scalar_count": 288,
        "schema_valid": True,
        "provenance_complete": True,
        "production_write_performed": False,
        "raw_values_exposed": False,
        "coordinates_exposed": False,
    }
    monkeypatch.setattr(weathernext_canary.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        weathernext_canary,
        "_fixed_credential_provider",
        lambda: object(),
    )
    monkeypatch.setattr(
        weathernext_canary,
        "read_private_first_access_gcs",
        lambda **kwargs: SimpleNamespace(evidence=evidence, run=object()),
    )

    observed = weathernext_canary.run_fixed_canary(
        datetime(2026, 10, 3, 18, tzinfo=timezone.utc)
    )
    assert observed == evidence
    rendered = json.dumps(observed)
    assert "credential" not in rendered
    assert "token" not in rendered
    assert "HOME_LAT" not in rendered
    assert "HOME_LON" not in rendered


def test_canary_source_has_one_fixed_secret_path_and_no_database_path() -> None:
    source = Path(weathernext_canary.__file__).read_text(encoding="utf-8")
    assert 'Path("/run/secrets/weathernext-google.json")' in source
    assert "/run/weathernext-binding" not in source
    assert "first-access-private.json" not in source
    assert "credentials/" not in source
    assert "devstorage.read_only" in source
    assert "load_credentials_from_file" in source
    assert "Database(" not in source
    assert "HOME_LAT" not in source
    assert "HOME_LON" not in source
