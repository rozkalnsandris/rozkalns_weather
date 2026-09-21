from __future__ import annotations

from datetime import date, datetime, timezone
import io
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from rozkalns_weather.locations import BENCHMARK_LOCATION, BENCHMARK_TRUTH_STATION_ID
from rozkalns_weather.providers.dwd_cdc import DwdCdcObservationAdapter, PRODUCTS, parse_cdc_product_zip


def _zip(product: str, header: str, values: str) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(f"produkt_{product.lower()}_stunde_20260402_20260402_01303.txt", header + "\n" + values + "\n")
        archive.writestr("Metadaten_Stationsname_01303.txt", "01303;Essen-Bredeney\n")
    return buffer.getvalue()


def _one(product: str, header: str, values: str):
    return parse_cdc_product_zip(
        _zip(product, header, values),
        product_code=product,
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
        retrieved_at=datetime(2026, 9, 21, 8, tzinfo=timezone.utc),
    )


def test_benchmark_station_is_public_pinned_cdc_identity() -> None:
    assert BENCHMARK_TRUTH_STATION_ID == "01303"
    assert BENCHMARK_LOCATION.id == "station_dwd_cdc_01303"
    assert BENCHMARK_LOCATION.label == "DWD CDC Essen-Bredeney 01303"
    assert BENCHMARK_LOCATION.lat == pytest.approx(51.4041)
    assert BENCHMARK_LOCATION.lon == pytest.approx(6.9677)


def test_cdc_products_cover_required_truth_semantics() -> None:
    cases = {
        "TU": ("STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor", "1303;2026040200;9;12.5;71.0;eor"),
        "TD": ("STATIONS_ID;MESS_DATUM;QN_8;TT;TD;eor", "1303;2026040200;8;12.5;7.5;eor"),
        "P0": ("STATIONS_ID;MESS_DATUM;QN_8;P;P0;eor", "1303;2026040200;8;1014.2;996.0;eor"),
        "FF": ("STATIONS_ID;MESS_DATUM;QN_3;F;D;eor", "1303;2026040200;10;4.5;240;eor"),
        "FX": ("STATIONS_ID;MESS_DATUM;QN_8;FX_911;eor", "1303;2026040200;8;11.2;eor"),
        "RR": ("STATIONS_ID;MESS_DATUM;QN_8;R1;RS_IND;WRTR;eor", "1303;2026040200;8;0.7;1;6;eor"),
        "N": ("STATIONS_ID;MESS_DATUM;QN_8;V_N;V_N_I;eor", "1303;2026040200;8;6;I;eor"),
    }
    variables: dict[str, object] = {}
    for product, (header, row) in cases.items():
        for item in _one(product, header, row):
            assert item.station_id == "01303"
            assert item.location_id == BENCHMARK_LOCATION.id
            assert item.source_provider == "DWD"
            assert item.quality_status == "recent_nonfinal_qc"
            assert item.source_metadata["product_code"] == product
            assert item.source_metadata["recent_quality_final"] is False
            assert item.source_metadata["missing_values_omitted_not_imputed"] is True
            variables[item.variable] = item
    assert set(variables) == {
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "pressure_msl",
        "wind_speed_10m",
        "wind_gust_10m",
        "precipitation_1h",
        "cloud_cover",
    }
    assert variables["pressure_msl"].value == pytest.approx(1014.2)
    assert variables["cloud_cover"].value == pytest.approx(75.0)
    assert variables["cloud_cover"].source_metadata["native_value"] == pytest.approx(6.0)
    assert variables["cloud_cover"].source_metadata["native_unit"] == "okta"


def test_cdc_parser_omits_missing_values_and_rejects_station_drift() -> None:
    missing = _one(
        "TU",
        "STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor",
        "1303;2026040200;9;-999;65;eor",
    )
    assert [item.variable for item in missing] == ["relative_humidity_2m"]

    with pytest.raises(ValueError, match="unexpected station"):
        _one(
            "TU",
            "STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor",
            "10416;2026040200;9;12;65;eor",
        )


def test_adapter_fetches_exactly_the_seven_pinned_station_products() -> None:
    payloads = {
        "TU": _zip("TU", "STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor", "1303;2026040200;9;12;65;eor"),
        "TD": _zip("TD", "STATIONS_ID;MESS_DATUM;QN_8;TT;TD;eor", "1303;2026040200;8;12;6;eor"),
        "P0": _zip("P0", "STATIONS_ID;MESS_DATUM;QN_8;P;P0;eor", "1303;2026040200;8;1012;995;eor"),
        "FF": _zip("FF", "STATIONS_ID;MESS_DATUM;QN_3;F;D;eor", "1303;2026040200;10;3;180;eor"),
        "FX": _zip("FX", "STATIONS_ID;MESS_DATUM;QN_8;FX_911;eor", "1303;2026040200;8;7;eor"),
        "RR": _zip("RR", "STATIONS_ID;MESS_DATUM;QN_8;R1;RS_IND;WRTR;eor", "1303;2026040200;8;0;0;0;eor"),
        "N": _zip("N", "STATIONS_ID;MESS_DATUM;QN_8;V_N;V_N_I;eor", "1303;2026040200;8;4;I;eor"),
    }
    calls: list[str] = []

    def fetcher(url: str) -> bytes:
        calls.append(url)
        code = next(product.code for product in PRODUCTS if product.recent_url == url)
        return payloads[code]

    items = DwdCdcObservationAdapter(fetcher=fetcher).fetch_range(start=date(2026, 4, 2), end=date(2026, 4, 2))
    assert len(calls) == 7
    assert {url.rsplit("/", 1)[-1] for url in calls} == {f"stundenwerte_{code}_01303_akt.zip" for code in ("TU", "TD", "P0", "FF", "FX", "RR", "N")}
    assert {item.station_id for item in items} == {"01303"}
    assert {item.location_id for item in items} == {BENCHMARK_LOCATION.id}
