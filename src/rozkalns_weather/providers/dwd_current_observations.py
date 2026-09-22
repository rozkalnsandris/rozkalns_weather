from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
from io import BytesIO, StringIO
from typing import Callable
from zipfile import ZipFile

from ..locations import DWD_CDC_05480
from ..models import Observation, utc_iso
from .base import BytesFetcher, fetch_bytes

DWD_10MIN_ROOT = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes"
CURRENT_STATION_ID = "05480"
CURRENT_STATION_NAME = "Werl"
CURRENT_SOURCE_PROVIDER = "DWD_CURRENT"
CURRENT_MODEL_NAME = "DWD CDC 10-minute Current"
CURRENT_TRANSPORT = "DWD CDC 10-minute now"


@dataclass(frozen=True, slots=True)
class CurrentValue:
    column: str
    variable: str
    unit: str


@dataclass(frozen=True, slots=True)
class CurrentProduct:
    family: str
    archive_stem: str
    values: tuple[CurrentValue, ...]
    required_for_anchor: bool = False


CURRENT_PRODUCTS = (
    CurrentProduct(
        "air_temperature",
        "TU",
        (
            CurrentValue("TT_10", "temperature_2m", "degC"),
            CurrentValue("RF_10", "relative_humidity_2m", "%"),
            CurrentValue("TD_10", "dew_point_2m", "degC"),
        ),
        required_for_anchor=True,
    ),
    CurrentProduct(
        "wind",
        "wind",
        (CurrentValue("FF_10", "wind_speed_10m", "m/s"),),
    ),
    CurrentProduct(
        "extreme_wind",
        "extrema_wind",
        (CurrentValue("FX_10", "wind_gust_10m", "m/s"),),
    ),
)

CURRENT_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "wind_speed_10m",
    "wind_gust_10m",
)

# Deliberately absent from the current-now contract. PP_10 is station-height
# pressure rather than pressure_msl, 10-minute precipitation is not a 1-hour
# accumulation, and the DWD 10-minute climate family has no cloud-cover product.
UNAVAILABLE_CURRENT_VARIABLES = (
    "pressure_msl",
    "precipitation_1h",
    "cloud_cover",
)


def _normalized_station_id(value: object) -> str:
    text = str(value or "").strip()
    return text.zfill(5) if text.isdigit() else text


def _float_or_none(value: object) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if parsed <= -999.0:
        return None
    return parsed


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("DWD 10-minute product text is not decodable")


def _product_text(archive: bytes) -> str:
    with ZipFile(BytesIO(archive)) as zipped:
        names = [
            name
            for name in zipped.namelist()
            if name.rsplit("/", 1)[-1].lower().startswith("produkt_") and name.lower().endswith(".txt")
        ]
        if len(names) != 1:
            raise ValueError("DWD 10-minute archive must contain exactly one Produkt_*.txt payload")
        return _decode(zipped.read(names[0]))


def _parse_timestamp(value: object) -> datetime:
    text = str(value or "").strip()
    formats = {12: "%Y%m%d%H%M", 10: "%Y%m%d%H"}
    fmt = formats.get(len(text))
    if fmt is None:
        raise ValueError("DWD 10-minute MESS_DATUM must be YYYYMMDDHHMM UTC")
    try:
        return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("DWD 10-minute MESS_DATUM is invalid UTC time") from exc


def _now_url(product: CurrentProduct) -> str:
    return (
        f"{DWD_10MIN_ROOT}/{product.family}/now/"
        f"10minutenwerte_{product.archive_stem}_{CURRENT_STATION_ID}_now.zip"
    )


def parse_current_archive(
    archive: bytes,
    *,
    product: CurrentProduct,
    source_url: str,
    retrieved_at: datetime | None = None,
) -> list[Observation]:
    retrieved = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reader = csv.DictReader(StringIO(_product_text(archive)), delimiter=";")
    if not reader.fieldnames:
        raise ValueError("DWD 10-minute product has no header")
    fields = {field.strip() for field in reader.fieldnames if field is not None}
    required = {"STATIONS_ID", "MESS_DATUM", *(value.column for value in product.values)}
    missing = sorted(required - fields)
    if missing:
        raise ValueError(f"DWD 10-minute {product.family} missing columns: {','.join(missing)}")

    output: list[Observation] = []
    for raw in reader:
        row = {str(key).strip(): value for key, value in raw.items() if key is not None}
        station_id = _normalized_station_id(row.get("STATIONS_ID"))
        if station_id != CURRENT_STATION_ID:
            raise ValueError(
                f"unexpected DWD 10-minute station id {station_id!r}; expected {CURRENT_STATION_ID}"
            )
        observed_at = _parse_timestamp(row.get("MESS_DATUM"))
        quality = {
            key: str(row.get(key) or "").strip()
            for key in sorted(row)
            if key == "QN" or key.startswith("QN_")
            if str(row.get(key) or "").strip()
        }
        for definition in product.values:
            value = _float_or_none(row.get(definition.column))
            if value is None:
                continue
            metadata: dict[str, object] = {
                "source_authority": "DWD",
                "transport": CURRENT_TRANSPORT,
                "dwd_station_id": CURRENT_STATION_ID,
                "dwd_cdc_station_id": CURRENT_STATION_ID,
                "station_name": CURRENT_STATION_NAME,
                "reference_location_id": DWD_CDC_05480.id,
                "station_identity_pinned": True,
                "cdc_product_family": product.family,
                "cdc_value_column": definition.column,
                "source_url": source_url,
                "source_observed_at_utc": utc_iso(observed_at),
                "retrieved_at_utc": utc_iso(retrieved),
                "current_feed": True,
                "quality_control": "preliminary_not_complete",
                "missing_values_omitted": True,
            }
            if quality:
                metadata["dwd_quality_fields"] = quality
            output.append(
                Observation(
                    source_provider=CURRENT_SOURCE_PROVIDER,
                    station_id=CURRENT_STATION_ID,
                    location_id=DWD_CDC_05480.id,
                    observed_at_utc=observed_at,
                    variable=definition.variable,
                    value=value,
                    unit=definition.unit,
                    quality_status="observed_preliminary",
                    source_metadata=metadata,
                )
            )
    return output


class DwdCurrentObservationAdapter:
    """Exact-station 05480 DWD 10-minute `now` feed for the Overview/current lane."""

    station_id = CURRENT_STATION_ID
    location_id = DWD_CDC_05480.id
    source_provider = CURRENT_SOURCE_PROVIDER

    def __init__(self, fetcher: BytesFetcher = fetch_bytes) -> None:
        self.fetcher = fetcher

    def fetch(self, *, now: datetime | None = None) -> list[Observation]:
        retrieved = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        by_family: dict[str, list[Observation]] = {}
        for product in CURRENT_PRODUCTS:
            url = _now_url(product)
            by_family[product.family] = parse_current_archive(
                self.fetcher(url),
                product=product,
                source_url=url,
                retrieved_at=retrieved,
            )

        anchor_rows = by_family["air_temperature"]
        anchor_times = [
            row.observed_at_utc
            for row in anchor_rows
            if row.variable == "temperature_2m"
        ]
        if not anchor_times:
            return []
        anchor = max(anchor_times)

        # One Overview/current payload represents one observation time. Optional
        # product families may lag the air-temperature anchor; those fields are
        # omitted rather than mixing ages or borrowing hourly verification truth.
        selected = [
            row
            for rows in by_family.values()
            for row in rows
            if row.observed_at_utc == anchor
        ]
        selected.sort(key=lambda row: row.variable)
        return selected
