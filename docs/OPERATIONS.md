# Operations — private RPi5 deployment candidate

Šis ir deploy-ready source contract, nevis live deployment authorization.

## Runtime prerequisites

- Python 3.12+ vai Docker;
- persistent writable `data/` volume;
- private `.env` containing exact home coordinates;
- internet access to DWD/Bright Sky/Open-Meteo;
- WeatherNext live ingestam: Google allowlist + Google Cloud credentials + Analytics Hub linked dataset.

## Private `.env`

Never commit this file.

```dotenv
HOME_LAT=<private>
HOME_LON=<private>
HOME_TIMEZONE=Europe/Berlin
HOME_LABEL=Dortmund-Wickede
DATABASE_URL=sqlite:///data/weather.db
GOOGLE_CLOUD_PROJECT=<private-project>
WEATHERNEXT_BIGQUERY_DATASET=<private-linked-dataset>
```

Google authentication should use normal Application Default Credentials/service identity outside Git. Do not put service-account JSON in repo.

## Local validation

```bash
python -m pytest
uvicorn rozkalns_weather.app:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/health/providers
```

Health output must never contain `HOME_LAT`/`HOME_LON`.

## Collectors

Public baselines can run independently from WeatherNext:

```bash
rozkalns-weather ingest-public
```

WeatherNext is intentionally separate so allowlist/credential errors do not block DWD/ECMWF:

```bash
rozkalns-weather ingest-weathernext
```

Suggested cadence candidates in `deploy/` are conservative templates, not active timers.

## Docker candidate

```bash
docker compose -f deploy/docker-compose.example.yml up -d --build
```

The compose template binds a configurable host port and keeps SQLite in a named volume. Do not expose it publicly without an explicit private-access design.

## Cloudflare

If remote mobile access is later needed, preferred design is Cloudflare Tunnel + Access authentication. Creating/changing tunnel routes, DNS, Access policies or credentials is a separate LIVE/Cloudflare authorization.

## WeatherNext readiness

A live WeatherNext run is Ready only when:

1. Google allowlist access works;
2. linked BigQuery dataset contains both `weathernext_3_0_0_0p05deg` and `weathernext_3_0_0_0p1deg`;
3. schema probe returns expected field paths;
4. home point is private runtime config;
5. `ingest-weathernext` stores a real immutable run;
6. API health shows a successful WeatherNext ingest timestamp.

Never replace missing live data with fabricated fixture values.

## Backup / recovery

The primary runtime state is the SQLite DB. Back up `data/weather.db` consistently (SQLite online backup or stopped-service copy). Forecast tables are immutable; provider status rows and location config are mutable runtime state.

## Attribution / authority

- DWD remains official warning authority.
- Bright Sky is a transport/API layer over DWD data.
- Open-Meteo is transport/interpolation for ICON-D2/ECMWF adapters; upstream model identity remains visible.
- WeatherNext 3 is experimental/research output and is never shown as an official warning.
