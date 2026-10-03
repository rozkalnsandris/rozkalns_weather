from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .weathernext_gcs_transport import read_private_first_access_gcs

FIXED_CREDENTIAL_PATH = Path("/run/secrets/weathernext-google.json")
GCS_READONLY_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"
MAX_CREDENTIAL_BYTES = 64 * 1024


class WeatherNextGCSCanaryError(RuntimeError):
    pass


def parse_init_utc(value: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise WeatherNextGCSCanaryError("init must be RFC3339 UTC with Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise WeatherNextGCSCanaryError("init must be valid RFC3339 UTC") from exc
    parsed = parsed.astimezone(timezone.utc)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise WeatherNextGCSCanaryError("init must be aligned to an exact UTC hour")
    return parsed


def _require_fixed_credential(*, expected_uid: int = 0) -> Path:
    try:
        observed = FIXED_CREDENTIAL_PATH.lstat()
    except OSError as exc:
        raise WeatherNextGCSCanaryError("fixed WeatherNext credential is unavailable") from exc
    if (
        not stat.S_ISREG(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_nlink != 1
        or observed.st_uid != expected_uid
        or stat.S_IMODE(observed.st_mode) != 0o600
        or observed.st_size <= 0
        or observed.st_size > MAX_CREDENTIAL_BYTES
    ):
        raise WeatherNextGCSCanaryError("fixed WeatherNext credential metadata drifted")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(FIXED_CREDENTIAL_PATH, flags)
    except OSError as exc:
        raise WeatherNextGCSCanaryError("fixed WeatherNext credential open failed") from exc
    try:
        opened = os.fstat(fd)
        if (
            (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino)
            or opened.st_size != observed.st_size
        ):
            raise WeatherNextGCSCanaryError("fixed WeatherNext credential changed before read")
    finally:
        os.close(fd)
    return FIXED_CREDENTIAL_PATH


def _fixed_credential_provider() -> Any:
    credential_path = _require_fixed_credential()
    try:
        import google.auth
        from obstore.auth.google import GoogleCredentialProvider

        credentials, _project = google.auth.load_credentials_from_file(
            str(credential_path),
            scopes=[GCS_READONLY_SCOPE],
        )
        return GoogleCredentialProvider(credentials=credentials)
    except Exception as exc:
        raise WeatherNextGCSCanaryError("fixed WeatherNext credential provider failed closed") from exc


def run_fixed_canary(init_time: datetime) -> Mapping[str, object]:
    if os.geteuid() != 0:
        raise WeatherNextGCSCanaryError(
            "WeatherNext GCS canary requires root inside the one-shot container"
        )
    try:
        result = read_private_first_access_gcs(
            init_time=init_time,
            retrieved_at=datetime.now(timezone.utc),
            credential_provider=_fixed_credential_provider(),
        )
    except WeatherNextGCSCanaryError:
        raise
    except Exception as exc:
        raise WeatherNextGCSCanaryError("WeatherNext GCS canary failed closed") from exc

    evidence = dict(result.evidence)
    if (
        evidence.get("state") != "gcs_canary_complete"
        or evidence.get("location_id") != "station_05480"
        or evidence.get("lead_count") != 6
        or evidence.get("materialized_scalar_count") != 288
        or evidence.get("schema_valid") is not True
        or evidence.get("provenance_complete") is not True
        or evidence.get("production_write_performed") is not False
    ):
        raise WeatherNextGCSCanaryError("WeatherNext GCS canary evidence failed closed")
    return evidence
