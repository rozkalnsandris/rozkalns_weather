from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from rozkalns_weather import weathernext_canary


def _fixed_binding(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "binding"
    credentials = root / "credentials"
    root.mkdir(mode=0o700)
    credentials.mkdir(mode=0o700)
    private = root / "first-access-private.json"
    private.write_text(
        json.dumps(
            {
                "schema": weathernext_canary.PRIVATE_BINDING_SCHEMA,
                "credential_file": "google.json",
            }
        ),
        encoding="utf-8",
    )
    private.chmod(0o600)
    credential = credentials / "google.json"
    credential.write_text('{"fixture":"only"}', encoding="utf-8")
    credential.chmod(0o600)
    return root, credential


def test_init_is_exact_utc_hour() -> None:
    parsed = weathernext_canary.parse_init_utc("2026-10-03T18:00:00Z")
    assert parsed == datetime(2026, 10, 3, 18, tzinfo=timezone.utc)

    with pytest.raises(weathernext_canary.WeatherNextGCSCanaryError):
        weathernext_canary.parse_init_utc("2026-10-03T18:15:00Z")
    with pytest.raises(weathernext_canary.WeatherNextGCSCanaryError):
        weathernext_canary.parse_init_utc("2026-10-03T18:00:00+00:00")


def test_binding_path_is_fixed_bounded_and_no_follow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, credential = _fixed_binding(tmp_path)
    monkeypatch.setattr(weathernext_canary, "FIXED_BINDING_ROOT", root)
    monkeypatch.setattr(
        weathernext_canary,
        "FIXED_PRIVATE_BINDING",
        root / "first-access-private.json",
    )
    monkeypatch.setattr(
        weathernext_canary,
        "FIXED_CREDENTIAL_ROOT",
        root / "credentials",
    )

    observed = weathernext_canary._credential_path(expected_uid=os.getuid())
    assert observed == credential

    credential.unlink()
    credential.symlink_to(root / "first-access-private.json")
    with pytest.raises(
        weathernext_canary.WeatherNextGCSCanaryError,
        match="metadata drifted",
    ):
        weathernext_canary._credential_path(expected_uid=os.getuid())


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
    monkeypatch.setattr(weathernext_canary, "_fixed_credential_provider", lambda: object())
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


def test_canary_source_uses_one_fixed_binding_and_no_database_path() -> None:
    source = Path(weathernext_canary.__file__).read_text(encoding="utf-8")
    assert 'Path("/run/weathernext-binding")' in source
    assert "devstorage.read_only" in source
    assert "load_credentials_from_file" in source
    assert "Database(" not in source
    assert "HOME_LAT" not in source
    assert "HOME_LON" not in source
