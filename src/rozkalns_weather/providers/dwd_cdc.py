from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
from typing import Callable
from zipfile import BadZipFile, ZipFile

from ..locations import BENCHMARK_LOCATION, BENCHMARK_TRUTH_STATION_ID
from ..models import Observation, utc_iso
from .base import BytesFetcher, fetch_bytes

CDC_HOURLY_BASE_URL = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly"
CDC_STATION_ID = BENCHMARK_TRUTH_STATION_ID


@dataclass(frozen=True, slots=True)
class CdcField:
    source_field: str
    variable: str
    unit: str
    native_unit: str | None = None
    transform: Callable[[float], float] | None = None


@dataclass(frozen=True, slots=True)
class CdcProduct:
    code: str
    archive: str
    quality_field: str
    fields: tuple[CdcField, ...]

    @property
    def recent_url(self) -> str:
        return f"{CDC_HOURLY_BASE_URL}/{self.archive}/recent/stundenwerte_{self.code}_{CDC_STATION_ID}_akt.zip"


PRODUCTS = (
    CdcProduct(
        "TU",
        "air_temperature",
        "QN_9",
        (
            CdcField("TT_TU", "temperature_2m", "degC"),
            CdcField("RF_TU", "relative_humidity_2m", "%"),
        ),
    ),
    CdcProduct("TD", "dew_point", "QN_8", (CdcField("TD", "dew_point_2m", "degC"),)),
    CdcProduct("P0", "pressure", "QN_8", (CdcField("P", "pressure_msl", "hPa"),)),
    CdcProduct("FF", "wind", "QN_3", (CdcField("F", "wind_speed_10m", "m/s"),)),
    CdcProduct("FX", "extreme_wind", "QN_8", (CdcField("FX_911", "wind_gust_10m", "m/s"),)),
    CdcProduct("RR", "precipitation", "QN_8", (CdcField("R1", "precipitation_1h", "mm"),)),
    CdcProduct(
        "N",
        "cloudiness",
        "QN_8",
        (CdcField("V_N", "cloud_cover", "%", native_unit="okta", transform=lambda value: value * 12.5),),
    ),
)
PRODUCT_BY_CODE = {product.code: product for product in PRODUCTS}


def _normalized_station_id(value: str) -> str:
    stripped = value.strip()
    if not stripped.isdigit():
        raise ValueError("DWD CDC row has a non-numeric STATIONS_ID")
    return stripped.zfill(5)


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y%m%d%H").replace(tzinfo=timezone.utc)


def _parse_number(value: str) -> float | None:
    try:
        parsed = float(value.strip().replace(",", "."))
    except (AttributeError, ValueError):
        return None
    if parsed <= -999.0:
        return None
    return parsed


def _product_member(archive: ZipFile) -> str:
    members = [name for name in archive.namelist() if name.rsplit("/", 1)[-1].lower().startswith("produkt_") and name.lower().endswith(".txt")]
    if len(members) != 1:
        raise ValueError("DWD CDC station ZIP must contain exactly one produkt_*.txt data file")
    return members[0]


def parse_cdc_product_zip(
    payload: bytes,
    *,
    product_code: str,
    start: date,
    end: date,
    retrieved_at: datetime | None = None,
    source_url: str | None = None,
) -> list[Observation]:
    if end < start:
        raise ValueError("end date must not be before start date")
    product = PRODUCT_BY_CODE.get(product_code)
    if product is None:
        raise ValueError(f"unsupported DWD CDC product: {product_code}")
    retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    archive_sha256 = hashlib.sha256(payload).hexdigest()
    try:
        with ZipFile(io.BytesIO(payload)) as archive:
            raw = archive.read(_product_member(archive))
    except BadZipFile as exc:
        raise ValueError("DWD CDC response is not a valid ZIP archive") from exc
    text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if reader.fieldnames is None:
        raise ValueError("DWD CDC product has no CSV header")
    start_at = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    output: list[Observation] = []
    for raw_row in reader:
        row = {str(key).strip(): str(value or "").strip() for key, value in raw_row.items() if key is not None}
        if _normalized_station_id(row.get("STATIONS_ID", "")) != CDC_STATION_ID:
            raise ValueError("DWD CDC station ZIP contains a row for an unexpected station")
        observed_at = _parse_timestamp(row.get("MESS_DATUM", ""))
        if observed_at < start_at or observed_at >= end_at:
            continue
        quality_level = _parse_number(row.get(product.quality_field, ""))
        for field in product.fields:
            native = _parse_number(row.get(field.source_field, ""))
            if native is None:
                continue
            value = field.transform(native) if field.transform is not None else native
            metadata: dict[str, object] = {
                "source_authority": "DWD",
                "transport": "DWD CDC recent station ZIP",
                "cdc_station_id": CDC_STATION_ID,
                "station_name": "Essen-Bredeney",
                "reference_location_id": BENCHMARK_LOCATION.id,
                "station_identity_pinned": True,
                "product_code": product.code,
                "product_archive": product.archive,
                "product_field": field.source_field,
                "source_url": source_url or product.recent_url,
                "source_archive_sha256": archive_sha256,
                "retrieved_at_utc": utc_iso(retrieved_at),
                "quality_level": quality_level,
                "recent_quality_final": False,
                "recent_values_may_change_upstream": True,
                "missing_values_omitted_not_imputed": True,
            }
            if field.native_unit is not None:
                metadata["native_value"] = native
                metadata["native_unit"] = field.native_unit
            output.append(
                Observation(
                    source_provider="DWD",
                    station_id=CDC_STATION_ID,
                    location_id=BENCHMARK_LOCATION.id,
                    observed_at_utc=observed_at,
                    variable=field.variable,
                    value=float(value),
                    unit=field.unit,
                    quality_status="recent_nonfinal_qc",
                    source_metadata=metadata,
                )
            )
    return output


class DwdCdcObservationAdapter:
    provider_id = "dwd_observations"

    def __init__(self, *, fetcher: BytesFetcher = fetch_bytes) -> None:
        self.fetcher = fetcher

    def fetch_range(
        self,
        *,
        start: date,
        end: date,
        retrieved_at: datetime | None = None,
    ) -> list[Observation]:
        if end < start:
            raise ValueError("end date must not be before start date")
        retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        observations: list[Observation] = []
        for product in PRODUCTS:
            payload = self.fetcher(product.recent_url)
            observations.extend(
                parse_cdc_product_zip(
                    payload,
                    product_code=product.code,
                    start=start,
                    end=end,
                    retrieved_at=retrieved_at,
                    source_url=product.recent_url,
                )
            )
        observations.sort(key=lambda item: (item.observed_at_utc, item.variable))
        return observations

    def fetch(self, *, hours: int = 48, now: datetime | None = None) -> list[Observation]:
        if hours < 1 or hours > 24 * 31:
            raise ValueError("hours must be between 1 and 744")
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        start = now - timedelta(hours=hours)
        return [item for item in self.fetch_range(start=start.date(), end=now.date(), retrieved_at=now) if item.observed_at_utc >= start]
