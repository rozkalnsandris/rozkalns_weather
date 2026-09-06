# Architecture

## Goals

- viens privāts lokāls weather dashboard;
- first-class WeatherNext 3 ingestion un verification;
- vienāda point location visiem point-capable modeļiem;
- immutable forecast snapshots;
- provider provenance;
- zema ekspluatācijas sarežģītība uz RPi5;
- viegli paplašināms ar radar, AQI, pollen un citiem slāņiem.

## MVP stack

### Backend

- Python 3
- FastAPI
- SQLite sākumā
- APScheduler/systemd timer/cron tipa scheduled collectors (precīzo runtime orchestration izvēlēsim implementācijas laikā)
- Pydantic provider schemas

### Frontend

- viegls responsive SPA/PWA;
- sākotnēji pietiek ar TypeScript + Vite/React vai līdzvērtīgu minimālu stack;
- mobile-first;
- nav vajadzīga native Android app MVP.

### Private access

Ja dashboard tiek publicēts internetā tehniskai piekļuvei no telefona, tas joprojām paliek privāts. Kandidāts: Cloudflare Tunnel + Cloudflare Access.

Deploy/runtime konfigurācija nav šīs bootstrap dokumentācijas daļa un prasa atsevišķu autorizāciju.

## Logical components

```text
                         +--------------------+
                         | local runtime cfg  |
                         | HOME_LAT/HOME_LON  |
                         +----------+---------+
                                    |
             +----------------------+----------------------+
             |                      |                      |
             v                      v                      v
      WeatherNext 3             DWD adapters          ECMWF adapters
       BigQuery                 ICON/MOSMIX/etc       IFS/AIFS
             |                      |                      |
             +----------------------+----------------------+
                                    |
                                    v
                           provider normalization
                                    |
                 +------------------+------------------+
                 |                                     |
                 v                                     v
         forecast snapshots                     observations
                 |                                     |
                 +------------------+------------------+
                                    |
                                    v
                             verification engine
                                    |
                 +------------------+------------------+
                 |                                     |
                 v                                     v
              REST API                          metrics/materialized
                 |                                  summaries
                 +------------------+------------------+
                                    |
                                    v
                                  PWA
```

## Provider adapter contract

Katram adapterim jāatgriež normalized records ar minimum:

```text
provider
model_provider
model_name
model_version
transport_provider
source_surface
init_time_utc
retrieved_at_utc
valid_time_utc
lead_hours
location_id
variable
statistic
value
unit
native_value
native_unit
quality/status metadata
```

### `location_id`

Database nesaista forecast ar publiski ierakstītu adresi. Lokālajam punktam var lietot stabilu internal ID, piem. `home`.

Precīzās koordinātas glabā runtime config un pēc vajadzības lokālajā DB, kas netiek commitota.

## Database sketch

### `locations`

- `id`
- `label`
- `lat`
- `lon`
- `elevation_m`
- `timezone`

Lokālā DB saturs nav GitHub artifacts.

### `forecast_runs`

- `id`
- `provider`
- `model_name`
- `model_version`
- `init_time_utc`
- `retrieved_at_utc`
- `source_surface`
- `raw_payload_ref/hash`
- `status`

### `forecast_values`

- `run_id`
- `location_id`
- `valid_time_utc`
- `lead_hours`
- `variable`
- `statistic`
- `value`
- `unit`
- `accumulation_window_minutes` where applicable

### `observations`

- `source_provider`
- `station_id`
- `location_id/reference`
- `observed_at_utc`
- `variable`
- `value`
- `unit`
- `quality metadata`

### `warnings`

- `source=dwd`
- CAP identifier
- onset/effective/expires
- severity
- urgency
- certainty
- area metadata
- headline/description

### `verification_scores`

Materialized/cacheable metrics. Raw forecasts un observations paliek primārais auditējamais datu pamats.

## Ingestion cadence

Cadence jābalsta provider publicēšanas režīmā, nevis jāpolling katru minūti bez jēgas.

### WeatherNext 3

- 6-hour synoptic 15-day runs;
- interim hourly 48 h runs;
- jāņem vērā ~7+ h dissemination latency;
- collector schedule jāpieskaņo faktiskajam availability window.

### ICON-D2

- aptuveni ik 3 h;
- īstermiņa 0–48 h.

### MOSMIX-L

- polling cadence atbilstoši DWD published runs; `LATEST` fails ļauj vienkāršu ingest.

### Observations

- pietiekami bieži, lai truth būtu salīdzināms ar forecast valid times;
- saglabāt source timestamps, nevis pieņemt retrieval time kā observation time.

### Radar

- atsevišķs higher-frequency pipeline;
- nebloktē MVP forecast ingestion.

## Raw data retention

MVP optimizācija:

- normalized forecast values glabā vienmēr;
- raw WeatherNext/DWD/ECMWF response var glabāt kā compressed payload/hash/reference atkarībā no izmēra/licences;
- nedrīkst pazaudēt init/version/provenance;
- historical forecast snapshots nedrīkst overwrite ar `latest`.

## API sketch

```text
GET /api/current
GET /api/hourly?hours=48
GET /api/daily?days=15
GET /api/providers
GET /api/providers/{provider}/forecast
GET /api/uncertainty/weathernext3
GET /api/warnings
GET /api/verification/summary
GET /api/verification/by-lead-time
GET /api/health/providers
```

## Failure behavior

Ja viens provider nav pieejams:

- pārējie turpina darboties;
- API atgriež freshness/status;
- UI parāda “stale/unavailable”, nevis klusām aizvieto provider;
- verification neinterpretē missing forecast kā meteoroloģisku kļūdu.

## Combined forecast

Combined ir atsevišķs derived layer. Tas nekad nedrīkst overwrite provider data.

V1: nav automātiskas weighting.

V2+: weights var būt atkarīgi no:

- provider;
- variable;
- lead bucket;
- season;
- recent skill;
- calibration.

Jebkuram Combined output jābūt izskaidrojamam ar izmantotajiem provider weights/version.
