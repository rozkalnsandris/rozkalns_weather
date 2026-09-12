from datetime import datetime, timezone
from rozkalns_weather.providers.open_meteo import ECMWF_AIFS, ECMWF_IFS, ICON_D2, OpenMeteoSingleRunAdapter, parse_model_metadata

PAYLOAD={
"generationtime_ms":1.2,
"hourly_units":{
"time":"iso8601","temperature_2m":"°C","dew_point_2m":"°C","precipitation":"mm",
"pressure_msl":"hPa","cloud_cover":"%","wind_speed_10m":"m/s","wind_gusts_10m":"m/s"},
"hourly":{
"time":["2026-09-07T06:00","2026-09-07T07:00"],
"temperature_2m":[20.0,21.0],"dew_point_2m":[10.0,11.0],"precipitation":[0.0,0.5],
"pressure_msl":[1012.0,1011.5],"cloud_cover":[20.0,30.0],
"wind_speed_10m":[2.0,3.0],"wind_gusts_10m":[4.0,5.0]}}

def test_model_keys_and_metadata_domains_are_explicit()->None:
    assert ICON_D2.model_key=="icon_d2"; assert ICON_D2.meta_domain=="dwd_icon_d2"; assert ECMWF_IFS.model_key=="ecmwf_ifs"; assert ECMWF_AIFS.model_key=="ecmwf_aifs025_single"

def test_metadata_preserves_init_and_availability_separately()->None:
    meta=parse_model_metadata({"last_run_initialisation_time":1788753600,"last_run_availability_time":1788760800,"temporal_resolution_seconds":3600,"update_interval_seconds":10800}); assert meta.init_time_utc<meta.availability_time_utc; assert meta.temporal_resolution_seconds==3600

def test_single_run_request_has_exact_run_and_no_probability_field()->None:
    seen=[]
    def fetcher(url,params): seen.append((url,dict(params))); return PAYLOAD
    adapter=OpenMeteoSingleRunAdapter(ICON_D2,fetcher=fetcher); init=datetime(2026,9,7,6,tzinfo=timezone.utc); available=datetime(2026,9,7,8,tzinfo=timezone.utc); run=adapter.fetch(lat=51.5,lon=7.6,init_time=init,availability_time=available,retrieved_at=datetime(2026,9,7,8,30,tzinfo=timezone.utc)); params=seen[0][1]; assert params["run"]=="2026-09-07T06:00"; assert "precipitation_probability" not in params["hourly"]; assert run.init_time_utc==init; assert run.upstream_available_at_utc==available; assert run.init_time_quality=="single_runs_explicit"; assert run.source_metadata["probability_fields_included"] is False; assert run.source_metadata["provider_contract_drift"]["status"]=="COMPATIBLE"
