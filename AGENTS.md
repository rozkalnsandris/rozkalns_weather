# AGENTS.md

## Source of truth

GitHub ir projekta canonical source of truth. Pirms darba vienmēr nolasi šo failu, aktuālo README/docs, current `main`, aktīvo issue/PR un tikai attiecīgajam work item nepieciešamo CI/review stāvokli.

## Project intent

Šis ir privātām mājas vajadzībām paredzēts weather dashboard/verification projekts. Galvenais pētniecības objekts ir **Google WeatherNext 3**, salīdzināts ar DWD un ECMWF avotiem konkrētam mājas punktam Dortmund-Wickede apkārtnē.

## WeatherNext 3 priority

- WeatherNext 3 jābūt first-class provider, nevis dekoratīvam papildinājumam.
- Saglabā raw provider metadata: model version, init time, forecast valid time, lead time, retrieval time, statistic/member information.
- Nedrīkst pārrakstīt vai izlīdzināt WeatherNext vērtības tā, ka vairs nevar veikt reproducējamu salīdzinājumu ar citiem modeļiem.
- Combined forecast nedrīkst slēpt provider-level prognozes.
- WeatherNext accuracy jāvērtē ar atsevišķiem verifikācijas rādītājiem un lead-time buckets.

## Safety / authority

- WeatherNext ir eksperimentāla forecast sistēma, nevis oficiāls warning source.
- DWD CAP/oficiālie DWD brīdinājumi ir autoritatīvi severe-weather warnings Vācijā.
- UI nedrīkst prezentēt AI model output kā oficiālu brīdinājumu.

## Privacy

- Precīzu mājas adresi, `HOME_LAT`, `HOME_LON`, API credentials, Cloudflare credentials un citus privātus runtime parametrus necommitot.
- Repo pašreizējā redzamība jāpārbauda pirms jebkādu lokācijas detaļu pievienošanas.
- `.env` nedrīkst commitot; tikai `.env.example` ar tukšiem placeholderiem.

## GitHub workflow

- Pirms GitHub write nosaki precīzu repo, branch/target un darbību.
- `turpini` autorizē safe/read-only/source-level darbu līdz nākamajam Ready/STOP punktam; tas neautorizē merge/deploy/runtime mutation.
- Merge prasa atsevišķu skaidru lietotāja autorizāciju.
- Production/host/DB mutation, deploy, restart, secrets, permissions vai repository settings izmaiņas prasa atsevišķu skaidru autorizāciju.
- Pēc pirmās autorizētās mutation kļūdas vai būtiskas neskaidrības saglabā evidence un STOP; neveic automātisku alternate mutation path.

## Implementation principles

- Sāc ar minimum-sufficient architecture: Python/FastAPI + SQLite + viegls web/PWA.
- Provider adapters saglabā atsevišķi no normalization/verification slāņa.
- Saglabā gan forecast snapshot, gan observation truth data; nepārraksti vēsturiskos snapshotus ar jaunāku run.
- Laiki datu slānī glabā UTC; UI attēlo `Europe/Berlin`.
- Vienības normalizē uz SI/meteoroloģiski skaidru formu (`°C`, `mm`, `m/s` vai konsekventi izvēlēts display `km/h`, `hPa`).
- Katram datu punktam saglabā provenance.
- Provider failure nedrīkst izraisīt citas prognozes pazaudēšanu; UI rāda freshness/status.

## Out of scope until explicitly added

- Publisks weather service.
- Komerciāla izplatīšana.
- Automātiski severe-weather lēmumi tikai no WeatherNext.
- Sarežģīts ML ensemble weighting pirms pietiekama lokāla verification corpus.
