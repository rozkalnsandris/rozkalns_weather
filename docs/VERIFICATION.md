# Forecast verification

## Mērķis

Projekta galvenā vērtība ir objektīvi izmērīt WeatherNext 3 un citu modeļu lokālo skill, saglabājot reproducējamu forecast provenance. Forecast snapshot netiek aizvietots ar vēlāk publicētu run.

## Truth un location semantics

Measured benchmark izmanto publisko DWD WMO `10416` reference location `station_10416`. Historical truth backfill ir pinned tieši uz WMO `10416`; Bright Sky ir transport, DWD paliek source authority. Ja transport response source metadata neapstiprina 10416, dati netiek klusām pāradresēti uz nearest station.

Privātais `home` punkts ir atsevišķs comparison stream. Home forecast netiek saukts par izmērītu home accuracy, kamēr nav home observation truth.

## Immutable forecast policy

Minimum identity saglabā:

```text
(provider, model_version, init_time, location, valid_time, variable, statistic, retrieval/revision provenance)
```

Identisks payload ir idempotents. Ja upstream pārpublicē citu payload tam pašam run, tas ir jauns revision; vecais snapshot netiek pārrakstīts.

Historical Open-Meteo Single Runs saglabā explicit `run=` initialization. Ja historical surface neizpauž original availability timestamp, `upstream_available_at_utc` paliek `null`; retrieval time netiek fabricēts par publication time.

## Deterministic baseline

Strict exact-run archive comparatori:

- DWD ICON-D2;
- ECMWF IFS HRES;
- ECMWF AIFS 0.25° Single.

Common public archive comparison window sākas `2026-04-02`. IFS vecāks history no `2024-03-14` drīkst būt tikai atsevišķs non-common series.

Temperature minimum metrics:

- MAE;
- RMSE;
- bias;
- explicit sample size `n`.

Lead buckets:

- 0–6 h
- 6–12 h
- 12–24 h
- 24–48 h
- 2–3 d
- 3–5 d
- 5–7 d
- 7–10 d
- 10–15 d

Model-version periods paliek atsevišķi.

## Common-sample fairness

`common_sample_leaderboard` vispirms intersecto sample identity starp salīdzināmajiem provider vienā comparison mode un lead bucket, un tikai tad rēķina metric. Provider-only timestamps netiek izmantoti, lai mākslīgi uzlabotu ranking.

Comparison modes ir atsevišķi:

- `run_to_run` — līdzīgu initialization/run semantics salīdzinājums;
- `user_available` — tikai forecast, kas bija reāli pieejams attiecīgajā decision-time contract.

Šos režīmus nedrīkst poolot vienā leaderboard. `init_time`, `upstream_available_at_utc` un `retrieved_at_utc` jāglabā atsevišķi, lai user-available gate būtu auditējams.

Bootstrap MAE 95% CI tiek rādīts tikai pie `n >= 30`; mazākam sample uncertainty state paliek explicit, nevis tiek izdomāts confidence interval.

## Public ensembles

Open-Meteo Ensemble API public adapters:

- DWD ICON-D2-EPS;
- ECMWF IFS ENS 0.25°;
- ECMWF AIFS ENS 0.25°.

Parser saglabā control/member identity un member suffix konsekvenci starp variables. Individual-member historical retention ir īsa un source adapter ir bounded līdz trim `past_days`; vecāki member dati netiek fabricēti.

WeatherNext 2 ir tikai `legacy_ai_context`. Ja Open-Meteo surface nedod defensible exact-run init provenance, WN2 neiet strict run-to-run leaderboard un nekad neaizvieto WeatherNext 3.

## Genuine probabilistic verification

Probabilistic score drīkst saņemt tikai genuine ensemble/probability input.

Implemented primitives:

- ensemble CRPS;
- empirical member quantiles;
- central interval lower/upper, width un empirical coverage;
- interval score un WIS-style weighted interval score;
- precipitation event probability kā genuine member fraction;
- Brier Score;
- reliability bins.

Default precipitation occurrence candidate ir `>= 0.1 mm/h`. Probability tiek rēķināta kā member fraction, kas sasniedz slieksni. Deterministic precipitation amount un WeatherNext summary quantiles netiek pārvērstas probability.

## WeatherNext uncertainty

WeatherNext 3 summary distribution jāsaglabā kā `mean/p10/p25/p50/p75/p90` ar model version/init/retrieval/valid/lead provenance. Summary intervalam var vērtēt coverage/width, bet CRPS/Brier nedrīkst izlikties par full-ensemble score, ja genuine members/probability nav pieejami.

## Event verification

Temperature extreme, precipitation event un wind/gust event verification lieto tikai semantiski matched forecast/truth variable un explicit threshold/direction.

Event summary rāda:

- hits;
- misses;
- false alarms;
- correct negatives;
- hit rate;
- false-alarm ratio;
- critical success index.

10 m sustained wind un gust nekad netiek sajaukti kā viena quantity.

## Missing data

Missing observation vai forecast nav automātiski forecast error. Missing values netiek imputētas tikai metric aizpildīšanai. Member data, kas vairs nav pieejami retention dēļ, tiek atzīmēti kā unavailable, nevis rekonstruēti/fabricēti.

## Accuracy v3 UI

PWA Accuracy/Models skati atdala:

- deterministic providers;
- ensemble providers;
- WeatherNext 3 `primary_research`;
- WeatherNext 2 `legacy_ai_context`.

UI rāda lead bucket, `n`, sample-confidence state un genuine precipitation calibration atsevišķi. Production UI nekad nedrīkst izmantot izdomātus skill skaitļus.

## Combined forecast eligibility

Weighted Combined forecast paliek ārpus scope, kamēr nav pietiekams common-period corpus, stabila provenance, missing-data logic, metric tests un transparent versioned weighting/backtest contract.

## WeatherNext evolution report

Kad ir reāls corpus, periodiskais report rāda WeatherNext version, sample period, lead-time skill vs public baselines, change vs previous period, uncertainty calibration un notable misses. Release/model events tiek piesaistīti tikai verificētam provenance; nekas netiek fabricēts.
