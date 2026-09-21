from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
import io
from typing import Any
import zipfile

from ..locations import DWD_10416, PUBLIC_BENCHMARK_LOCATION, PUBLIC_BENCHMARK_STATION_ID
from ..models import Observation, parse_time, utc_iso
from .base import BytesFetcher, JsonFetcher, fetch_bytes, fetch_json
from .provider_contracts import enforce_contract, inspect_dwd_observations

BRIGHTSKY_WEATHER_URL = "https://api.brightsky.dev/weather"
LEGACY_WMO_STATION_ID = "10416"

CDC_ROOT = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly"
CDC_PRODUCTS = {
    "temperature_2m": {
        "family": "air_temperature",
        "code": "TU",
        "value_column": "TT_TU",
        "unit": "degC",
        "quality_column": "QN_9",
        "historical_file": "stundenwerte_TU_05480_20030910_20251231_hist.zip",
    },
    "precipitation_1h": {
        "family": "precipitation",
        "code": "RR",
        "value_column": "R1",
        "unit": "mm",
        "quality_column": "QN_8",
        "historical_file": "stundenwerte_RR_05480_20030910_20251231_hist.zip",
    },
    "wind_gust_10m": {
        "family": "extreme_wind",
        "code": "FX",
        "value_column": "FX_911",
        "unit": "m/s",
        "quality_column": "QN_8",
        "historical_file": "stundenwerte_FX_05480_19900705_20251231_hist.zip",
    },
}


def _normalize_station_id(value: object) -> str:
    text = str(value or "").strip()
    return text.zfill(5) if text.isdigit() else text


def _product_url(variable: str, *, historical: bool) -> str:
    spec = CDC_PRODUCTS[variable]
    filename = str(spec["historical_file"]) if historical else f"stundenwerte_{spec['code']}_{PUBLIC_BENCHMARK_STATION_ID}_akt.zip"
    lane = "historical" if historical else "recent"
    return f"{CDC_ROOT}/{spec['family']}/{lane}/{filename}"


def parse_cdc_product_zip(
    payload: bytes,
    *,
    variable: str,
    source_url: str,
    retrieved_at: datetime | None = None,
) -> list[Observation]:
    if variable not in CDC_PRODUCTS:
        raise ValueError(f"unsupported DWD CDC benchmark variable: {variable}")
    retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    spec = CDC_PRODUCTS[variable]
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith(".txt") and "produkt_" in name.lower()]
        if len(candidates) != 1:
            raise ValueError("DWD CDC archive must contain exactly one produkt_*.txt data file")
        raw = archive.read(candidates[0])
    text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    required = {"STATIONS_ID", "MESS_DATUM", str(spec["value_column"])}
    if reader.fieldnames is None:
        raise ValueError("DWD CDC product has no header")
    normalized_fields = {name.strip() for name in reader.fieldnames}
    if not required.issubset(normalized_fields):
        raise ValueError(f"DWD CDC product missing required columns: {sorted(required - normalized_fields)}")

    output: list[Observation] = []
    for raw_row in reader:
        row = {str(key).strip(): (value.strip() if isinstance(value, str) else value) for key, value in raw_row.items() if key is not None}
        station_id = _normalize_station_id(row.get("STATIONS_ID"))
        if station_id != PUBLIC_BENCHMARK_STATION_ID:
            raise ValueError(f"DWD CDC station mismatch: expected {PUBLIC_BENCHMARK_STATION_ID}, got {station_id}")
        timestamp_text = str(row.get("MESS_DATUM") or "").strip()
        try:
            observed_at = datetime.strptime(timestamp_text, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError(f"invalid DWD CDC MESS_DATUM: {timestamp_text}") from exc
        value_text = str(row.get(str(spec["value_column"])) or "").strip()
        try:
            value = float(value_text)
        except ValueError as exc:
            raise ValueError(f"invalid DWD CDC value for {variable}: {value_text}") from exc
        if value == -999.0:
            continue
        quality = row.get(str(spec["quality_column"]))
        output.append(
            Observation(
                source_provider="DWD",
                station_id=PUBLIC_BENCHMARK_STATION_ID,
                location_id=PUBLIC_BENCHMARK_LOCATION.id,
                observed_at_utc=observed_at,
                variable=variable,
                value=value,
                unit=str(spec["unit"]),
                quality_status="observed",
                source_metadata={
                    "source_authority": "DWD",
                    "transport": "DWD CDC Open Data",
                    "dwd_station_id": PUBLIC_BENCHMARK_STATION_ID,
                    "station_name": "Werl",
                    "reference_location_id": PUBLIC_BENCHMARK_LOCATION.id,
                    "station_identity_pinned": True,
                    "product_family": spec["family"],
                    "product_code": spec["code"],
                    "value_column": spec["value_column"],
                    "quality_level": quality,
                    "source_url": source_url,
                    "retrieved_at_utc": utc_iso(retrieved_at),
                    "missing_values_omitted_not_imputed": True,
                },
            )
        )
    return output


class DwdCdcObservationAdapter:
    """Canonical DWD CDC truth adapter for the measured public benchmark."""

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
        # The frozen production window is in the rolling recent archive. Historical
        # archives remain supported for dates through the latest completed version.
        use_historical = start <= date(2025, 12, 31)
        for variable in CDC_PRODUCTS:
            urls = []
            if use_historical:
                urls.append(_product_url(variable, historical=True))
            urls.append(_product_url(variable, historical=False))
            for url in urls:
                for item in parse_cdc_product_zip(
                    self.fetcher(url),
                    variable=variable,
                    source_url=url,
                    retrieved_at=retrieved_at,
                ):
                    if start <= item.observed_at_utc.date() <= end:
                        observations.append(item)
        deduped: dict[tuple[str, str, str], Observation] = {}
        for item in observations:
            key = (item.station_id or "", utc_iso(item.observed_at_utc), item.variable)
            deduped[key] = item
        return [deduped[key] for key in sorted(deduped)]

    def fetch(self, *, hours: int = 48, now: datetime | None = None) -> list[Observation]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        start = now - timedelta(hours=hours)
        return self.fetch_range(start=start.date(), end=now.date(), retrieved_at=now)


# Legacy transport/parser is retained for already-recorded WMO-10416 provenance.
LEGACY_VARIABLES = {
    "temperature": ("temperature_2m", "degC"),
    "dew_point": ("dew_point_2m", "degC"),
    "pressure_msl": ("pressure_msl", "hPa"),
    "relative_humidity": ("relative_humidity_2m", "%"),
    "wind_speed": ("wind_speed_10m", "m/s"),
    "wind_gust_speed": ("wind_gust_10m", "m/s"),
    "precipitation": ("precipitation_1h", "mm"),
    "cloud_cover": ("cloud_cover", "%"),
}


def parse_brightsky_observations(payload: dict[str, Any], *, retrieved_at: datetime | None = None) -> list[Observation]:
    retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    contract_report = enforce_contract(
        inspect_dwd_observations(payload, expected_wmo_station_id=LEGACY_WMO_STATION_ID)
    )
    sources = {source.get("id"): source for source in payload.get("sources", []) if isinstance(source, dict)}
    output: list[Observation] = []
    for row in payload.get("weather", []):
        if not isinstance(row, dict) or not row.get("timestamp"):
            continue
        source = sources.get(row.get("source_id"))
        if not isinstance(source, dict):
            continue
        wmo = str(source.get("wmo_station_id") or "")
        if wmo != LEGACY_WMO_STATION_ID:
            continue
        for source_key, (variable, unit) in LEGACY_VARIABLES.items():
            raw = row.get(source_key)
            if raw is None:
                continue
            output.append(
                Observation(
                    source_provider="DWD",
                    station_id=wmo,
                    location_id=DWD_10416.id,
                    observed_at_utc=parse_time(str(row["timestamp"])),
                    variable=variable,
                    value=float(raw),
                    unit=unit,
                    quality_status="observed",
                    source_metadata={
                        "source_authority": "DWD",
                        "transport": "Bright Sky",
                        "retrieved_at_utc": utc_iso(retrieved_at),
                        "source_id": row.get("source_id"),
                        "station_name": source.get("station_name"),
                        "dwd_station_id": source.get("dwd_station_id"),
                        "wmo_station_id": source.get("wmo_station_id"),
                        "reference_location_id": DWD_10416.id,
                        "station_identity_pinned": True,
                        "missing_values_omitted_not_imputed": True,
                        "provider_contract_drift": contract_report.to_metadata(),
                        "legacy_truth_transport": True,
                    },
                )
            )
    return output


class DwdObservationAdapter:
    provider_id = "dwd_observations_legacy_10416"

    def __init__(self, *, fetcher: JsonFetcher = fetch_json) -> None:
        self.fetcher = fetcher

    def fetch_range(self, *, start: date, end: date, retrieved_at: datetime | None = None) -> list[Observation]:
        if end < start:
            raise ValueError("end date must not be before start date")
        params = {
            "date": start.isoformat(),
            "last_date": end.isoformat(),
            "wmo_station_id": LEGACY_WMO_STATION_ID,
            "tz": "UTC",
            "units": "si",
        }
        return parse_brightsky_observations(self.fetcher(BRIGHTSKY_WEATHER_URL, params), retrieved_at=retrieved_at)


LegacyDwdWmo10416ObservationAdapter = DwdObservationAdapter
