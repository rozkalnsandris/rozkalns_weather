from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import csv
from io import BytesIO, StringIO
import re
from typing import Callable, Iterable
from zipfile import ZipFile

from ..locations import DWD_CDC_05480
from ..models import Observation
from .base import BytesFetcher, fetch_bytes

CDC_HOURLY_ROOT = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly"
CDC_STATION_ID = "05480"
CDC_STATION_NAME = "Werl"


@dataclass(frozen=True, slots=True)
class CdcValue:
    column: str
    variable: str
    unit: str
    transform: Callable[[float], float] | None = None
    accumulation_window_minutes: int | None = None


@dataclass(frozen=True, slots=True)
class CdcProduct:
    family: str
    archive_code: str
    values: tuple[CdcValue, ...]


PRODUCTS = (
    CdcProduct(
        "air_temperature",
        "TU",
        (
            CdcValue("TT_TU", "temperature_2m", "degC"),
            CdcValue("RF_TU", "relative_humidity_2m", "%"),
        ),
    ),
    CdcProduct("dew_point", "TD", (CdcValue("TD", "dew_point_2m", "degC"),)),
    # DWD's product family/archive code is P0, but the CSV column P is the
    # pressure reduced to mean sea level. P0 is station-height pressure.
    CdcProduct("pressure", "P0", (CdcValue("P", "pressure_msl", "hPa"),)),
    CdcProduct("wind", "FF", (CdcValue("F", "wind_speed_10m", "m/s"),)),
    CdcProduct("extreme_wind", "FX", (CdcValue("FX_911", "wind_gust_10m", "m/s"),)),
    CdcProduct(
        "precipitation",
        "RR",
        (CdcValue("R1", "precipitation_1h", "mm", accumulation_window_minutes=60),),
    ),
    CdcProduct(
        "cloudiness",
        "N",
        (CdcValue("V_N", "cloud_cover", "%", transform=lambda oktas: oktas * 12.5),),
    ),
)

REQUIRED_VARIABLES = (
    "temperature_2m",
    "dew_point_2m",
    "relative_humidity_2m",
    "pressure_msl",
    "wind_speed_10m",
    "wind_gust_10m",
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
    # DWD CDC missing sentinel. It must never become a physical observation.
    if parsed <= -999.0:
        return None
    return parsed


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("DWD CDC product text is not decodable")


def _product_text(archive: bytes) -> str:
    with ZipFile(BytesIO(archive)) as zipped:
        names = [name for name in zipped.namelist() if name.rsplit("/", 1)[-1].lower().startswith("produkt_") and name.lower().endswith(".txt")]
        if len(names) != 1:
            raise ValueError("DWD CDC archive must contain exactly one Produkt_*.txt payload")
        return _decode(zipped.read(names[0]))


def parse_cdc_archive(
    archive: bytes,
    *,
    product: CdcProduct,
    source_url: str,
    start: date,
    end: date,
    retrieved_at: datetime | None = None,
) -> list[Observation]:
    if end < start:
        raise ValueError("end must not be before start")
    retrieved = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reader = csv.DictReader(StringIO(_product_text(archive)), delimiter=";")
    if not reader.fieldnames:
        raise ValueError("DWD CDC product has no header")
    normalized_fields = {field.strip(): field for field in reader.fieldnames if field is not None}
    required = {"STATIONS_ID", "MESS_DATUM", *(value.column for value in product.values)}
    missing = sorted(required - set(normalized_fields))
    if missing:
        raise ValueError(f"DWD CDC {product.archive_code} missing columns: {','.join(missing)}")

    output: list[Observation] = []
    for raw in reader:
        row = {str(key).strip(): value for key, value in raw.items() if key is not None}
        station_id = _normalized_station_id(row.get("STATIONS_ID"))
        if station_id != CDC_STATION_ID:
            raise ValueError(f"unexpected DWD CDC station id {station_id!r}; expected {CDC_STATION_ID}")
        try:
            observed_at = datetime.strptime(str(row.get("MESS_DATUM") or "").strip(), "%Y%m%d%H").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("DWD CDC MESS_DATUM must be YYYYMMDDHH UTC") from exc
        if observed_at.date() < start or observed_at.date() > end:
            continue

        quality_columns = sorted(key for key in row if key.startswith("QN"))
        quality = {key: str(row.get(key) or "").strip() for key in quality_columns if str(row.get(key) or "").strip()}
        for definition in product.values:
            value = _float_or_none(row.get(definition.column))
            if value is None:
                continue
            if definition.variable == "cloud_cover":
                # V_N is total cloud cover in eighths. DWD can use negative
                # special states (for example sky obscured); those are not a
                # numeric cloud-cover percentage and are omitted, not imputed.
                if value < 0:
                    continue
                if value > 8:
                    raise ValueError("DWD CDC V_N cloud cover must be within 0..8 oktas")
            normalized = definition.transform(value) if definition.transform else value
            metadata: dict[str, object] = {
                "source_authority": "DWD",
                "transport": "DWD CDC Open Data",
                "dwd_cdc_station_id": CDC_STATION_ID,
                "dwd_station_id": CDC_STATION_ID,
                "station_name": CDC_STATION_NAME,
                "reference_location_id": DWD_CDC_05480.id,
                "station_identity_pinned": True,
                "cdc_product_family": product.family,
                "cdc_archive_code": product.archive_code,
                "cdc_value_column": definition.column,
                "source_url": source_url,
                "retrieved_at_utc": retrieved.isoformat().replace("+00:00", "Z"),
                "missing_values_omitted": True,
            }
            if quality:
                metadata["dwd_quality_fields"] = quality
            if definition.variable == "cloud_cover":
                metadata["native_unit"] = "1/8"
                metadata["conversion"] = "oktas_to_percent_x12.5"
            if definition.accumulation_window_minutes is not None:
                metadata["accumulation_window_minutes"] = definition.accumulation_window_minutes
            output.append(
                Observation(
                    source_provider="DWD",
                    station_id=CDC_STATION_ID,
                    location_id=DWD_CDC_05480.id,
                    observed_at_utc=observed_at,
                    variable=definition.variable,
                    value=normalized,
                    unit=definition.unit,
                    quality_status="observed",
                    source_metadata=metadata,
                )
            )
    return output


def _historical_index_url(product: CdcProduct) -> str:
    return f"{CDC_HOURLY_ROOT}/{product.family}/historical/"


def _recent_url(product: CdcProduct) -> str:
    return f"{CDC_HOURLY_ROOT}/{product.family}/recent/stundenwerte_{product.archive_code}_{CDC_STATION_ID}_akt.zip"


def _historical_urls(index_html: str, product: CdcProduct, *, start: date, end: date) -> list[str]:
    pattern = re.compile(
        rf'href=["\'](stundenwerte_{re.escape(product.archive_code)}_{CDC_STATION_ID}_(\d{{8}})_(\d{{8}})_hist\.zip)["\']',
        re.IGNORECASE,
    )
    urls: list[str] = []
    for filename, start_text, end_text in pattern.findall(index_html):
        archive_start = date.fromisoformat(f"{start_text[:4]}-{start_text[4:6]}-{start_text[6:8]}")
        archive_end = date.fromisoformat(f"{end_text[:4]}-{end_text[4:6]}-{end_text[6:8]}")
        if archive_end < start or archive_start > end:
            continue
        urls.append(_historical_index_url(product) + filename)
    return sorted(set(urls))


class DwdCdcObservationAdapter:
    """Exact-station DWD CDC historical/recent truth transport for Werl 05480."""

    station_id = CDC_STATION_ID
    location_id = DWD_CDC_05480.id

    def __init__(self, fetcher: BytesFetcher = fetch_bytes) -> None:
        self.fetcher = fetcher

    def fetch_range(
        self,
        *,
        start: date,
        end: date,
        retrieved_at: datetime | None = None,
    ) -> list[Observation]:
        if end < start:
            raise ValueError("end must not be before start")
        retrieved = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        observations: dict[tuple[datetime, str], Observation] = {}
        for product in PRODUCTS:
            index_url = _historical_index_url(product)
            index_html = _decode(self.fetcher(index_url))
            urls = _historical_urls(index_html, product, start=start, end=end)
            urls.append(_recent_url(product))
            for url in urls:
                rows = parse_cdc_archive(
                    self.fetcher(url),
                    product=product,
                    source_url=url,
                    start=start,
                    end=end,
                    retrieved_at=retrieved,
                )
                for row in rows:
                    key = (row.observed_at_utc, row.variable)
                    previous = observations.get(key)
                    if previous is not None and (previous.value != row.value or previous.unit != row.unit):
                        raise ValueError(
                            f"conflicting DWD CDC observation for {CDC_STATION_ID} {row.variable} {row.observed_at_utc.isoformat()}"
                        )
                    observations[key] = row
        return [observations[key] for key in sorted(observations, key=lambda item: (item[0], item[1]))]

    def fetch(self, *, now: datetime | None = None, hours: int = 72) -> list[Observation]:
        if hours < 1 or hours > 24 * 31:
            raise ValueError("hours must be between 1 and 744")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        start = (current - timedelta(hours=hours)).date()
        return self.fetch_range(start=start, end=current.date(), retrieved_at=current)
