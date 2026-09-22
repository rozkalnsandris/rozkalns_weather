from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile

import pytest

from rozkalns_weather.providers.dwd_current_observations import (
    CURRENT_PRODUCTS,
    CURRENT_SOURCE_PROVIDER,
    CURRENT_VARIABLES,
    UNAVAILABLE_CURRENT_VARIABLES,
    DwdCurrentObservationAdapter,
    parse_current_archive,
)


def _archive(text: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zipped:
        zipped.writestr("produkt_fixture.txt", text)
    return buffer.getvalue()


def _product(family: str):
    return next(item for item in CURRENT_PRODUCTS if item.family == family)


def test_air_temperature_now_archive_pins_05480_and_preserves_provenance() -> None:
    rows = parse_current_archive(
        _archive(
            "STATIONS_ID;MESS_DATUM;QN;TT_10;RF_10;TD_10\n"
            "5480;202609221210;1;18.5;71.0;13.1\n"
            "5480;202609221220;1;-999;-999;-999\n"
        ),
        product=_product("air_temperature"),
        source_url="https://opendata.dwd.de/fixture-TU-now.zip",
        retrieved_at=datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc),
    )

    assert [(row.variable, row.value, row.unit) for row in rows] == [
        ("temperature_2m", 18.5, "degC"),
        ("relative_humidity_2m", 71.0, "%"),
        ("dew_point_2m", 13.1, "degC"),
    ]
    assert all(row.source_provider == CURRENT_SOURCE_PROVIDER for row in rows)
    assert all(row.station_id == "05480" for row in rows)
    assert all(row.location_id == "station_05480" for row in rows)
    assert all(row.observed_at_utc == datetime(2026, 9, 22, 12, 10, tzinfo=timezone.utc) for row in rows)

    metadata = rows[0].source_metadata
    assert metadata["source_authority"] == "DWD"
    assert metadata["transport"] == "DWD CDC 10-minute now"
    assert metadata["dwd_station_id"] == "05480"
    assert metadata["reference_location_id"] == "station_05480"
    assert metadata["source_observed_at_utc"] == "2026-09-22T12:10:00Z"
    assert metadata["retrieved_at_utc"] == "2026-09-22T12:30:00Z"
    assert metadata["dwd_quality_fields"] == {"QN": "1"}
    assert metadata["quality_control"] == "preliminary_not_complete"
    assert metadata["missing_values_omitted"] is True


def test_current_archive_rejects_wrong_station_and_missing_schema() -> None:
    with pytest.raises(ValueError, match="unexpected DWD 10-minute station id"):
        parse_current_archive(
            _archive("STATIONS_ID;MESS_DATUM;FF_10\n10416;202609221210;2.0\n"),
            product=_product("wind"),
            source_url="https://opendata.dwd.de/wrong-station.zip",
        )

    with pytest.raises(ValueError, match="missing columns"):
        parse_current_archive(
            _archive("STATIONS_ID;MESS_DATUM\n05480;202609221210\n"),
            product=_product("extreme_wind"),
            source_url="https://opendata.dwd.de/missing-column.zip",
        )


def test_current_adapter_uses_temperature_anchor_and_never_mixes_ages() -> None:
    archives = {
        "air_temperature": _archive(
            "STATIONS_ID;MESS_DATUM;QN;TT_10;RF_10;TD_10\n"
            "05480;202609221200;1;17.0;72;12.0\n"
            "05480;202609221210;1;18.0;70;12.5\n"
        ),
        # Deliberately behind the temperature anchor: wind must be omitted rather
        # than carried forward as a mixed-age current value.
        "wind": _archive(
            "STATIONS_ID;MESS_DATUM;QN;FF_10\n"
            "05480;202609221200;1;3.0\n"
        ),
        "extreme_wind": _archive(
            "STATIONS_ID;MESS_DATUM;QN;FX_10\n"
            "05480;202609221210;1;6.5\n"
        ),
    }

    def fetcher(url: str) -> bytes:
        family = next(item.family for item in CURRENT_PRODUCTS if f"/{item.family}/" in url)
        assert url.endswith("_05480_now.zip")
        return archives[family]

    rows = DwdCurrentObservationAdapter(fetcher=fetcher).fetch(
        now=datetime(2026, 9, 22, 12, 20, tzinfo=timezone.utc)
    )

    assert {row.variable for row in rows} == {
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "wind_gust_10m",
    }
    assert {row.observed_at_utc for row in rows} == {
        datetime(2026, 9, 22, 12, 10, tzinfo=timezone.utc)
    }
    assert "wind_speed_10m" not in {row.variable for row in rows}


def test_current_contract_does_not_relabel_incompatible_10_minute_fields() -> None:
    assert CURRENT_VARIABLES == (
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "wind_speed_10m",
        "wind_gust_10m",
    )
    assert UNAVAILABLE_CURRENT_VARIABLES == (
        "pressure_msl",
        "precipitation_1h",
        "cloud_cover",
    )
