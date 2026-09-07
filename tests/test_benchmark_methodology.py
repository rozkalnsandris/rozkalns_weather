from datetime import datetime,timezone
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun,ForecastValue,Observation

def _run()->ForecastRun:
    init=datetime(2026,9,7,0,tzinfo=timezone.utc);return ForecastRun(provider="icon_d2",model_provider="DWD",model_name="ICON-D2",init_time_utc=init,retrieved_at_utc=datetime(2026,9,7,3,tzinfo=timezone.utc),upstream_available_at_utc=datetime(2026,9,7,2,30,tzinfo=timezone.utc),init_time_quality="single_runs_explicit",source_surface="test",values=(ForecastValue(valid_time_utc=datetime(2026,9,7,6,tzinfo=timezone.utc),lead_hours=6,variable="temperature_2m",value=20.0,unit="degC"),))

def test_home_forecast_is_not_verified_against_station_truth(tmp_path)->None:
    db=Database(f"sqlite:///{tmp_path/'weather.db'}");db.initialize();db.ensure_location(location_id=DWD_10416.id,label=DWD_10416.label,lat=DWD_10416.lat,lon=DWD_10416.lon,elevation_m=DWD_10416.elevation_m,timezone=DWD_10416.timezone);db.ensure_home_location(label="Home",lat=51.5,lon=7.6,timezone="Europe/Berlin");db.insert_observations([Observation(source_provider="DWD",station_id="10416",location_id=DWD_10416.id,observed_at_utc=datetime(2026,9,7,6,tzinfo=timezone.utc),variable="temperature_2m",value=19.0,unit="degC")]);db.insert_forecast_run(_run(),location_id="home");assert db.temperature_verification_pairs(days=3650,location_id=DWD_10416.id)==[];db.insert_forecast_run(_run(),location_id=DWD_10416.id);pairs=db.temperature_verification_pairs(days=3650,location_id=DWD_10416.id);assert len(pairs)==1;assert pairs[0]["truth_location_id"]==DWD_10416.id
