from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from .weathernext_gcs_transport import read_private_first_access_gcs

FIXED_BINDING_ROOT = Path("/run/weathernext-binding")
FIXED_PRIVATE_BINDING = FIXED_BINDING_ROOT / "first-access-private.json"
FIXED_CREDENTIAL_ROOT = FIXED_BINDING_ROOT / "credentials"
PRIVATE_BINDING_SCHEMA = "rozkalns-weather.weathernext-private-first-access-binding.v1"
GCS_READONLY_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"
MAX_BINDING_BYTES = 16 * 1024
MAX_CREDENTIAL_BYTES = 64 * 1024
_CREDENTIAL_BASENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


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


def _require_directory(path: Path, *, expected_uid: int = 0) -> None:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise WeatherNextGCSCanaryError("fixed WeatherNext binding directory is unavailable") from exc
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != expected_uid
        or stat.S_IMODE(observed.st_mode) != 0o700
    ):
        raise WeatherNextGCSCanaryError("fixed WeatherNext binding directory metadata drifted")


def _read_regular(
    path: Path,
    *,
    max_bytes: int,
    expected_uid: int = 0,
) -> bytes:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise WeatherNextGCSCanaryError("fixed WeatherNext binding file is unavailable") from exc
    if (
        not stat.S_ISREG(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_nlink != 1
        or observed.st_uid != expected_uid
        or stat.S_IMODE(observed.st_mode) != 0o600
        or observed.st_size <= 0
        or observed.st_size > max_bytes
    ):
        raise WeatherNextGCSCanaryError("fixed WeatherNext binding file metadata drifted")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise WeatherNextGCSCanaryError("fixed WeatherNext binding file open failed") from exc
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino):
            raise WeatherNextGCSCanaryError("fixed WeatherNext binding file changed before read")
        raw = b""
        while len(raw) <= max_bytes:
            block = os.read(fd, min(65536, max_bytes + 1 - len(raw)))
            if not block:
                break
            raw += block
    finally:
        os.close(fd)
    if len(raw) != observed.st_size or len(raw) > max_bytes:
        raise WeatherNextGCSCanaryError("fixed WeatherNext binding file changed during read")
    return raw


def _credential_path(*, expected_uid: int = 0) -> Path:
    _require_directory(FIXED_BINDING_ROOT, expected_uid=expected_uid)
    _require_directory(FIXED_CREDENTIAL_ROOT, expected_uid=expected_uid)
    try:
        value = json.loads(
            _read_regular(
                FIXED_PRIVATE_BINDING,
                max_bytes=MAX_BINDING_BYTES,
                expected_uid=expected_uid,
            ).decode("utf-8", "strict")
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WeatherNextGCSCanaryError("fixed WeatherNext private binding is malformed") from exc
    if type(value) is not dict or set(value) != {"schema", "credential_file"}:
        raise WeatherNextGCSCanaryError("fixed WeatherNext private binding schema drifted")
    credential_file = value.get("credential_file")
    if (
        value.get("schema") != PRIVATE_BINDING_SCHEMA
        or type(credential_file) is not str
        or _CREDENTIAL_BASENAME.fullmatch(credential_file) is None
        or credential_file in {".", ".."}
    ):
        raise WeatherNextGCSCanaryError("fixed WeatherNext private binding is incomplete")
    path = FIXED_CREDENTIAL_ROOT / credential_file
    _read_regular(path, max_bytes=MAX_CREDENTIAL_BYTES, expected_uid=expected_uid)
    return path


def _fixed_credential_provider() -> Any:
    credential_path = _credential_path()
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
        raise WeatherNextGCSCanaryError("WeatherNext GCS canary requires root inside the one-shot container")
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
