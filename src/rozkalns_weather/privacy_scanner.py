from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlsplit


ARTIFACT_KINDS = frozenset(
    {
        "api_snapshot",
        "rollout_evidence",
        "diagnostics_bundle",
        "benchmark_export",
        "report",
        "reproducibility_receipt",
    }
)

PUBLIC_STATION_IDS = frozenset({"station_05480", "station_10416"})
_PLACEHOLDERS = frozenset(
    {
        "",
        "redacted",
        "<redacted>",
        "placeholder",
        "<placeholder>",
        "example",
        "changeme",
        "${token}",
        "${api_key}",
        "${secret}",
        "${password}",
    }
)

HOME_COORDINATE_KEYS = frozenset(
    {
        "home_lat",
        "home_lon",
        "home_lng",
        "home_latitude",
        "home_longitude",
    }
)
PRIVATE_ADDRESS_KEYS = frozenset(
    {
        "home_address",
        "private_address",
        "street_address",
        "residential_address",
    }
)
RAW_LOG_KEYS = frozenset({"raw_log", "raw_logs", "private_log", "private_logs"})
PRIVATE_PATH_KEYS = frozenset(
    {
        "runtime_path",
        "filesystem_path",
        "private_path",
        "database_path",
        "db_path",
        "sqlite_path",
        "log_path",
    }
)
CREDENTIAL_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "refresh_token",
        "auth_token",
        "authorization",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "credential",
        "credentials",
        "private_key",
        "service_account_key",
        "cookie",
    }
)

_PRIVATE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:/home/[^/\s]+/|/root/|/Users/[^/\s]+/|file:///[^ \t\r\n]+)"
)
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|"
    r"password|passwd|client[_-]?secret|private[_-]?key|credential(?:s)?)\s*[:=]\s*"
    r"([^\s,;]+)"
)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    reason_code: str


@dataclass(frozen=True)
class ScanResult:
    schema: str
    artifact_kind: str
    status: str
    findings: tuple[Finding, ...]

    @property
    def github_safe(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "artifact_kind": self.artifact_kind,
            "status": self.status,
            "github_safe": self.github_safe,
            "findings": [
                {"path": finding.path, "reason_code": finding.reason_code}
                for finding in self.findings
            ],
        }


def _normalize_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in _PLACEHOLDERS or (
        lowered.startswith("${") and lowered.endswith("}")
    )


def _reason_for_key(key: str) -> str | None:
    if key in HOME_COORDINATE_KEYS:
        return "PRIVATE_HOME_COORDINATE_FIELD"
    if key in PRIVATE_ADDRESS_KEYS:
        return "PRIVATE_ADDRESS_FIELD"
    if key in RAW_LOG_KEYS:
        return "RAW_PRIVATE_LOG_FIELD"
    if key in PRIVATE_PATH_KEYS:
        return "PRIVATE_RUNTIME_PATH_FIELD"
    if key in CREDENTIAL_KEYS:
        return "CREDENTIAL_OR_SECRET_FIELD"
    return None


def _station_identity(value: Mapping[str, Any]) -> str | None:
    for key in ("location_id", "station_id", "benchmark_location_id"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            return candidate
    return None


def _coordinate_keys(value: Mapping[str, Any]) -> tuple[str, str] | None:
    normalized = {_normalize_key(key): key for key in value}
    latitude = next(
        (normalized[key] for key in ("lat", "latitude") if key in normalized), None
    )
    longitude = next(
        (
            normalized[key]
            for key in ("lon", "lng", "longitude")
            if key in normalized
        ),
        None,
    )
    if latitude is None or longitude is None:
        return None
    if not isinstance(value[latitude], (int, float)) or isinstance(value[latitude], bool):
        return None
    if not isinstance(value[longitude], (int, float)) or isinstance(value[longitude], bool):
        return None
    return str(latitude), str(longitude)


def _scan_text(text: str, path: str) -> Iterable[Finding]:
    if _PRIVATE_PATH_RE.search(text):
        yield Finding(path, "PRIVATE_RUNTIME_PATH_TEXT")

    for match in _ASSIGNMENT_RE.finditer(text):
        if not _is_placeholder(match.group(2)):
            yield Finding(path, "CREDENTIAL_OR_SECRET_TEXT")
            break

    for raw_url in _URL_RE.findall(text):
        try:
            parsed = urlsplit(raw_url)
        except ValueError:
            continue
        if parsed.username is not None or parsed.password is not None:
            yield Finding(path, "URL_EMBEDDED_CREDENTIAL")
            continue
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            normalized = _normalize_key(key)
            if normalized in CREDENTIAL_KEYS and not _is_placeholder(value):
                yield Finding(path, "URL_QUERY_CREDENTIAL")
                break


def _walk(
    value: Any, path: str, inherited_station_id: str | None = None
) -> Iterable[Finding]:
    if isinstance(value, Mapping):
        station_id = _station_identity(value) or inherited_station_id
        coordinate_keys = _coordinate_keys(value)
        if coordinate_keys and station_id not in PUBLIC_STATION_IDS:
            yield Finding(path, "PRIVATE_OR_UNSCOPED_COORDINATE_PAIR")

        for raw_key in sorted(value, key=lambda item: str(item)):
            child = value[raw_key]
            key = _normalize_key(raw_key)
            child_path = f"{path}.{raw_key}"
            reason = _reason_for_key(key)
            if reason is not None:
                if reason == "CREDENTIAL_OR_SECRET_FIELD" and isinstance(child, str):
                    if _is_placeholder(child):
                        pass
                    else:
                        yield Finding(child_path, reason)
                else:
                    yield Finding(child_path, reason)

            # Do not echo values into findings; text scanning reports only the path/reason.
            if isinstance(child, str):
                yield from _scan_text(child, child_path)
            elif isinstance(child, (Mapping, list, tuple)):
                yield from _walk(child, child_path, station_id)
        return

    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            if isinstance(child, str):
                yield from _scan_text(child, child_path)
            elif isinstance(child, (Mapping, list, tuple)):
                yield from _walk(child, child_path, inherited_station_id)
        return

    if isinstance(value, str):
        yield from _scan_text(value, path)


def scan_github_safe_artifact(artifact_kind: str, payload: Any) -> ScanResult:
    """Return deterministic, sanitized privacy evidence for a GitHub-bound artifact.

    The result never includes source values. A non-PASS result must block treating the
    payload as GitHub-safe; this helper does not retrieve secrets or mutate artifacts.
    """

    if artifact_kind not in ARTIFACT_KINDS:
        findings = (Finding("$", "UNSUPPORTED_ARTIFACT_KIND"),)
    else:
        findings = tuple(sorted(set(_walk(payload, "$"))))

    return ScanResult(
        schema="rozkalns.weather.privacy-scan.v1",
        artifact_kind=artifact_kind,
        status="PASS" if not findings else "BLOCKED",
        findings=findings,
    )


def require_github_safe_artifact(artifact_kind: str, payload: Any) -> dict[str, Any]:
    """Return sanitized evidence or raise without embedding sensitive payload values."""

    result = scan_github_safe_artifact(artifact_kind, payload)
    if not result.github_safe:
        codes = ",".join(sorted({finding.reason_code for finding in result.findings}))
        raise ValueError(f"artifact is not GitHub-safe: {codes}")
    return result.to_dict()
