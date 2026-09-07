# Benchmark methodology v2

## Location identity

Measured skill is only computed when forecast and truth share the same `location_id`.

- `station_10416`: DWD WMO 10416 reference point; used for measured skill.
- `home`: private runtime-only forecast point; comparison-only until home observations exist.

MOSMIX 10416 is stored at `station_10416`. ICON-D2, IFS, AIFS and WeatherNext are collected at `station_10416` for fair verification and optionally also at `home` for the dashboard.

## Run provenance

Every immutable run preserves provider/model identity, model version when known, `init_time_utc`, `upstream_available_at_utc` when known, `retrieved_at_utc`, valid time, lead, statistic, transport and content/revision provenance.

Open-Meteo comparison models use Single Runs with explicit `run=` initialisation. Metadata `last_run_initialisation_time` and `last_run_availability_time` are used; the documented 10-minute eventual-consistency safety window is respected.

## WeatherNext cycles

WeatherNext 3 is initialized hourly. 00/06/12/18 UTC are `synoptic_360h`; all other hours are `interim_48h`. The collector considers the latest run whose documented BigQuery dissemination target has passed, but the target is not treated as a guarantee: if that run is still absent, it may fall back to an older target-disseminated hourly run. Permission/schema errors are never hidden by that fallback.

## Temperature skill

Primary metrics: MAE, RMSE, bias, sample count and lead-time bucket. WeatherNext additionally reports p10–p90 coverage. Direct rankings use common valid timestamps inside the same lead bucket.

## Run skill vs user-available skill

`station_run_skill` compares true init/lead forecasts against station truth and does not ask whether the forecast had reached a user yet.

Operational/user-available analysis must additionally require the forecast to be available upstream **and** retrieved by this dashboard no later than the decision time. When upstream availability metadata is absent, retrieval time is the conservative boundary. `retrieval_hour_proxy` is never promoted to exact run provenance.

## Precipitation

`precipitation_1h` is an amount in mm for a 60-minute accumulation. `precipitation_probability_1h` is a probability for a versioned event. They are never interchangeable.

Deterministic amount uses amount errors; genuine probability inputs use Brier Score/reliability. WeatherNext BigQuery quantiles are not converted into an exact occurrence probability. Full-ensemble probabilistic verification can later use the 64-member GCS dataset if justified.

## WeatherNext evolution

Monthly reports use the station benchmark, common timestamps within each lead bucket, model-version dimensions and sample-size warnings. Notable misses/wins are derived from real corpus only. Release-note/model change events are surfaced only when a verified event has already been recorded in `model_events`; report generation never fabricates them.

## Authority

DWD warnings remain authoritative. WeatherNext, ICON, IFS and AIFS are forecasts and must not be rendered as official warnings.
