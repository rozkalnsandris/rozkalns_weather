# Forecast verification

## Mērķis

Galvenā projekta vērtība ir nevis tikai “parādīt vairākus modeļus”, bet **objektīvi izmērīt WeatherNext 3 un citu modeļu lokālo skill**.

Galvenais princips:

> Forecast jānovērtē pret to, kas bija zināms un pieejams prognozes izdošanas brīdī, un pēc tam pret neatkarīgu reālo novērojumu.

Nedrīkst izmantot vēlāk atjaunotu prognozi kā aizvietojumu tam forecast, ko modelis deva agrāk.

## Provider minimum

Benchmark tabulā vismaz:

- WeatherNext 3;
- DWD ICON-D2;
- DWD MOSMIX-L 10416;
- ECMWF IFS HRES;
- ECMWF AIFS.

Papildus var vērtēt Combined forecast pēc tam, kad ir pietiekams corpus.

## Truth source

Sākotnēji:

- DWD observations no piemērotākās lokālās stacijas, primāri `10416 DORTMUND`, ja konkrētais parametrs/stundas novērojums ir pieejams;
- jāglabā station metadata un distance;
- DWD radar var kalpot precipitation event truth/context, bet tā interpretācija jādefinē atsevišķi.

Vēlāk:

- lokāls mājas weather sensor var tikt pievienots kā atsevišķs ground-truth stream;
- nedrīkst automātiski sajaukt home sensor un DWD station observations vienā truth series bez source dimension.

## Forecast snapshot policy

Katru provider run saglabājam immutable.

Minimum key:

```text
(provider, model_version, init_time, location, valid_time, variable, statistic)
```

Ja provider vēlāk labo/pārpublicē to pašu run, saglabājam revision/retrieval metadata, nevis klusām pārrakstām vēsturi.

## Lead-time buckets

Metrics nerēķina tikai vienā kopējā vidējā. Minimum buckets:

- 0–6 h
- 6–12 h
- 12–24 h
- 24–48 h
- 2–3 d
- 3–5 d
- 5–7 d
- 7–10 d
- 10–15 d

Ne visi provider aptver visus buckets. Salīdzinājumu veic tikai kopīgajā pieejamības logā.

## Temperature metrics

Minimum:

### MAE

`mean(abs(forecast - observed))`

Viegli interpretējams galvenais rādītājs.

### RMSE

Vairāk soda lielas kļūdas.

### Bias

`mean(forecast - observed)`

Parāda sistemātisku par siltu/par aukstu tendenci.

### Median absolute error

Noder robustumam pret atsevišķiem outlier.

Rādām metric pēc:

- provider/model version;
- lead bucket;
- 30/90 dienu window;
- kalendārā mēneša/sezonas;
- day/night, ja pietiek datu.

## Precipitation verification

Nedrīkst salīdzināt tikai “mm kļūdu”, jo precipitation ir gan occurrence, gan amount problēma.

### Occurrence

Definē event threshold, piemēram, `>= 0.1 mm/h` vai citu explicit slieksni.

Probabilistic forecasts:

- Brier Score;
- reliability/calibration;
- hit/miss/false alarm summary pie izvēlētiem probability threshold.

Deterministic amount:

- MAE/RMSE precipitation amount;
- event-conditioned error;
- accumulated 3 h / 6 h / 24 h totals, ja accumulation semantics ir pareizi normalizēti.

WeatherNext 3 percentiles/ensemble nedrīkst reducēt uz vienu deterministic number pirms saglabāšanas.

## Wind verification

Atsevišķi:

- sustained wind speed;
- gusts, ja provider/truth semantiski salīdzināmi;
- direction circular error, ja ieviešam.

Svarīgi nesalīdzināt 10 m mean wind ar gust kā vienu un to pašu mainīgo.

## WeatherNext uncertainty verification

WeatherNext 3 ensemble ir viena no projekta galvenajām priekšrocībām.

Jāvērtē:

- cik bieži observation iekrīt `p10–p90` intervalā;
- interval width;
- calibration pēc lead time;
- vai šaurāks interval tiešām nozīmē mazāku kļūdu;
- reliability diagrams precipitation probability, ja pieejams atbilstošs probabilistic field.

## Fair-comparison rules

1. Izmanto vienu un to pašu valid time.
2. Izmanto vienu un to pašu home location semantics, cik modelis to ļauj.
3. Saglabā provider native init time.
4. Nesaņem vēlāk publicētu run un neuzdod to par agrāku prognozi.
5. Izmanto tikai forecast, kas bija pieejams pirms valid time.
6. Normalizē units un accumulation windows.
7. Salīdzinājumos skaidri norādi sample size `n`.
8. Neizdari secinājumus no ļoti maza sample.
9. Model version changes rāda atsevišķi.
10. Missing data nav forecast error.

## Data availability bias

WeatherNext dissemination latency var būt būtiska. Ja salīdzinām “freshest available forecast at decision time”, jāglabā:

- `init_time`;
- `published/available time`, ja iespējams;
- `retrieved_at`.

Tad var būt divi benchmark režīmi:

### Run-to-run skill

Salīdzina līdzīga init cikla modeļus.

### User-available skill

Salīdzina labāko forecast, kas reāli bija pieejams lietotājam konkrētajā brīdī.

Abi atbild uz atšķirīgiem jautājumiem un nedrīkst tikt sajaukti.

## Rolling dashboards

Plānotie summary:

```text
Temperature MAE — last 30 days
WeatherNext 3   1.1 °C
ICON-D2         0.9 °C
MOSMIX          1.0 °C
IFS HRES        1.2 °C
AIFS            1.1 °C
```

Tas ir tikai UI piemērs; nedrīkst izmantot izdomātus skaitļus produkcijas datos.

Papildu skati:

- 30d / 90d / all-time;
- by lead time;
- by model version;
- temperature / precipitation / wind tabs;
- WeatherNext p10–p90 calibration;
- worst misses;
- best/worst event types.

## Combined forecast eligibility

Combined weighting nedrīkst sākties, kamēr nav:

- pietiekams common-period sample;
- vismaz vairāku nedēļu datu, bet vēlams sezonāli plašāks corpus;
- stabila provenance;
- pārbaudīta missing-data logic;
- metric pipeline tests.

Sākuma Combined var būt tikai vizuāls konsenss, nevis “mūsu modelis”.

Kad weighting tiek ieviests, weights jāsaglabā ar version un training/evaluation window, lai rezultāts būtu auditējams.

## WeatherNext evolution report

Reizi mēnesī vai pēc būtiska model release var ģenerēt:

- WeatherNext version;
- sample period;
- lead-time skill vs ICON-D2/IFS/AIFS;
- change vs previous period;
- uncertainty calibration;
- notable failure cases;
- release-note/context links.

Tas tieši atbalsta projekta mērķi sekot, **kā WeatherNext 3 attīstās mūsu lokācijā**.
