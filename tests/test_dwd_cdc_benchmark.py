from __future__ import annotations

from datetime import date, datetime, timezone
import io
import zipfile

import pytest

from rozkalns_weather.locations import PUBLIC_BENCHMARK_LOCATION, PUBLIC_BENCHMARK_STATION_ID
from rozkalns_weather.providers.dwd_observations import (
    CDC_PRODUCTS,
    DwdCdcObservationAdapter,
    parse_cdc_product_zip,
)


def _zip(product_name: str, content: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(product_name, content.encode("latin-1"))
    return stream.getvalue()


@pytest.mark.parametrize(
    ("variable", "header", "row", "expected"),
    [
        ("temperature_2m", "STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor\r\n", "5480;2026040201;10;7.3;81.0;eor\r\n", 7.3),
        ("precipitation_1h", "STATIONS_ID;MESS_DATUM;QN_8;R1;RS_IND;WRTR;eor\r\n", "05480;2026040201;10;1.7;1;6;eor\r\n", 1.7),
        ("wind_gust_10m", "STATIONS_ID;MESS_DATUM;QN_8;FX_911;eor\r\n", "05480;2026040201;10;12.5;eor\r\n", 12.5),
    ],
)
def test_cdc_parser_pins_station_units_utc_and_provenance(variable, header, row, expected) -> None:
    url = f"https://opendata.dwd.de/example/{variable}.zip"
    items = parse_cdc_product_zip(
        _zip("produkt_fixture.txt", header + row),
        variable=variable,
        source_url=url,
        retrieved_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
    )
    assert len(items) == 1
    item = items[0]
    assert item.station_id == PUBLIC_BENCHMARK_STATION_ID == "05480"
    assert item.location_id == PUBLIC_BENCHMARK_LOCATION.id
    assert item.observed_at_utc == datetime(2026, 4, 2, 1, tzinfo=timezone.utc)
    assert item.value == expected
    assert item.source_provider == "DWD"
    assert item.source_metadata["transport"] == "DWD CDC Open Data"
    assert item.source_metadata["station_identity_pinned"] is True
    assert item.source_metadata["source_url"] == url


def test_cdc_parser_rejects_any_other_station() -> None:
    payload = _zip(
        "produkt_fixture.txt",
        "STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor\r\n"
        "05481;2026040201;10;7.3;81.0;eor\r\n",
    )
    with pytest.raises(ValueError, match="station mismatch"):
        parse_cdc_product_zip(payload, variable="temperature_2m", source_url="fixture")


def test_cdc_missing_values_are_omitted_not_imputed() -> None:
    payload = _zip(
        "produkt_fixture.txt",
        "STATIONS_ID;MESS_DATUM;QN_8;R1;RS_IND;WRTR;eor\r\n"
        "05480;2026040201;10;-999;-999;-999;eor\r\n",
    )
    assert parse_cdc_product_zip(payload, variable="precipitation_1h", source_url="fixture") == []


def test_adapter_uses_all_three_required_recent_products_for_2026() -> None:
    payloads = {
        "TU": _zip("produkt_tu.txt", "STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor\r\n05480;2026040201;10;7.3;81;eor\r\n"),
        "RR": _zip("produkt_rr.txt", "STATIONS_ID;MESS_DATUM;QN_8;R1;RS_IND;WRTR;eor\r\n05480;2026040201;10;0.2;1;6;eor\r\n"),
        "FX": _zip("produkt_fx.txt", "STATIONS_ID;MESS_DATUM;QN_8;FX_911;eor\r\n05480;2026040201;10;8.5;eor\r\n"),
    }
    urls: list[str] = []

    def fetch(url: str) -> bytes:
        urls.append(url)
        code = next(code for code in payloads if f"_{code}_05480_" in url)
        return payloads[code]

    items = DwdCdcObservationAdapter(fetcher=fetch).fetch_range(
        start=date(2026, 4, 2), end=date(2026, 4, 2)
    )
    assert {item.variable for item in items} == set(CDC_PRODUCTS)
    assert len(urls) == 3
    assert all("/recent/" in url and url.endswith("_05480_akt.zip") for url in urls)
