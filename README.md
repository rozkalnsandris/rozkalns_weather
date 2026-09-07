# rozkalns_weather

Privāts, lokāli orientēts laikapstākļu projekts mājas vajadzībām Dortmund-Wickede apkārtnē.

## Galvenais mērķis

Projekta centrā ir **Google WeatherNext 3**: iegūt tā prognozes konkrētam mājas punktam, salīdzināt tās ar DWD un ECMWF modeļiem, ilgtermiņā izmērīt, cik precīzs WeatherNext 3 ir tieši mūsu lokācijā, un sekot tam, kā modeļa kvalitāte attīstās.

Šis nav paredzēts kā publisks weather service. Sākotnējais mērķis ir privāts web/PWA skats ģimenei.

## Pamatideja

Vienā mobilajam draudzīgā web skatā apvienot:

- **WeatherNext 3** — galvenais eksperimentālais/izpētes modelis;
- **DWD ICON-D2** — augstas izšķirtspējas īstermiņa modelis Vācijai;
- **DWD MOSMIX-L** — lokāla station-based prognoze;
- **DWD observations** — faktiskie novērojumi verifikācijai;
- **DWD CAP warnings** — vienīgais autoritatīvais warning slānis;
- **DWD radar** — faktiskie/ļoti īstermiņa nokrišņi;
- **ECMWF IFS HRES** — tradicionāls globālais etalons;
- **ECMWF AIFS** — vēl viens AI modelis salīdzinājumam;
- vēlāk: AQI, pollen un UV.

## WeatherNext 3 projektā ir īpašā lomā

WeatherNext 3 nav vienkārši vēl viens modelis sarakstā. Projekts radās tieši tāpēc, lai:

1. redzētu WeatherNext 3 prognozi blakus DWD/ECMWF;
2. saglabātu katras prognozes snapshot pirms notikuma;
3. pēc tam salīdzinātu prognozi ar reāli novēroto;
4. mērītu kļūdas pēc lead time, sezonas un parametra;
5. redzētu WeatherNext 3 ensemble nenoteiktību (`mean`, `p10`, `p25`, `p50`, `p75`, `p90`);
6. sekotu modeļa versiju un kvalitātes izmaiņām laika gaitā.

Sk. [docs/WEATHERNEXT3.md](docs/WEATHERNEXT3.md) un [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Lokācija

- Darba lokācija: **Dortmund-Wickede**.
- DWD lokālais references punkts: **DORTMUND / WMO 10416** (`MOSMIX_L_LATEST_10416.kmz`).
- **Unna nav jāizmanto kā forecast bāze.** Modeļiem jāpadod precīzs mājas WGS84 punkts, nevis pilsētas centrs vai tuvākā pilsēta.
- Precīza mājas adrese un koordinātas netiek glabātas GitHub. Tās būs tikai lokālā runtime konfigurācijā (`HOME_LAT`, `HOME_LON`).

> Piezīme: repository pašlaik ir publisks. Tāpēc tajā apzināti netiek commitota precīza mājas adrese, koordinātas, API credentials vai citi sensitīvi dati.

## Plānotā arhitektūra

```text
Home WGS84 point
      |
      +-- WeatherNext 3 (BigQuery initially)
      +-- DWD ICON-D2
      +-- DWD MOSMIX-L / observations
      +-- DWD CAP warnings
      +-- DWD radar
      +-- ECMWF IFS / AIFS
                |
                v
        collectors/adapters
                |
                v
       normalized forecast DB
                |
        +-------+--------+
        |                |
   verification       REST API
        |                |
        +---------> Web/PWA
```

MVP backend virziens: **Python + FastAPI + SQLite**. Frontend: viegls responsive web/PWA. Privātu ārējo pieeju vēlāk var nodrošināt ar Cloudflare Access.

## Dokumentācija

- [Project brief](docs/PROJECT_BRIEF.md)
- [WeatherNext 3](docs/WEATHERNEXT3.md)
- [Data sources](docs/DATA_SOURCES.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Forecast verification](docs/VERIFICATION.md)
- [UI / UX](docs/UI.md)
- [Roadmap](docs/ROADMAP.md)
- [FAST-LANE v2.2 local contract](docs/FAST_LANE_V2_2.md)
- [Source references](docs/SOURCES.md)

## GitHub darba modelis

Repo izmanto shared `ops-workflows` FAST-LANE v2.2, GITHUB-ONLY/LIVE-ALL, START_GITHUB_ONLY un Agent Work Cycle v1 modeli. Reusable policy CI ir piesaistīts immutable exact `ops-workflows` commit SHA; lokālie privacy un DWD official-warning noteikumi ir stingrāki un paliek autoritatīvi.

## Pašreizējais statuss

**Bootstrap / research design.** Vēl nav runtime implementācijas.

Pirmais ārējais WeatherNext 3 blocker ir Google real-time forecast allowlist pieeja. DWD un ECMWF daļu var sākt būvēt neatkarīgi no tās.
