# UI izskata plāns — veidojam šajā Codex sarunā

Statuss: **dizains vēl tiek veidots kopā ar Andri; nav apstiprināts integrācijai**.

Īpašnieka lēmums 2026-09-26: “UI izskatu nodali. veidosim šeit ar tevi, bet pārējo no Plus chat.”

Darbu uzskaite: [#237](https://github.com/rozkalnsandris/rozkalns_weather/issues/237). [Tehniskais ieviešanas plāns un atbildību matrica](IMPLEMENTATION_PLAN.md). [Vizuālais audita dokuments](report.html).

## Ko veidojam šeit

- Desktop un mobile kompozīciju: header, navigācija, hero, stundas/dienas, Model Snapshot, detail skati.
- Krāsu paleti, tipogrāfiju, atstarpes, radius, border/shadow, ikonas un fonu.
- Warning, pending, missing, loading un error stāvokļu vizuālo noformējumu, ievērojot tehniskajā plānā noteikto nozīmi.
- Models/Accuracy grafiku vizuālo hierarhiju un radar vadīklu izkārtojumu.
- Light/dark un 320/390/412/1440 px piemērus, ar reālistisku garu tekstu un tukšu/novecojušu datu situācijām.

## Secība šajā sarunā

1. Izvēlēties kopējo izskata virzienu uz Overview piemēra.
2. Izveidot desktop + mobile maketu un kopā precizēt vietu, hero, stundu/dienu un modeļu blokus.
3. Fiksēt kopīgos tokenus un atkārtojamos komponentus.
4. Attiecināt virzienu uz Models, Radar, Accuracy un Status.
5. Pārbaudīt pieejamību, kontrastu, tekstu ietilpību un visu stāvokļu dizainu.
6. Sagatavot konkrētu handoff Plus chat: pieņemtie maketi, tokeni, komponentu stāvokļi un atļautās implementācijas robežas.

Katrs posms ir plānots. Šis nodalījums neapstiprina agrāko audita koncepciju kā gala dizainu.

## Ko sagaidām no Plus chat

Funkcionējošus datu/stāvokļu līgumus un UI loģiku, saglabājot esošo izskatu līdz pieņemtam handoff. Vajadzīgās jaunās komponentes Plus chat apraksta ar datiem, interakcijām un accessibility prasībām. Svarīgi safety/a11y labojumi esošajā stilā drīkst notikt pirms redesign. Plus chat pats neizvēlas jaunu fontu, paleti, navigācijas kompozīciju vai karšu dizainu.

## Handoff pieņemšana

- [ ] Andris šajā sarunā izvēlējies vizuālo variantu.
- [ ] Ir desktop/mobile maketi un faili vai precīzas saites uz to versiju.
- [ ] Ir tokenu vērtības un komponentu stāvokļu specifikācija.
- [ ] DWD authority, provenance, WeatherNext pending un observation/forecast atšķirība dizainā saglabāta.
- [ ] Redzami missing/error/stale/active/clear scenāriji; krāsa nav vienīgā pazīme.
- [ ] Kontrasts un keyboard/focus prasības pārbaudītas.
- [ ] Plus chat nodota konkrēta pieņemtā versija; turpmākās vizuālās izmaiņas atgriežas šajā sarunā.

## Iepriekšējie priekšlikumi — sākuma materiāls apspriešanai

Zemāk saglabātā sākuma specifikācija ir priekšlikums. Tās izmēri, kompozīcija un tokeni nav vēl apstiprināti dizaina lēmumi.

### Mērķa UI un komponenti

**Overview secība:** vieta un atjauninājums → aktīvs DWD brīdinājums → pašreizējais novērojums → nākamās stundas → tuvākās dienas → Model Snapshot → papildu rādītāji. Ja brīdinājumu nav, kompakts DWD statusa bloks. Sarežģītās provenance detaļas atveras pēc pieprasījuma.

**Desktop:** apmēram 1200–1280 px satura maksimums; 12 kolonnu režģis, galvenais saturs 8 un sekundārā informācija 4 kolonnās, augšējā navigācija. **Mobile:** viena kolonna, piecas skaidri marķētas navigācijas saites; horizontāli ritināma tikai stundu josla, ne visa lapa. Pārejas punktu izvēlas pēc satura, pārbaudot arī 320 px.

| Komponents | Pienākums un robeža |
|---|---|
| `LocationHeader` | Lietotājam saprotams nosaukums, izvēle, timezone; tehniskais station ID detaļās. Vietas maiņa atceļ iepriekšējos pieprasījumus. |
| `WarningSummary` / `WarningList` | Viens DWD state model abos skatos; severity, area, issued/valid/checked, saite uz avotu. |
| `CurrentConditions` | Observation temperatūra un laiks; atsevišķi marķēta forecast condition/high-low; null nav 0. |
| `HourlyStrip` / `HourDetails` | Stundas laikapstākļi pirms provenance; tastatūras izvēle un mobilais scroll. |
| `DailyList` / `DayDetails` | Izvēršami rādītāji un izvēlētais provider; faktiskais horizonts, bez slepenas provider maiņas. |
| `ModelSnapshot` / `ModelChart` | Vienādam valid time salīdzinātas vērtības; pending WeatherNext; izskaidrots spread. |
| `RadarPlayer` | Karšu slānis, derīgs ģeogrāfiskais novietojums, kadru laiks, leģenda, play/pause, observed/nowcast robeža. |
| `AccuracySummary` | Readiness, periods, n, coverage, metric skaidrojums, common-sample salīdzinājums. |
| `SourceDetails` / `Status` | Pilnā provenance un tehniskā diagnostika; cilvēkam saprotami error/pending paskaidrojumi. |

Šie ir loģiski moduļu nosaukumi, nevis prasība izmantot konkrētu komponentu bibliotēku. Izstrādātājs piemeklē failu sadalījumu, saglabājot vienu renderētāju katram blokam.

**Dizaina tokenu sākuma specifikācija:** body 16 px; metadata 14 px; navigācija 12–13 px; line-height vismaz 1.4; spacing 4/8/12/16/24/32; divi konsekventi karšu radius līmeņi. Light/dark režīmā lietot semantiskus background/text/border/status tokenus un vienotu SVG ikonu komplektu. Ikona, teksts un forma papildina krāsu. 44 px ir mūsu praktiskais vadīklu mērķis; WCAG 2.2 AA 2.5.8 minimums ir 24 px ar izņēmumiem.

