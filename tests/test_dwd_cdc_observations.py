from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from zipfile import ZipFile

import pytest

from rozkalns_weather.providers.dwd_cdc_observations import (
    CDC_STATION_ID,
    PRODUCTS,
    REQUIRED_VARIABLES,
    _historical_urls,
    parse_cdc_archive,
)


def _product(code: str):
    return next(item for item in PRODUCTS if item.archive_code == code)


def _archive(text: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zipped:
        zipped.writestr("produkt_fixture.txt", text)
    return buffer.getvalue()


def test_required_variable_scope_is_complete_and_stable() -> None:
    assert REQUIRED_VARIABLES == (
        "temperature_2m",
        "dew_point_2m",
        "relative_humidity_2m",
        "pressure_msl",
        "wind_speed_10m",
        "wind_gust_10m",
        "precipitation_1h",
        "cloud_cover",
    )
    assert {item.archive_code for item in PRODUCTS} == {"TU", "TD", "P0", "FF", "FX", "RR", "N"}


def test_air_temperature_archive_pins_station_and_preserves_provenance() -> None:
    rows = parse_cdc_archive(
        _archive(
            "STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU\n"
            "5480;2026040200;1;10.5;80.0\n"
            "5480;2026040201;1;-999;-999\n"
        ),
        product=_product("TU"),
        source_url="https://opendata.dwd.de/fixture-TU.zip",
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
        retrieved_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
    )
    assert [(row.variable, row.value, row.unit) for row in rows] == [
        ("temperature_2m", 10.5, "degC"),
        ("relative_humidity_2m", 80.0, "%"),
    ]
    assert all(row.station_id == CDC_STATION_ID for row in rows)
    assert all(row.location_id == "station_05480" for row in rows)
    metadata = rows[0].source_metadata
    assert metadata["source_authority"] == "DWD"
    assert metadata["transport"] == "DWD CDC Open Data"
    assert metadata["dwd_cdc_station_id"] == "05480"
    assert metadata["reference_location_id"] == "station_05480"
    assert metadata["source_url"] == "https://opendata.dwd.de/fixture-TU.zip"
    assert metadata["retrieved_at_utc"] == "2026-09-21T10:00:00Z"
    assert metadata["dwd_quality_fields"] == {"QN_9": "1"}
    assert metadata["missing_values_omitted"] is True


def test_precipitation_and_cloud_semantics_are_not_imputed() -> None:
    precip = parse_cdc_archive(
        _archive("STATIONS_ID;MESS_DATUM;R1\n05480;2026040200;1.25\n"),
        product=_product("RR"),
        source_url="https://opendata.dwd.de/fixture-RR.zip",
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
    )
    assert len(precip) == 1
    assert precip[0].variable == "precipitation_1h"
    assert precip[0].value == 1.25
    assert precip[0].source_metadata["accumulation_window_minutes"] == 60

    cloud = parse_cdc_archive(
        _archive(
            "STATIONS_ID;MESS_DATUM;V_N\n"
            "05480;2026040200;8\n"
            "05480;2026040201;-1\n"
            "05480;2026040202;-999\n"
        ),
        product=_product("N"),
        source_url="https://opendata.dwd.de/fixture-N.zip",
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
    )
    assert len(cloud) == 1
    assert cloud[0].variable == "cloud_cover"
    assert cloud[0].value == 100.0
    assert cloud[0].unit == "%"
    assert cloud[0].source_metadata["native_unit"] == "1/8"
    assert cloud[0].source_metadata["conversion"] == "oktas_to_percent_x12.5"


def test_parser_fails_closed_on_station_column_and_cloud_drift() -> None:
    with pytest.raises(ValueError, match="unexpected DWD CDC station id"):
        parse_cdc_archive(
            _archive("STATIONS_ID;MESS_DATUM;TD\n10416;2026040200;5.0\n"),
            product=_product("TD"),
            source_url="https://opendata.dwd.de/wrong-station.zip",
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
        )

    with pytest.raises(ValueError, match="missing columns"):
        parse_cdc_archive(
            _archive("STATIONS_ID;MESS_DATUM\n05480;2026040200\n"),
            product=_product("FF"),
            source_url="https://opendata.dwd.de/missing-column.zip",
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
        )

    with pytest.raises(ValueError, match="0..8 oktas"):
        parse_cdc_archive(
            _archive("STATIONS_ID;MESS_DATUM;V_N\n05480;2026040200;9\n"),
            product=_product("N"),
            source_url="https://opendata.dwd.de/invalid-cloud.zip",
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
        )


def test_historical_url_discovery_is_exact_station_and_window_bounded() -> None:
    index = """
    <a href="stundenwerte_TU_05480_20240101_20260331_hist.zip">old</a>
    <a href="stundenwerte_TU_05480_20260401_20260915_hist.zip">wanted</a>
    <a href="stundenwerte_TU_10416_20260401_20260915_hist.zip">wrong station</a>
    <a href="stundenwerte_TU_05480_20260916_20261231_hist.zip">future</a>
    """
    urls = _historical_urls(
        index,
        _product("TU"),
        start=date(2026, 4, 2),
        end=date(2026, 9, 10),
    )
    assert urls == [
        "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/air_temperature/historical/stundenwerte_TU_05480_20260401_20260915_hist.zip"
    ]
