from datetime import datetime, timezone
import io
import zipfile

from rozkalns_weather.providers.dwd_mosmix import parse_mosmix_kmz


def _kmz() -> bytes:
    kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:dwd="https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd">
<Document>
<dwd:ProductDefinition><dwd:IssueTime>2026-09-07T00:00:00Z</dwd:IssueTime></dwd:ProductDefinition>
<dwd:ForecastTimeSteps><dwd:TimeStep>2026-09-07T01:00:00Z</dwd:TimeStep><dwd:TimeStep>2026-09-07T02:00:00Z</dwd:TimeStep></dwd:ForecastTimeSteps>
<Placemark><ExtendedData>
<dwd:Forecast dwd:elementName="TTT"><dwd:value>293.15 294.15</dwd:value></dwd:Forecast>
<dwd:Forecast dwd:elementName="PPPP"><dwd:value>101300 101200</dwd:value></dwd:Forecast>
<dwd:Forecast dwd:elementName="RR1c"><dwd:value>0.1 1.2</dwd:value></dwd:Forecast>
</ExtendedData></Placemark>
</Document></kml>'''
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("MOSMIX.kml", kml)
    return stream.getvalue()


def test_mosmix_parser_normalizes_units_and_provenance() -> None:
    run = parse_mosmix_kmz(_kmz(), retrieved_at=datetime(2026, 9, 7, 3, tzinfo=timezone.utc))
    assert run.provider == "dwd_mosmix_l"
    assert run.source_metadata["station_id"] == "10416"
    temps = [v for v in run.values if v.variable == "temperature_2m"]
    assert [round(v.value, 1) for v in temps] == [20.0, 21.0]
    pressure = next(v for v in run.values if v.variable == "pressure_msl")
    assert pressure.value == 1013.0
    rain = next(v for v in run.values if v.variable == "precipitation_1h")
    assert rain.accumulation_window_minutes == 60
