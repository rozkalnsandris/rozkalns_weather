from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import io
import math
import re
from typing import Any
from collections.abc import Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET
import zipfile

COMPATIBLE = "COMPATIBLE"
WARN = "WARN"
BLOCKED = "BLOCKED"

OPEN_METEO_UNITS: dict[str, frozenset[str]] = {
    "temperature_2m": frozenset({"°C", "degC"}),
    "dew_point_2m": frozenset({"°C", "degC"}),
    "precipitation": frozenset({"mm"}),
    "pressure_msl": frozenset({"hPa"}),
    "cloud_cover": frozenset({"%"}),
    "wind_speed_10m": frozenset({"m/s"}),
    "wind_gusts_10m": frozenset({"m/s"}),
}
BRIGHTSKY_REQUIRED_SOURCE_FIELDS = frozenset({"id", "wmo_station_id"})
BRIGHTSKY_REQUIRED_WEATHER_FIELDS = frozenset({"timestamp", "source_id"})
BRIGHTSKY_SUPPORTED_WEATHER_FIELDS = frozenset({
    "temperature", "dew_point", "pressure_msl", "relative_humidity",
    "wind_speed", "wind_gust_speed", "precipitation", "cloud_cover",
})
MOSMIX_SUPPORTED_ELEMENTS = frozenset({"TTT", "Td", "FF", "FX1", "PPPP", "N", "RR1c"})
_MEMBER_RE = re.compile(r"^(?P<variable>[A-Za-z0-9_]+)_member(?P<member>\d+)$")


@dataclass(frozen=True, slots=True)
class ContractFinding:
    severity: str
    reason_code: str
    detail: str


@dataclass(frozen=True, slots=True)
class ContractReport:
    provider_contract: str
    status: str
    findings: tuple[ContractFinding, ...]

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(f.reason_code for f in self.findings)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "provider_contract": self.provider_contract,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
        }


class ProviderContractDriftError(ValueError):
    def __init__(self, report: ContractReport) -> None:
        self.report = report
        super().__init__(
            f"{report.provider_contract} contract drift blocked: "
            + ",".join(report.reason_codes)
        )


def _report(name: str, findings: Iterable[ContractFinding]) -> ContractReport:
    items = tuple(findings)
    status = (
        BLOCKED
        if any(item.severity == BLOCKED for item in items)
        else WARN
        if any(item.severity == WARN for item in items)
        else COMPATIBLE
    )
    return ContractReport(name, status, items)


def enforce_contract(report: ContractReport) -> ContractReport:
    if report.status == BLOCKED:
        raise ProviderContractDriftError(report)
    return report


def _finding(severity: str, code: str, detail: str) -> ContractFinding:
    return ContractFinding(severity, code, detail)


def _is_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def inspect_dwd_observations(
    payload: Mapping[str, Any],
    *,
    expected_wmo_station_id: str,
) -> ContractReport:
    findings: list[ContractFinding] = []
    sources = payload.get("sources")
    weather = payload.get("weather")
    if not isinstance(sources, list):
        findings.append(_finding(BLOCKED, "SOURCES_MISSING", "sources must be a list"))
        sources = []
    if not isinstance(weather, list):
        findings.append(_finding(BLOCKED, "WEATHER_MISSING", "weather must be a list"))
        weather = []

    source_by_id: dict[Any, Mapping[str, Any]] = {}
    expected_seen = False
    for source in sources:
        if not isinstance(source, Mapping):
            findings.append(_finding(BLOCKED, "SOURCE_SHAPE_INVALID", "source row must be an object"))
            continue
        missing = sorted(BRIGHTSKY_REQUIRED_SOURCE_FIELDS - set(source))
        if missing:
            findings.append(_finding(BLOCKED, "SOURCE_FIELD_MISSING", ",".join(missing)))
            continue
        source_by_id[source["id"]] = source
        if str(source.get("wmo_station_id") or "") == expected_wmo_station_id:
            expected_seen = True

    if sources and not expected_seen:
        findings.append(
            _finding(
                BLOCKED,
                "STATION_MISMATCH",
                f"expected WMO station {expected_wmo_station_id}",
            )
        )

    supported_seen = False
    for row in weather:
        if not isinstance(row, Mapping):
            findings.append(_finding(BLOCKED, "WEATHER_ROW_INVALID", "weather row must be an object"))
            continue
        missing = sorted(BRIGHTSKY_REQUIRED_WEATHER_FIELDS - set(row))
        if missing:
            findings.append(_finding(BLOCKED, "WEATHER_FIELD_MISSING", ",".join(missing)))
            continue
        if not _is_timestamp(row.get("timestamp")):
            findings.append(_finding(BLOCKED, "TIMESTAMP_INVALID", "weather timestamp is invalid"))
        source = source_by_id.get(row.get("source_id"))
        if source is None:
            findings.append(_finding(BLOCKED, "SOURCE_REFERENCE_UNKNOWN", "weather source_id is unknown"))
        elif str(source.get("wmo_station_id") or "") != expected_wmo_station_id:
            findings.append(_finding(BLOCKED, "STATION_MISMATCH", "weather row references another station"))
        row_fields = set(row) - BRIGHTSKY_REQUIRED_WEATHER_FIELDS
        if row_fields & BRIGHTSKY_SUPPORTED_WEATHER_FIELDS:
            supported_seen = True
        unknown = sorted(row_fields - BRIGHTSKY_SUPPORTED_WEATHER_FIELDS)
        for field in unknown:
            findings.append(_finding(WARN, "FIELD_ADDED", field))

    if weather and not supported_seen:
        findings.append(_finding(BLOCKED, "NO_SUPPORTED_FIELDS", "no supported weather values found"))
    return _report("dwd_observations_brightsky_v1", findings)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def inspect_dwd_mosmix_kmz(
    payload: bytes,
    *,
    expected_station_id: str,
    station_id: str,
) -> ContractReport:
    findings: list[ContractFinding] = []
    if station_id != expected_station_id:
        findings.append(_finding(BLOCKED, "STATION_MISMATCH", f"expected station {expected_station_id}"))
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
            if not names:
                findings.append(_finding(BLOCKED, "KML_MISSING", "KMZ contains no KML"))
                return _report("dwd_mosmix_l_kmz_v1", findings)
            raw = archive.read(names[0])
    except (zipfile.BadZipFile, KeyError, OSError):
        findings.append(_finding(BLOCKED, "ARCHIVE_INVALID", "KMZ is invalid"))
        return _report("dwd_mosmix_l_kmz_v1", findings)

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        findings.append(_finding(BLOCKED, "KML_INVALID", "KML XML is invalid"))
        return _report("dwd_mosmix_l_kmz_v1", findings)

    issue_time: str | None = None
    time_steps: list[str] = []
    forecasts: list[tuple[str, list[str]]] = []
    for element in root.iter():
        name = _local_name(element.tag)
        if name == "IssueTime" and element.text:
            issue_time = element.text.strip()
        elif name == "TimeStep" and element.text:
            time_steps.append(element.text.strip())
        elif name == "Forecast":
            element_name = next(
                (value for key, value in element.attrib.items() if key.rsplit("}", 1)[-1] == "elementName"),
                None,
            )
            value_node = next((child for child in element if _local_name(child.tag) == "value"), None)
            if element_name and value_node is not None and value_node.text:
                forecasts.append((str(element_name), value_node.text.split()))

    if not issue_time or not _is_timestamp(issue_time):
        findings.append(_finding(BLOCKED, "INIT_TIME_INVALID", "IssueTime missing or invalid"))
    if not time_steps:
        findings.append(_finding(BLOCKED, "TIMESTEPS_MISSING", "TimeStep list is empty"))
    elif any(not _is_timestamp(value) for value in time_steps):
        findings.append(_finding(BLOCKED, "TIMESTAMP_INVALID", "TimeStep contains invalid timestamp"))

    supported_seen = False
    for element_name, tokens in forecasts:
        if element_name in MOSMIX_SUPPORTED_ELEMENTS:
            supported_seen = True
            if len(tokens) != len(time_steps):
                findings.append(
                    _finding(
                        BLOCKED,
                        "SERIES_LENGTH_MISMATCH",
                        f"{element_name}:{len(tokens)}!={len(time_steps)}",
                    )
                )
        else:
            findings.append(_finding(WARN, "FIELD_ADDED", element_name))
    if forecasts and not supported_seen:
        findings.append(_finding(BLOCKED, "NO_SUPPORTED_FIELDS", "no supported MOSMIX elements found"))
    return _report("dwd_mosmix_l_kmz_v1", findings)


def _series_contract(
    payload: Mapping[str, Any],
    *,
    requested_variables: Sequence[str],
    contract_name: str,
    allow_members: bool,
) -> ContractReport:
    findings: list[ContractFinding] = []
    hourly = payload.get("hourly")
    units = payload.get("hourly_units")
    if not isinstance(hourly, Mapping):
        findings.append(_finding(BLOCKED, "HOURLY_MISSING", "hourly must be an object"))
        return _report(contract_name, findings)
    if not isinstance(units, Mapping):
        findings.append(_finding(BLOCKED, "UNITS_MISSING", "hourly_units must be an object"))
        units = {}
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        findings.append(_finding(BLOCKED, "TIMESTAMPS_MISSING", "hourly.time must be a non-empty list"))
        times = []
    elif any(not _is_timestamp(str(value) + ("Z" if isinstance(value, str) and "+" not in value and not value.endswith("Z") else "")) for value in times):
        findings.append(_finding(BLOCKED, "TIMESTAMP_INVALID", "hourly.time contains an invalid timestamp"))

    known_columns = {"time"}
    member_sets: dict[str, set[str]] = {}
    for variable in requested_variables:
        accepted_units = OPEN_METEO_UNITS.get(variable)
        columns: list[tuple[str, str]] = []
        if variable in hourly:
            columns.append((variable, "control"))
        if allow_members:
            prefix = variable + "_member"
            for column in hourly:
                if not isinstance(column, str) or not column.startswith(prefix):
                    continue
                match = re.fullmatch(re.escape(prefix) + r"(\d+)", column)
                if match:
                    columns.append((column, "member" + match.group(1)))
                else:
                    findings.append(_finding(BLOCKED, "MEMBER_COLUMN_INVALID", column))
                    known_columns.add(column)
        if not columns:
            findings.append(_finding(BLOCKED, "FIELD_MISSING", variable))
            continue
        member_sets[variable] = {member for _, member in columns}
        for column, _member in columns:
            known_columns.add(column)
            series = hourly.get(column)
            if not isinstance(series, list):
                findings.append(_finding(BLOCKED, "SERIES_SHAPE_INVALID", column))
                continue
            if times and len(series) != len(times):
                findings.append(_finding(BLOCKED, "SERIES_LENGTH_MISMATCH", column))
            unit = units.get(column, units.get(variable))
            if accepted_units is not None and unit not in accepted_units:
                findings.append(_finding(BLOCKED, "UNIT_DRIFT", f"{column}:{unit!r}"))

    if allow_members and member_sets:
        shapes = {tuple(sorted(value)) for value in member_sets.values()}
        if len(shapes) > 1:
            findings.append(_finding(BLOCKED, "MEMBER_SHAPE_MISMATCH", "requested variables expose different members"))

    for column in sorted(set(hourly) - known_columns):
        findings.append(_finding(WARN, "FIELD_ADDED", str(column)))
    return _report(contract_name, findings)


def inspect_open_meteo_single(
    payload: Mapping[str, Any],
    *,
    requested_variables: Sequence[str],
) -> ContractReport:
    return _series_contract(
        payload,
        requested_variables=requested_variables,
        contract_name="open_meteo_single_runs_v1",
        allow_members=False,
    )


def inspect_open_meteo_ensemble(
    payload: Mapping[str, Any],
    *,
    requested_variables: Sequence[str],
) -> ContractReport:
    return _series_contract(
        payload,
        requested_variables=requested_variables,
        contract_name="open_meteo_ensemble_v1",
        allow_members=True,
    )


def inspect_open_meteo_metadata(payload: Mapping[str, Any]) -> ContractReport:
    findings: list[ContractFinding] = []
    parsed: dict[str, float] = {}
    for field in ("last_run_initialisation_time", "last_run_availability_time"):
        value = payload.get(field)
        try:
            number = float(value)
            datetime.fromtimestamp(number, tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            findings.append(_finding(BLOCKED, "RUN_METADATA_INVALID", field))
            continue
        if not math.isfinite(number):
            findings.append(_finding(BLOCKED, "RUN_METADATA_INVALID", field))
            continue
        parsed[field] = number
    if (
        "last_run_initialisation_time" in parsed
        and "last_run_availability_time" in parsed
        and parsed["last_run_initialisation_time"] > parsed["last_run_availability_time"]
    ):
        findings.append(_finding(BLOCKED, "RUN_METADATA_ORDER_INVALID", "initialisation after availability"))

    for field in ("temporal_resolution_seconds", "update_interval_seconds"):
        if payload.get(field) is None:
            continue
        try:
            value = int(payload[field])
        except (TypeError, ValueError):
            findings.append(_finding(BLOCKED, "RUN_METADATA_INVALID", field))
            continue
        if value <= 0:
            findings.append(_finding(BLOCKED, "RUN_METADATA_INVALID", field))
    return _report("open_meteo_model_metadata_v1", findings)
