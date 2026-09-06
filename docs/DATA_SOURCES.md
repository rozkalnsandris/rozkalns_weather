# Data sources

## Source hierarchy

Šajā projektā nav viena “labākā” weather source. Katram avotam ir sava loma.

### 1. Official warnings

**DWD official warnings / CAP** ir autoritatīvais severe-weather warning source Vācijā.

WeatherNext, ICON, ECMWF un Combined forecast nedrīkst aizstāt DWD warnings.

### 2. Ground truth / observations

Galvenais tuvākais station-based references punkts:

- `WMO 10416 DORTMUND`;
- DWD MOSMIX single-station endpoint eksistē kā `MOSMIX_L_LATEST_10416.kmz`;
- precīzs home point modeļiem tiek glabāts lokāli, nevis repository.

Observation ingestion jāglabā:

- station ID/name;
- station coordinates/elevation;
- timestamp;
- measurement value;
- QC/source flags, ja pieejami;
- distance no home point.

DWD stacija ir labs praktiskais truth references punkts, bet tā nav identiska mājas mikroklimatam. Vēlāk iespējams pievienot lokālu mājas sensoru kā atsevišķu truth stream.

## DWD MOSMIX-L

DWD publicē gatavu local forecast konkrētām stacijām.

Mūsu sākuma station ID: **10416**.

Tiešais katalogs:

`https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/10416/kml/`

Aktuālais fails:

`MOSMIX_L_LATEST_10416.kmz`

Loma:

- station-oriented hourly/local forecast;
- DWD references līnija blakus model-grid forecasts;
- vienkāršs robusts baseline.

## DWD ICON-D2

Galvenais īstermiņa modelis Vācijai.

Open-Meteo DWD dokumentācija norāda:

- region: Central Europe;
- resolution: ~0.02° / ~2 km;
- native temporal resolution: līdz 15 min noteiktiem mainīgajiem;
- forecast length: ~2 dienas;
- update frequency: ik 3 h.

Loma:

- 0–48 h forecast;
- temperatūra;
- precipitation;
- vējš/gusts;
- convective/lightning-supporting variables, ja vēlāk vajag;
- comparison pret WeatherNext 3.

Point request jāveic uz precīzu `HOME_LAT`, `HOME_LON`, nevis Unna/Dortmund centru.

## DWD radar

Radar ir observation/nowcasting slānis, nevis tāds pats forecast provider kā ICON/WeatherNext.

Loma:

- pašreizējā precipitation situācija;
- lietus kustības vizualizācija;
- “rain approaching” UX;
- forecast verification konteksts.

MVP var sākt ar Bright Sky radar funkcijām vai DWD Open Data, bet ilgtermiņā jāvērtē tiešais upstream DWD ingest reproducējamībai.

## DWD CAP warnings

Loma:

- official warning banner;
- severity/urgency/certainty;
- effective/expiry time;
- administratīvās teritorijas filtrēšana;
- nekad nejaukt ar AI-generated risk score.

## Bright Sky

Bright Sky ir open-source JSON API virs DWD Open Data.

Priekšrocības MVP:

- nav API key;
- point queries ar `lat/lon`;
- atgriež source station metadata un distance;
- weather observations;
- precipitation probabilities;
- weather radar;
- weather alerts;
- vienkāršs JSON.

Loma projektā: **adapter/prototyping layer**, nevis primārais meteoroloģiskais source of truth. Upstream provenance vienmēr ir DWD.

Reference: https://brightsky.dev/

## Google WeatherNext 3

Galvenais pētniecības modelis.

MVP access: BigQuery pēc allowlist apstiprināšanas.

Loma:

- AI point forecast;
- ensemble mean/percentiles;
- 15-day medium-range salīdzinājums;
- model evolution tracking;
- lokāla accuracy verification.

Sk. `docs/WEATHERNEXT3.md`.

## ECMWF IFS HRES

Tradicionāls high-quality global NWP references modelis.

Open-Meteo ECMWF dokumentācija pašlaik norāda:

- native IFS HRES ~9 km;
- up to 15 days;
- 1-hourly pirmajām ~90 h, vēlāk retāks native timestep;
- updates ik 6 h.

Loma:

- medium-range baseline;
- WeatherNext 3 comparison;
- traditional NWP vs AI skill.

## ECMWF AIFS

ECMWF AI forecasting model.

Loma:

- AI-vs-AI comparison ar WeatherNext 3;
- medium-range skill benchmarking;
- izvairīties no pārāk vienkārša “AI vs classic NWP” secinājuma.

Pirms implementācijas precīzi jāpārbauda izvēlētā AIFS produkta resolution, ensemble/deterministic semantics un timestep.

## Open-Meteo

Open-Meteo ir ērts adapteris vairākiem upstream weather modeļiem.

MVP izmantošanas kandidāti:

- DWD ICON-D2;
- ECMWF IFS HRES;
- ECMWF AIFS;
- previous/single runs verifikācijas workflow;
- air quality / pollen / UV papildslāņi.

Svarīgi: datubāzē jāglabā **upstream model identity**, nevis tikai `provider=open-meteo`. Piemēram:

```text
transport_provider = open-meteo
model_provider     = dwd
model_name         = icon_d2
```

Tas saglabā provenance.

## Air quality / pollen / UV

V2+ papildinājumi:

- European AQI;
- PM2.5;
- PM10;
- NO2;
- O3;
- pollen categories;
- UV index.

Tie nav centrālie WeatherNext benchmarka mainīgie, tāpēc nedrīkst aizkavēt MVP.

## Data freshness policy

Katram provider response saglabā:

- `retrieved_at_utc`;
- `source_init_time_utc`, ja ir;
- `valid_time_utc`;
- `published_at_utc`, ja avots dod;
- provider status/error;
- adapter version.

UI rāda provider freshness un nedrīkst klusām prezentēt stale data kā current.

## Normalization

Canonical datu slānī:

- temperature: °C;
- precipitation amount: mm ar explicit accumulation window;
- precipitation probability: 0–1 vai 0–100%, konsekventi storage schema;
- wind: m/s canonical, display var būt km/h;
- pressure: hPa;
- time: UTC storage, `Europe/Berlin` display.

Jāglabā arī native unit/value metadata, ja tas vajadzīgs auditam.

## Source references

- DWD Open Data: https://opendata.dwd.de/
- DWD MOSMIX 10416: https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/10416/kml/
- Bright Sky: https://brightsky.dev/
- Open-Meteo DWD: https://open-meteo.com/en/docs/dwd-api
- Open-Meteo ECMWF: https://open-meteo.com/en/docs/ecmwf-api
- WeatherNext: https://developers.google.com/weathernext/
