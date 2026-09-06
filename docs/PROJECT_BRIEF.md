# Project brief

## Kāpēc projekts eksistē

Projekts sākās no vēlmes praktiski izmantot un novērtēt **Google WeatherNext 3** savām mājas vajadzībām Vācijā. Mērķis nav tikai parādīt laika prognozi; mērķis ir vienā privātā web skatā redzēt vairākus neatkarīgus modeļus un ilgtermiņā objektīvi izmērīt, kurš no tiem ir precīzāks tieši mūsu lokācijā.

Galvenais jautājums:

> Cik precīzs WeatherNext 3 ir Dortmund-Wickede lokācijā salīdzinājumā ar DWD ICON-D2/MOSMIX un ECMWF IFS/AIFS, un kā tā relatīvā kvalitāte mainās laika gaitā?

## Lokācijas lēmums

Forecast avotiem neizmantojam `Unna`, `Dortmund centre` vai citu pilsētas centru kā approximation. Visi point-capable modeļi saņem vienu un to pašu precīzo mājas WGS84 punktu no lokālas runtime konfigurācijas.

DWD station-based reference:

- WMO / MOSMIX station: **10416 DORTMUND**;
- tā ir piemērota lokālā stacija Dortmund-Wickede / Dortmund Airport apkārtnē;
- DWD publicē `MOSMIX_L_LATEST_10416.kmz`.

Precīzā mājas adrese un koordinātas GitHub netiek glabātas.

## Produkta forma

Privāts responsive web/PWA, lietojams galvenokārt telefonā, pēc informācijas blīvuma līdzīgs tradicionālai weather app, bet ar modeļu salīdzinājumu.

Galvenais ekrāns:

1. pašreizējais novērojums;
2. tuvākās stundas;
3. temperatūras un nokrišņu grafiks;
4. `Combined | DWD | WeatherNext | ECMWF` pārslēgšana;
5. WeatherNext uncertainty diapazons;
6. daily cards;
7. DWD warnings;
8. radar;
9. vēlāk AQI / pollen / UV;
10. atsevišķa accuracy sadaļa.

## Provideru lomas

### WeatherNext 3

Galvenais eksperimentālais modelis un projekta izpētes fokuss. Rādām ne tikai ensemble mean, bet arī percentiles, init time un freshness.

### DWD ICON-D2

Galvenais augstas izšķirtspējas īstermiņa NWP references modelis Vācijai, īpaši 0–48 h logā.

### DWD MOSMIX-L

Lokāla, gatava station-based forecast līnija stacijai 10416.

### DWD observations

Ground-truth kandidāts forecast verification mērķiem. Jāsaglabā arī source station metadata un distance no home point.

### DWD CAP warnings

Vienīgais autoritatīvais warning slānis projektā.

### DWD radar

Nowcasting / faktiskās nokrišņu situācijas slānis. To nedrīkst sajaukt ar modeļa forecast.

### ECMWF IFS HRES

Tradicionāls augstas kvalitātes globālais NWP references modelis vidējam termiņam.

### ECMWF AIFS

Papildu AI-based modelis, lai WeatherNext 3 salīdzinājums nebūtu tikai `AI vs traditional NWP`, bet arī `AI vs AI`.

## Datu adapteri

MVP var izmantot adapterus, kas samazina formātu sarežģītību:

- **Bright Sky** — JSON API virs DWD Open Data, labs observations/alerts/radar/probability prototipēšanai;
- **Open-Meteo** — ērts point API DWD ICON-D2, ECMWF IFS/AIFS un vēsturisku/single-run datu iegūšanai;
- **WeatherNext BigQuery** — sākotnējais WeatherNext 3 point forecast ceļš.

Ilgtermiņā kritiskajiem provider datiem var pāriet uz tiešajiem upstream avotiem, ja vajadzīga pilna kontrole vai reproducējamība.

## Combined forecast princips

Sākumā **neveidojam vienkāršu `(DWD + WN3 + ECMWF) / 3`**. Pirmajā periodā provider prognozes jāredz atsevišķi un jākrāj verifikācijas dati.

Tikai pēc pietiekama lokālā corpus var ieviest svarotu Combined prognozi, piemēram, svarus nosakot pēc:

- lead-time bucket;
- mainīgā (temperature, precipitation, wind);
- sezonas;
- pēdējo 30/90 dienu skill;
- calibration/reliability.

Combined prognoze vienmēr saglabā iespēju apskatīt oriģinālos provider output.

## Privātums

Projekts ir paredzēts personīgai lietošanai. Precīzie home coordinates ir runtime secrets/config, nevis repository saturs.

Ja web būs pieejams no interneta, plānotais variants ir autentificēta pieeja, piemēram, Cloudflare Access.

## Sākotnējie non-goals

- publisks weather portal;
- komerciāls API;
- mobilā native app pirms PWA;
- smags ML ensemble modelis pirms pietiekamiem verifikācijas datiem;
- WeatherNext izmantošana severe-weather warning vietā.
