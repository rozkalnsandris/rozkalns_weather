# Operations — private RPi5 deployment candidate

Šis ir deploy-ready source contract, nevis LIVE authorization. Source/CI state pats par sevi nepierāda, ka RPi5 ir deployots.

## Runtime prerequisites

- Python 3.12+ vai Docker;
- persistent writable `data/` volume;
- private `.env` ar exact home point;
- internet access DWD/Bright Sky/Open-Meteo;
- WeatherNext live ingestam: Google allowlist, Google Cloud credentials un Analytics Hub linked dataset.

## Private `.env`

Never commit this file.

```dotenv
HOME_LAT=<private>
HOME_LON=<private>
HOME_TIMEZONE=Europe/Berlin
HOME_LABEL=Dortmund-Wickede

GOOGLE_CLOUD_PROJECT=<private-project>
WEATHERNEXT_BIGQUERY_DATASET=<private-linked-dataset>

INGEST_TIMEOUT_SECONDS=20
INGEST_RETRIES=2
PRECIP_EVENT_THRESHOLD_MM=0.1

DATABASE_URL=sqlite:///data/weather.db
WEATHER_PORT=9180
```

Google authentication izmanto Application Default Credentials/service identity ārpus Git. Service-account JSON, API keys un tokens repo nedrīkst nonākt.

## Source-level validation

Mandatory CI paliek fixture-driven un network-independent:

```bash
python -m pytest
```

Optional read-only public feed preflight:

```bash
rozkalns-weather smoke-public
```

Corpus/source diagnostics:

```bash
rozkalns-weather corpus-check
rozkalns-weather corpus-stats
```

## WeatherNext first-live preflight

Pēc allowlist approval un tikai privātajā runtime:

```bash
rozkalns-weather diagnose-weathernext --no-point-query
rozkalns-weather diagnose-weathernext
```

Diagnostic output nedrīkst rādīt credentials vai coordinates. Ready nozīmē:

1. linked dataset satur `weathernext_3_0_0_0p05deg` un `weathernext_3_0_0_0p1deg`;
2. schema validator atrod sagaidītos station-head/surface field paths;
3. query ir bounded ar `init_time` partition filter un selected columns;
4. point query atgriež reālus provider datus.

Tikai pēc tam:

```bash
rozkalns-weather ingest-weathernext
rozkalns-weather corpus-check
rozkalns-weather corpus-stats
```

Ja jaunākā hourly run target dissemination window ir pagājis, bet data vēl nav redzama, collectors drīkst fallback tikai uz iepriekšēju target-disseminated hourly run. Permission/schema kļūdas netiek maskētas ar fallback. WeatherNext vērtības nekad netiek fabricētas.

## Public baseline collectors

```bash
rozkalns-weather ingest-public
```

Tas krāj `station_10416` benchmark forecasts + DWD observations un, ja private home config eksistē, arī atsevišķus `home` forecast snapshotus.

## API preflight

```bash
uvicorn rozkalns_weather.app:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/health/providers
curl -fsS 'http://127.0.0.1:8000/api/hourly?hours=48&variable=temperature_2m'
curl -fsS 'http://127.0.0.1:8000/api/verification/summary?days=30'
```

Health/API output nedrīkst saturēt `HOME_LAT` vai `HOME_LON`.

## Timer/deploy candidates

Repo satur tikai templates:

- `deploy/rozkalns-weather-public-ingest.service.example`
- `deploy/rozkalns-weather-public-ingest.timer.example`
- `deploy/rozkalns-weather-weathernext.service.example`
- `deploy/rozkalns-weather-weathernext.timer.example`
- `deploy/docker-compose.example.yml`

Tie nav live RPi5 state pierādījums.

## Exact LIVE gate preflight

Pirms jebkādas RPi5 mutation svaigi jānosaka:

- exact target host;
- reviewed/merged source SHA;
- current deployed SHA/image/files;
- exact Docker/systemd targets;
- exact `.env`/credential prerequisites (vērtības neizpaužot);
- current DB/corpus baseline;
- mutation envelope;
- health + corpus verification commands;
- rollback semantics.

Merge neautorizē šo soli. Atsevišķa explicit LIVE authorization ir obligāta pirms deploy/redeploy/restart, systemd/Docker timer mutation, credentials, Cloudflare, DB/schema/data vai filesystem permission izmaiņām.

## Backup / recovery

Pirms long-running corpus start jābūt persistent SQLite storage. Source piedāvā consistent backup command:

```bash
rozkalns-weather backup --output <private-backup-path>
```

Backup/restore veikšana live runtime ir atsevišķa LIVE/data mutation authority. Forecast tables ir immutable; provider status/location config ir mutable runtime state.

## Monthly WeatherNext evolution report

Pēc reāla corpus uzkrāšanas:

```bash
rozkalns-weather report-monthly --month YYYY-MM
```

Report salīdzina tikai `station_10416` location-matched truth, sadala pa lead bucket/model version/common timestamps, rāda sample warning, notable misses/wins un tikai iepriekš verificētus `model_events`. Release-note events netiek izdomāti.

## Authority

- DWD ir official warning authority.
- Bright Sky ir DWD transport/API slānis.
- Open-Meteo ir transport layer; ICON-D2/IFS/AIFS upstream identity paliek saglabāta.
- WeatherNext 3 ir experimental/research forecast un nekad netiek rādīts kā official warning.
