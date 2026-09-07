# rozkalns_weather

Privāts, lokāli orientēts laikapstākļu dashboard + forecast-verification projekts Dortmund-Wickede apkārtnei.

## Kāpēc projekts eksistē

Projekta centrā ir **Google WeatherNext 3**. Mērķis nav tikai parādīt prognozi, bet ilgstoši saglabāt immutable forecast snapshotus un izmērīt, cik precīzs WeatherNext 3 ir tieši mūsu lokācijā salīdzinājumā ar DWD un ECMWF.

Galvenais cikls:

```text
forecast snapshot -> observation -> verification -> WeatherNext comparison
```

WeatherNext 3 ir `primary_research` modelis. Tas nav oficiāls warning source; severe-weather brīdinājumu autoritāte Vācijā paliek **DWD**.

## Provideri

- **WeatherNext 3** — BigQuery 0.05° station-head temperatūrai/dew point + 0.1° surface laukiem, ensemble `mean/p10/p25/p50/p75/p90`;
- **DWD MOSMIX-L 10416** — lokāls station-based baseline;
- **DWD observations / WMO 10416** — verifikācijas truth, transportēts ar Bright Sky/DWD Open Data;
- **DWD ICON-D2** — high-resolution short-range baseline caur Open-Meteo ar saglabātu upstream model identity;
- **ECMWF IFS HRES** — tradicionāls globālais baseline;
- **ECMWF AIFS** — AI baseline;
- **DWD CAP warnings + radar** — atsevišķs safety/observed slānis.

## Lokācija un privacy

Repo satur tikai publiski drošo `Dortmund-Wickede` label un DWD/WMO stacijas ID `10416`. Precīzā adrese, `HOME_LAT`, `HOME_LON`, Google credentials un Cloudflare/runtime secrets **netiek commitoti**.

Runtime `.env`:

```dotenv
HOME_LAT=
HOME_LON=
HOME_TIMEZONE=Europe/Berlin
HOME_LABEL=Dortmund-Wickede
GOOGLE_CLOUD_PROJECT=
WEATHERNEXT_BIGQUERY_DATASET=
DATABASE_URL=sqlite:///data/weather.db
```

## Implementācija

Backend: Python 3.12+, FastAPI, SQLite. Forecast runs/values ir DB-līmenī immutable. Provider failure ir izolēts; status/freshness tiek rādīts atsevišķi.

Svarīgākie endpointi:

```text
GET /health
GET /api/providers
GET /api/health/providers
GET /api/hourly?hours=48&variable=temperature_2m
GET /api/verification/summary?days=30
GET /api/warnings
GET /api/radar
```

Web/PWA ir iebūvēts FastAPI static slānī ar `Overview`, `Models`, `Accuracy`, `Warnings/Radar` skatiem. WeatherNext 3 ir vizuāli izcelts kā pētniecības modelis, nevis oficiāla autoritāte.

## Collectors

Publiskie baseline provideri:

```bash
rozkalns-weather ingest-public
```

WeatherNext 3 pēc Google allowlist/BigQuery konfigurācijas:

```bash
rozkalns-weather ingest-weathernext
```

WeatherNext live ingest izmanto optional dependency:

```bash
pip install '.[weathernext]'
```

Ja allowlist/config nav gatavs, sistēma paliek `access_pending`; tā nedrīkst ģenerēt/fabricēt WeatherNext datus.

## Verification v1

Temperatūrai ir MAE, RMSE, bias, lead-time buckets, 30d/90d logi un WeatherNext `p10-p90` coverage. Forecast/observation matching V1 ir exact hourly timestamp (`0 min` tolerance), lai noteikums būtu reproducējams. Model version tiek saglabāts un metrics API atdala versijas.

## Deployment

`Dockerfile`, `deploy/docker-compose.example.yml`, systemd timer piemēri un `docs/OPERATIONS.md` sagatavo RPi5 deploymentu, bet **nekāds live deploy, secrets, Cloudflare vai host mutation netiek veikts bez atsevišķas autorizācijas**.

## Dokumentācija

- [WeatherNext 3](docs/WEATHERNEXT3.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Verification](docs/VERIFICATION.md)
- [Roadmap](docs/ROADMAP.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Operations](docs/OPERATIONS.md)
- [Sources](docs/SOURCES.md)
