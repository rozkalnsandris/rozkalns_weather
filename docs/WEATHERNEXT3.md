# WeatherNext 3

> **Project focus:** WeatherNext 3 ir šī projekta galvenais pētniecības objekts. Viss verification dizains jāveido tā, lai pēc mēnešiem varētu atbildēt ne tikai “kāda bija prognoze?”, bet “cik labs WeatherNext 3 bija salīdzinājumā ar citiem modeļiem konkrētā lead time un konkrētā lokācijā?”.

## Kāpēc tas ir interesants

Google WeatherNext 3 ir globāla AI weather forecasting sistēma ar live geostationary satellite input, hourly initialization un probabilistisku 64-member ensemble.

Aktuālā Google dokumentācija (2026-09):

- release: WeatherNext 3 v3.0, 2026. gada augusts;
- coverage: global;
- initialization: katru stundu;
- timestep: 1 h;
- 6-hourly synoptic runs (`00/06/12/18 UTC`): līdz 360 h / 15 dienām;
- interim hourly runs: līdz 48 h;
- ensemble: 64 members;
- surface grid: līdz ~0.1° (~10 km);
- station-oriented output: līdz ~0.05° (~5 km);
- operational forecast access: BigQuery, Earth Engine, Google Cloud Storage/Zarr.

Google pats to klasificē kā automated/experimental forecast system. Tas nav oficiāls severe-weather warning source.

## Kāpēc tas projektā nav “vēl viena līnija grafikā”

WeatherNext 3 dēļ jāsaglabā vairāk metadatu nekā parastai weather app:

```text
provider                weathernext3
model_version           3.x / source metadata
init_time_utc            model initialization
retrieved_at_utc         when we obtained it
valid_time_utc           forecast target time
lead_hours               valid - init
variable                 temperature_2m / precipitation / ...
statistic                mean / p10 / p25 / p50 / p75 / p90
value                    normalized value
native_value/unit        optional raw representation
source_surface           BigQuery / GCS / Earth Engine
```

Mērķis ir saglabāt katru forecast run kā immutable snapshot, nevis tikai pēdējo prognozi.

## Piekļuve

Real-time operational datasets ir allowlist režīmā. Google Quick Start norāda:

- jāiesniedz WeatherNext Data Request;
- tipisks review laiks: 5–7 darba dienas;
- nav obligāts jau esošs paid Google Cloud līgums;
- viena allowlist pieeja dod piekļuvi BigQuery, Earth Engine un GCS.

MVP izvēle: **BigQuery**.

Pamatojums:

- point lookup ar BigQuery GIS;
- precomputed ensemble statistics;
- nav jālejupielādē pilns globālais Zarr;
- vienai mājas lokācijai ir vienkāršāks ingestion ceļš.

Pirmās piekļuves source contract ir `deploy/weathernext-first-access.json` un `docs/WEATHERNEXT_FIRST_ACCESS.md`. Tas gatavo drošu linked-dataset/schema/dry-run/canary/provenance plūsmu, bet source merge pats nedod Google Cloud, BigQuery vai production SQLite authority.

Sustained collection source contract ir `deploy/weathernext-sustained-collection.json` un `docs/WEATHERNEXT_SUSTAINED_COLLECTION.md`. Tas sākas tikai pēc validēta first-access canary/snapshot admission un definē deterministic cadence, dedupe, missing-run ledger/recovery, model/schema boundaries, freshness health un first-month verification readiness. Tas pats neveic nevienu real BigQuery query, production SQLite write vai scheduler activation.

Version-evolution source contract ir `deploy/weathernext-version-evolution.json` un `docs/WEATHERNEXT_VERSION_EVOLUTION.md`. Tas sagatavo verificētas WeatherNext 3 model/schema boundary salīdzinājumu ar deterministic before/after windows, strict `station_10416` common samples, skill/quantile/freshness deltas, deterministic notable cases un privacy-safe report payload. Source merge pats nelasa production corpus un neapgalvo, ka reāls version boundary ir jau novērots lokāli.

## BigQuery query discipline

Google iesaka:

- vienmēr filtrēt pēc `init_time`, jo tabulas ir partitioned;
- atlasīt tikai nepieciešamās kolonnas, nevis `SELECT *`;
- point/spatial selection izmantot BigQuery GIS (`ST_INTERSECTS`, `ST_DWITHIN` u.c.).

Mūsu first-access contract papildus prasa BigQuery dry-run pirms bounded canary query un explicit `maximum_bytes_billed` limitu katram 0.05°/0.1° query. Pirmais canary izmanto reproducējamo `station_10416` benchmark punktu, vienu init un ne vairāk kā 24 forecast stundas. Private home point paliek vēlākai runtime-only aktivācijai.

Mūsu adapterim privātam home režīmam jāsaņem precīzs home point tikai no runtime config un jāizvēlas atbilstošais WeatherNext spatial element.

## Ensemble statistics

BigQuery/Earth Engine/GCS statistics produkti nodrošina precomputed summary statistics, tostarp:

- `mean`
- `p10`
- `p25`
- `p50`
- `p75`
- `p90`

UI sākotnēji rāda vismaz:

- mean vai p50;
- p10–p90 uncertainty band;
- init time;
- data age/freshness.

Verification slānis vērtē gan point forecast accuracy, gan interval/reliability kvalitāti.

## Data latency ir svarīga

Hourly initialization nenozīmē, ka consumer dataset ir pieejams uzreiz.

Google target dissemination BigQuery/Earth Engine 15-day synoptic runs:

| Init UTC | Horizon | Target availability BQ/EE |
|---|---:|---:|
| 00:00 | 360 h | ~08:10 UTC |
| 06:00 | 360 h | ~14:10 UTC |
| 12:00 | 360 h | ~20:10 UTC |
| 18:00 | 360 h | ~02:10 UTC next day |

Interim hourly runs BigQuery/Earth Engine target ir aptuveni `init + 7h25m`.

Šie ir **target dissemination** laiki, nevis provider-observed publication timestamps. Source tos saglabā kā `expected_available_at_utc`; `upstream_available_at_utc` paliek `null`, kamēr upstream nav devis defensible novērotu availability/publication evidence. Retrieval laiks nekad netiek izmantots kā publication aizvietotājs.

Sekas:

- WeatherNext 3 nevar automātiski uzskatīt par “svaigāko nowcast” tikai tāpēc, ka tas initialized hourly;
- UI obligāti rāda init/freshness;
- 0–6 h situācijās DWD radar/ICON-D2 var būt praktiski svarīgāki;
- modelu salīdzinājumā jāizmanto forecast, kas reāli bija pieejams lēmuma brīdī, nevis vēlāk publicēts run;
- latency fallback drīkst mēģināt agrāku target-disseminated run tikai genuine `data_latency` gadījumā; permission/link/schema/cost kļūdas nedrīkst maskēt kā latency.

Sustained collection ledger šos stāvokļus tur explicit kā `expected`, `target_disseminated`, `retrieved`, `missing`, `delayed` un `superseded`. Bounded recovery source plāns drīkst atlasīt tikai jau missing init ierobežotā logā; real recovery query un corpus write paliek atsevišķi owner gates.

## Resolution

Google publicē vairākus WeatherNext 3 produktus:

- ~0.1° gridded surface;
- ~0.05° station-oriented surface product;
- ~0.25° pressure-level fields GCS full ensemble kontekstā.

Implementācijas laikā nedrīkst pieņemt, ka visi mainīgie ir pieejami visās resolution/product kombinācijās. Adapterim jābalstās uz aktuālo Google schema un jātestē konkrētās kolonnas pirms provider tiek uzskatīts par Ready. First-access schema fingerprint attiecas tikai uz WeatherNext 3 expected field paths; WeatherNext 2/Gen/Graph netiek klusi pieņemti kā aizvietotāji.

## Precipitation

WeatherNext 3 dokumentācija norāda 1-hour precipitation output, nevis vecāko WeatherNext paaudžu 6-hour accumulation konvenciju. Mūsu normalization jāglabā accumulation window metadata, lai nepieļautu kļūdainu salīdzinājumu ar DWD/ECMWF.

Summary kvantiles `p10/p25/p50/p75/p90` drīkst izmantot empirical interval coverage/width un p50 error verifikācijai, bet tās **nedrīkst** pārvērst precipitation event probability. Brier/reliability vai full-ensemble CRPS WeatherNext 3 tiek atļauti tikai tad, ja vēlāk ir defensible genuine probability/member source.

## Licensing / privāts projekts

Google nošķir:

- real-time/future data — governed by GDM Real-Time Weather Forecasting Experimental Data Terms;
- historical data (time at least 1 h in the past) — CC BY 4.0.

Šis projekts sākotnēji ir privāts un nav paredzēts publiskai WeatherNext datu redistribūcijai. Pirms jebkādas publiskošanas terms jāpārbauda no jauna. First-month sanitized evidence contract tāpēc defaultā tur `publication_allowed=false` un `terms_recheck_required_before_publication=true`.

## Benchmarking princips

Google publicētie globālie benchmarki nav pietiekams pierādījums mūsu lokācijai.

Mēs vērtējam lokāli:

- temperature MAE/RMSE/bias;
- dew point/humidity, ja pieejams salīdzināms truth;
- precipitation occurrence Brier score / reliability;
- precipitation amount error;
- wind speed/gust error;
- lead-time buckets;
- day/night;
- season;
- convective vs stratiform/rainy events, kad datu apjoms to atļauj.

Pirmā mēneša WeatherNext measured eligibility ir stingri `station_10416` + DWD WMO 10416 truth, tikai explicit common valid-times, atsevišķi pa `model_version` un lead bucket. MAE/RMSE/bias tiek saukti par meaningful tikai slice ar `n >= 30`; private `home` šajā measured station accuracy netiek iekļauts.

Salīdzinājuma provider minimum:

1. WeatherNext 3;
2. DWD ICON-D2;
3. DWD MOSMIX-L;
4. ECMWF IFS HRES;
5. ECMWF AIFS.

## Model evolution tracking

Saglabājam model version/provider metadata. Ja Google maina WeatherNext versiju vai dataset schema:

- neapvienot veco un jauno periodu vienā aggregate metric bez version dimension;
- accuracy dashboard rādīt `model_version` split;
- pierakstīt migration/change date;
- regression/improvement analīzē izmantot salīdzināmu periodu.

Sustained collection contract model version un schema fingerprint tur kā atsevišķus collection dimensions. Jebkura neatbilstība rada `version_boundary`; current source atbalsts ir `3.0.0`, un unknown future version neprasa automātisku coercion — tas prasa explicit adapter/version lēmumu.

Version-evolution contract šo boundary analizē tikai tad, ja release/model metadata ir verificēta un before/after versijas ir explicit. Comparison windows tiek izvēlēti pēc fiksēta kalendāra ap boundary, nevis pēc forecast rezultātiem. Measured skill intersecto tikai semantiski identiskus `station_10416` samples un saglabā `n` katrai pusei + common `n`; lead bucket un run class netiek pooloti. Report rāda absolūtos/relatīvos MAE/RMSE/bias deltas, summary-quantile calibration un freshness/latency izmaiņas, bet neizdod globālu “winner”. Reāls report pret production corpus prasa atsevišķu read-only owner gate.

## Official references

- https://developers.google.com/weathernext/guides/models
- https://developers.google.com/weathernext/guides/access-forecast
- https://developers.google.com/weathernext/guides/bigquery
- https://developers.google.com/weathernext/guides/dissemination
- https://developers.google.com/weathernext/guides/disclaimers
- https://developers.google.com/weathernext/release-notes
