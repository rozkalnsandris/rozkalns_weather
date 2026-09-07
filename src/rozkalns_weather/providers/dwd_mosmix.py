from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET
import zipfile

from ..models import ForecastRun, ForecastValue, parse_time
from .base import BytesFetcher, fetch_bytes

MOSMIX_STATION_ID = "10416"
MOSMIX_URL = (
    "https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/"
    "single_stations/10416/kml/MOSMIX_L_LATEST_10416.kmz"
)

# MOSMIX element names deliberately limited to semantics we can normalize safely.
ELEMENTS = {
    "TTT": ("temperature_2m", "K", "degC", None),
    "Td": ("dew_point_2m", "K", "degC", None),
    "FF": ("wind_speed_10m", "m/s", "m/s", None),
    "FX1": ("wind_gust_10m", "m/s", "m/s", None),
    "PPPP": ("pressure_msl", "Pa", "hPa", None),
    "N": ("cloud_cover", "%", "%", None),
    "RR1c": ("precipitation_1h", "kg/m2", "mm", 60),
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _convert(value: float, native_unit: str, unit: str) -> float:
    if native_unit == "K" and unit == "degC":
        return value - 273.15
    if native_unit == "Pa" and unit == "hPa":
        return value / 100.0
    return value


def parse_mosmix_kmz(payload: bytes, *, retrieved_at: datetime) -> ForecastRun:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        kml_names = [name for name in archive.namelist() if PurePosixPath(name).suffix.lower() == ".kml"]
        if not kml_names:
            raise ValueError("MOSMIX KMZ does not contain a KML file")
        root = ET.fromstring(archive.read(kml_names[0]))

    issue_time_text: str | None = None
    time_steps: list[datetime] = []
    for element in root.iter():
        name = _local_name(element.tag)
        if name == "IssueTime" and element.text:
            issue_time_text = element.text.strip()
        elif name == "TimeStep" and element.text:
            time_steps.append(parse_time(element.text))

    if not issue_time_text:
        raise ValueError("MOSMIX KML has no IssueTime")
    if not time_steps:
        raise ValueError("MOSMIX KML has no forecast time steps")
    init_time = parse_time(issue_time_text)

    values: list[ForecastValue] = []
    for forecast in root.iter():
        if _local_name(forecast.tag) != "Forecast":
            continue
        element_name = forecast.attrib.get("{https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd}elementName") or forecast.attrib.get("elementName")
        if element_name not in ELEMENTS:
            continue
        value_node = next((child for child in forecast if _local_name(child.tag) == "value"), None)
        if value_node is None or not value_node.text:
            continue
        variable, native_unit, unit, accumulation = ELEMENTS[element_name]
        tokens = value_node.text.split()
        for valid_time, token in zip(time_steps, tokens, strict=False):
            if token in {"-", "NaN", "nan", ""}:
                continue
            try:
                native_value = float(token)
            except ValueError:
                continue
            normalized = _convert(native_value, native_unit, unit)
            lead_hours = max(0.0, (valid_time - init_time).total_seconds() / 3600.0)
            values.append(
                ForecastValue(
                    valid_time_utc=valid_time,
                    lead_hours=lead_hours,
                    variable=variable,
                    statistic="deterministic",
                    value=normalized,
                    unit=unit,
                    native_value=native_value,
                    native_unit=native_unit,
                    accumulation_window_minutes=accumulation,
                )
            )

    if not values:
        raise ValueError("MOSMIX KML contained no supported forecast values")

    return ForecastRun(
        provider="dwd_mosmix_l",
        model_provider="DWD",
        model_name="MOSMIX-L",
        model_version=None,
        init_time_utc=init_time,
        retrieved_at_utc=retrieved_at,
        source_surface="DWD Open Data MOSMIX_L KMZ",
        transport_provider="DWD Open Data",
        raw_payload_hash=hashlib.sha256(payload).hexdigest(),
        values=tuple(values),
        source_metadata={"station_id": MOSMIX_STATION_ID, "url": MOSMIX_URL},
    )


class DwdMosmixAdapter:
    provider_id = "dwd_mosmix_l"

    def __init__(self, *, fetcher: BytesFetcher = fetch_bytes) -> None:
        self.fetcher = fetcher

    def fetch(self, *, retrieved_at: datetime | None = None) -> ForecastRun:
        retrieved_at = retrieved_at or datetime.now(timezone.utc)
        return parse_mosmix_kmz(self.fetcher(MOSMIX_URL), retrieved_at=retrieved_at)
