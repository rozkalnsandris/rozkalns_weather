# Weather UI — ieviešanas plāns

Datums: 2026-09-26. Statuss: **plānots; šis dokuments neapliecina UI ieviešanu vai production izvietošanu**.

Mērķis: `weather.rozkalns.net` padarīt par ātri nolasāmu, modernu un praktisku laika apstākļu lietotni, saglabājot reproducējamu WeatherNext 3 / DWD / ECMWF salīdzinājumu.

Darbu uzskaite: https://github.com/rozkalnsandris/rozkalns_weather/issues/237. Pilns pamatojums: [28 punktu audits](REPORT.md). Vizuālais salīdzinājums un interaktīvā koncepcija: [web dokuments](report.html) — lejupielādēt un atvērt pārlūkā; GitHub HTML priekšskatījumu neizpilda. Koncepcijas laikapstākļi ir ilustratīvi, nevis reāli provider dati.

## Darbu sadalījums — īpašnieka lēmums 2026-09-26

**UI izskatu veidojam kopā ar Andri sākotnējā Codex sarunā. Pārējo tehnisko un funkcionālo ieviešanu turpinām Plus chat.** Šis sadalījums ir noteicošs pār agrāko S1–S6 posmu jaukto formulējumu.

- **Šeit / vizuālais darbs:** [UI_VISUAL_PLAN.md](UI_VISUAL_PLAN.md) — izkārtojums, informācijas vizuālā hierarhija, krāsas, fonti, atstarpes, kartes, ikonas, fonu/animācijas izvēle, mobile/desktop maketi un grafiku/radara vadīklu vizuālais noformējums. Dizaina varianti un to pieņemšana notiek šajā sarunā.
- **Plus chat / tehniskais darbs:** datu korektums, DWD warning lifecycle, API pieprasījumi, laiku salīdzināšana, provenance, interakciju loģika, lokāciju izvēle, i18n, semantiskā pieejamība, radar datu apstrāde, accuracy, PWA, moduļi un veiktspēja. Plus chat neveido patstāvīgu vizuālu pārbūvi.
- **Saskarne starp darbiem:** tehnisko loģiku var īstenot esošajā UI vai minimālā testu skatā, saglabājot esošo izskatu. Ja funkcijai vajadzīgs jauns komponents, Plus chat sagatavo datu/stāvokļu un pieejamības līgumu; izskatu izstrādājam šeit. Pieņemtā dizaina HTML/CSS integrāciju Plus chat var veikt pēc handoff, nemainot dizaina lēmumus.
- Drošības un pieejamības labojumi (piemēram, unknown nedrīkst būt zaļš clear, nepieciešams redzams focus) nav jāatliek līdz pilnam redesign; Plus chat veic minimālo korekto labojumu esošajā stilā un dokumentē izmaiņu.
- Vizuālā koncepcija auditā ir apspriešanas materiāls, ne jau apstiprināts dizaina uzdevums Plus chat. Nekāda automātiska sarunas nosūtīšana vai jauna uzdevuma aktivizēšana ar šo dokumentu nenotiek.

| Audita ID | Šeit: izskats | Plus chat: funkcija / dati |
|---|---|---|
| 01, 02, 04, 07 | Warning kartes gala noformējums | State model, automātiska ielāde, saturs, hidden regresija; minimālais safety fix |
| 03 | Radara kartes un vadīklu kompozīcija | Rastra ģeoreference/dekodēšana, player, laiks, observed/nowcast, lazy load |
| 05, 06, 08, 09, 10, 11 | Header/hero/hour/day/detail vizuālā hierarhija | Lokācija, observation/forecast, provenance, expand/select, missing/horizon |
| 12, 14, 15 | Grafiku/kartīšu izkārtojums un vizuālā valoda | Filtri, axes/units dati, keyboard/tabula, readiness/n/common sample |
| 13, 18, 19, 22, 23, 24, 25, 26, 28 | Tikai ja tehniskā prasība skar redzamo dizainu | Galvenā atbildība: matching, i18n, routes/focus, DST, loading, PWA, moduļi, docs, performance |
| 16, 17, 20, 21, 27 | Galvenā atbildība: fonts, fons, kontrasta palete, responsive kompozīcija, tokens | Mērījumi, a11y validācija un pieņemtā dizaina integrācija |

S1–S6 turpmāk apraksta produkta atkarības, ne vienas sarunas kopējo uzdevumu. Plus chat tehniskajam darbam **nav jāgaida viss S2 dizains**: S1 → tehniskie S2/S3 līgumi; S4/S5 pēc vajadzīgajiem datu līgumiem; S6 baseline un loading/PWA var sākt agrāk. Gala vizuālā integrācija un kopīgā pieņemšana seko pēc šeit pieņemtā dizaina handoff. 14–25 dienu vēsturiskais novērtējums aptvēra abus darba virzienus kopā; tas nav Plus chat tehniskā darba atsevišķs novērtējums.

## 1. Sākuma stāvoklis un jau paveiktais

Audita koda bāze: `d396b3dfdbc8680b7e28e7606096ae204746ee04`. Audita live ekrānattēlu atbilstība šim commit nav pierādīta. Plāna sagatavošanas laikā pārbaudītais `main`: `48dd2cd8967375ebf7b0f09880e37d78771c9d88`.

| Audita ID | Jaunāks pierādījums | Kā rīkoties ieviešanā |
|---|---|---|
| 07 — `[hidden]` | [PR #231](https://github.com/rozkalnsandris/rozkalns_weather/pull/231) pievieno `.hero-state[hidden]{display:none}` | Avota labojums jau ieviests. Pārbaudīt pārlūkā un saglabāt regresijas scenāriju; nedublēt patch. |
| 08 — avota dublēšanās | [PR #231](https://github.com/rozkalnsandris/rozkalns_weather/pull/231), [PR #235](https://github.com/rozkalnsandris/rozkalns_weather/pull/235) vienkāršo hero avotu un saglabā machine provenance | Daļēji atrisināts. Novērtēt atlikušās stāvokļu joslas un detaļu hierarhiju. |
| 24 — PWA resursi | #235 pievieno `provenance_v1.js`, kešs ir v10 | Daļēji atrisināts. Pārbaudīt visu faktisko script grafu, tostarp `runtime_badge.js` / `accuracy_v3.js`, un reālu offline startu. |
| 26 — dokumentācija | Atvērts [#236](https://github.com/rozkalnsandris/rozkalns_weather/issues/236) par continuation dokumentu konsekvenci | UI specifikāciju uzturēt šeit; nesākt otru paralēlu WeatherNext/controller sakārtošanu. Saskaņot kopīgos README/roadmap labojumus ar #236. |

Pārējie punkti ir audita novērojumi vai priekšlikumi, nevis jauna pilna `main` pārbaude. Pirms katra posma reproducēt attiecīgo problēmu uz tā brīža avota un pārlūka build. Source merge, production release un pārlūkā kešotais build ir atsevišķi stāvokļi.

Saglabājam [esošo apstiprināto UI virzienu](../../UI.md): piecas sadaļas, weather-first Overview un WeatherNext pirmās lapas Model Snapshot. Jaunā koncepcija precizē hierarhiju; tā pati par sevi nav pierādījums, ka sākotnējā #170 reference ir aizstāta.

## 2. Produkta un datu noteikumi

1. Publiskā sākuma lokācija ir `station_05480` / Werl. `station_10416` ir legacy/MOSMIX. Private home drīkst izmantot tikai jau konfigurētas un atļautas funkcijas ietvaros; publiskos dokumentos nav precīzu mājas koordinātu.
2. DWD ir oficiālo brīdinājumu avots. WeatherNext prognozes un modeļu atšķirības nedrīkst vizuāli kļūt par oficiāliem brīdinājumiem.
3. Novērojums un prognoze ir atsevišķi datu veidi. Temperatūras observation timestamp nedrīkst piedēvēt forecast condition. Katram skaitlim jāvar atvērt provider/model/init/valid/lead/retrieved/statistic/member/model-version provenance.
4. WeatherNext 3 paliek `primary_research` un redzams arī pending režīmā. Kvantiles, varbūtības, modeļa versijas un reāli dati netiek izdomāti. Private access #122/#224 nav priekšnoteikums publiskās UI uzlabošanai.
5. `mm` nav `%`. Starpmodelu min–max diapazons nav uzticamības intervāls vai lietus varbūtība. Weighted Combined paliek ārpus šā plāna.
6. Datu laiks ir UTC; attēlojums `Europe/Berlin`. Salīdzinām vienu lokāciju, quantity un valid timestamp; init/lead atšķirības ir redzamas. Nepilni dati paliek nepilni.
7. Saglabājam Python/FastAPI + SQLite un vieglu web/PWA. Framework migrācija nav nepieciešama šā plāna izpildei.

## 3. UI izskats — atsevišķs darbs šajā sarunā

Vizuālā specifikācija un iepriekšējās koncepcijas sākuma priekšlikumi pārcelti uz [UI_VISUAL_PLAN.md](UI_VISUAL_PLAN.md). Plus chat tos neuzskata par patstāvīgi īstenojamu redesign. Komponentu datu un uzvedības līgumi paliek tehniskās ieviešanas sastāvā.

## 4. Darbu secība un atkarības

| Posms | Rezultāts | Atkarība | Audita ID | Aptuvens apjoms |
|---|---|---|---|---|
| S1 | Godīgi dati, DWD stāvokļi un brīdinājumu kartes | Sākuma stāvokļa pārbaude | 01, 02, 04, 07, 13 | 2–4 dienas |
| S2 | Vienoti UI pamati, navigācija, valoda, specifikācija | S1 drošības semantika | 16, 18, 19, 20, 21, 26, 27 | 2–3 dienas |
| S3 | Praktisks Overview un detaļas | S1 + S2 | 05, 06, 08, 09, 10, 11, 17, 22 | 3–5 dienas |
| S4 | Reāls radar skatījums | S1 + S2 + radara datu formāta pārbaude | 03 | 3–5 dienas |
| S5 | Nolasāmi modeļi un accuracy | S1 time alignment + S2 | 12, 14, 15 | 2–4 dienas |
| S6 | Uzticama ielāde, PWA, moduļu sakārtojums un gala pārbaude | Ielādes darbus sākt agrāk; gala gate pēc S1–S5 | 23, 24, 25, 28 | 2–4 dienas |

Kopā **14–25 izstrādes dienas** vienam izstrādātājam, pieņemot lietojamus esošos API. Tas ir plānošanas diapazons, nevis termiņa solījums. Radara pārprojekcija/dekodēšana vai trūkstošs API līgums var prasīt papildu apjomu; to nosaka S4 sākuma izpēte. S4/S5 var veidot neatkarīgi pēc kopīgo līgumu nostiprināšanas. S6 veiktspējas baseline uzņem pirms UI pārbūves, lai būtu salīdzinājums.

### S1 — datu un brīdinājumu uzticamība

**Darbs:** `app.js`, `consumer_ui.js`, `weather_ui.js`, warning komponentu HTML/CSS un saistītie testu scenāriji. Pārbaudīt esošos API payload; neizdomāt backend laukus.

- [ ] Reproducēt 01/02 un pārbaudīt 07 labojumu no #231 uz aktuālā avota.
- [ ] Ieviest skaidru `unknown`, `loading`, `clear`, `active`, `stale`, `error` modeli. Saglabāt pēdējo zināmo aktīvo warning arī tad, ja jaunais fetch kļūdās, ar redzamu novecošanas norādi.
- [ ] `clear` atļaut tikai pēc sekmīgas, svaigas, derīgas atbildes par izvēlēto apgabalu. Tukšs/malformed payload nav automātiski “nav brīdinājumu”. Freshness slieksni definēt no faktiskā warning atjauninājumu līguma un dokumentēt; nevajag nepamatoti izvēlētu hardcoded TTL.
- [ ] Ielādēt DWD kopsavilkumu pie lapas atvēršanas, neatkarīgi no radar un health. Atgriežoties aktīvā cilnē, pārbaudīt vecumu; vienlaicīgus pieprasījumus nedublēt.
- [ ] Active warning virs hero; detaļās severity, area, derīgums, DWD authority. JSON paliek izvēles diagnostikā.
- [ ] Izveidot kopīgo modeļu matching helper: precīza lokācija + quantity/unit + valid timestamp; saglabāt katra init/lead/statistic. Ja laiki nesakrīt, rādīt “nav kopīga laika” vai izslēgt punktu ar iemeslu.

**Pieņemšana:** testu fixtures aptver visas 6 warning situācijas, expired-clear, pēdējo active + network error, 2 apgabalu ātru nomaiņu un modeļus ar dažādiem valid time. Zaļš statuss nav redzams unknown/error. #231 `[hidden]` darbojas vizuāli un accessibility tree. Darba rezultāts ir neliels avota PR ar ekrānattēliem, nevis datu corpus izmaiņa.

### S2 — dizaina, navigācijas un pieejamības pamati

**Darbs:** `app.css`, `index.html`, navigācijas/state loģika, neliela tekstu vārdnīca, `docs/UI.md`.

- [ ] Centralizēt type/spacing/color/radius tokenus un ieviest desktop režģi, saglabājot mobile struktūru.
- [ ] Vienoties par vienas valodas noklusējumu un LV/EN pārslēgšanu; šajā plānā ieteikums LV/EN, DE ir izvēles nākamais solis. `html lang` vienmēr atbilst redzamajam UI. Skaitļus/laikus formatēt ar Intl; provider nosaukumus netulkot.
- [ ] Navigācijai izmantot saites ar URL fragmentu vai route, `aria-current="page"`, Back/Forward un tiešās saites atjaunošanu. Pēc lietotāja pārejas fokuss sasniedz sadaļas virsrakstu; ir skip-link. Ja izvēlas tab modeli, pilnībā realizēt tab keyboard contract, nevis tikai pievienot ARIA atribūtus.
- [ ] Nodrošināt redzamu focus un vadīklu nosaukumus. Izmērīt īstās foreground/background kombinācijas arī gradientu galos, abās tēmās.
- [ ] Pārskatīt `docs/UI.md`: atdalīt implemented / planned / blocked; 05480 current benchmark, 10416 legacy, nav gatava Combined, kvantiles/probability tikai ar reāliem datiem. Continuation problēmas saskaņot ar #236.

**Pieņemšana:** 320/390/412 px un 1440 px nav visas lapas horizontāla scroll; navigācija, vieta un atjaunošana darbojas tikai ar tastatūru; 200% zoom nepazūd funkcijas; normāls teksts ≥4.5:1, liels teksts un nepieciešamie UI objekti ≥3:1 piemērojamajos gadījumos. Automātiska a11y pārbaude papildināta ar manuālo. Esošie grafiki var vēl gaidīt S5, bet kopējais shell ir lietojams.

### S3 — Overview kā ikdienas instruments

**Darbs:** Overview renderētāji, hourly/daily elementi un provenance detail panel; saglabāt #231/#235 labojumus.

- [ ] Header rāda “Werl”, laikjoslu un pieejamo lokāciju izvēli. Tehniskais station ID ir detaļās; nepieejama home opcija nav aktīva.
- [ ] Samazināt hero dekorāciju un tukšumu. Observation temperatūra, laiks un avots ir skaidri; forecast condition un max/min ir atsevišķi marķēti. Nav vienmēr saulaina fona mākoņainā/nakts situācijā.
- [ ] Viena īsa atjauninājuma/provenance rinda; degraded stāvokļi redzami, full provenance atveras detaļās. Atšķirt freshness no completeness/verification readiness.
- [ ] Stundas klikšķis rāda temperatūru, vēju, nokrišņu quantity un avotu; `MISSING_MODEL_VERSION` u.c. izskaidro tehniskajā sadaļā. Datu trūkums nebloķē pārējos derīgos rādītājus.
- [ ] Dienas ir reāli izvēršamas; provider switch nosaka faktisko horizontu, nav dekoratīvu chevron vai klusas datu apvienošanas. Min/max un nokrišņu rindas satilpst 320 px.
- [ ] Null rādītāji paskaidroti kā “avots nesniedz” / “nav ielādēts” / “novecojis”; nekad nepārvērst null uz nulli. Sekundāros tukšos rādītājus iespējams sakļaut.
- [ ] Timezone vienu reizi sadaļā; pilns UTC/offset detaļās. Rudens DST atkārtotajai stundai pievienot offset, lai abas 02:00 atšķirtos. Vecums atjaunojas arī bez jauna datu fetch.
- [ ] Pirmajā lapā saglabāt compact Model Snapshot, kur WeatherNext pending ir skaidri atšķirts no pieejamajiem modeļiem.

**Pieņemšana:** cilvēks 5 sekunžu uzdevumā var atrast vietu, temperatūru, svaigumu un DWD statusu; šis ir pārbaudāms mērķis, nevis jau izmērīts rezultāts. Hour/Day details strādā ar keyboard un touch. Testēt fresh/stale/partial/error un Europe/Berlin DST robežas. Datu izcelsme paliek pieejama visiem redzamajiem skaitļiem.

### S4 — radars

**Sākuma izpēte:** ar publisku/sanitizētu `/api/radar` piemēru noskaidrot encoding, izmērus, ģeoreferenci/projekciju, laika soli, nodata masku un precipitation mērvienības. `precipitation_5` nosaukums viens pats nepierāda konkrētu mērvienību. Sagatavot vienu statisku pareizi novietotu kadru pirms animācijas.

- [ ] Izvēlēties minimālo piemēroto renderer: esošais rastrs/overlay + viegla kartes bibliotēka, ja payload to pieļauj. Ja vajadzīga servera pārprojekcija/tiles, vispirms aprakstīt API izmaiņu un izmaksas atsevišķā source uzdevumā. Neizveidot jaunu maksas vai privātu servisu klusām.
- [ ] Publiskās references centra karte ar DWD slāņa attiecinājumu; home punktu nepublicēt. Saglabāt karšu piegādātāja attribution un pārbaudīt lietošanas/cache noteikumus.
- [ ] Slider, laika label, play/pause, iepriekšējais/nākamais kadrs, legend un nodata teksts. Playback apstājas, aizejot no skata; respektēt reduced-motion, neradīt bezgalīgu autoplay.
- [ ] Novērojumu un nowcast periodus atšķirt laika joslā un tekstā; nav maldinoša “tagad” novecojušam kadram.
- [ ] Ielādēt radar moduļus un lielos kadrus tikai vajadzības brīdī; bounded kadru kešs. Kļūda radarā nedrīkst bloķēt DWD warning.

**Pieņemšana:** zināma publiska punkta/rastra ģeogrāfiskā novietojuma pārbaude; kadra laiks un precipitation skala atbilst payload; fake fixture ir skaidri test data. Keyboard slider, mobile pan/zoom, tukšs/bojāts/novecojis kadrs, offline kļūda un observed/nowcast robeža pārbaudīti. Pārlūkā vairs nav tikai JSON sienas.

### S5 — modeļi un accuracy

- [ ] Models sākas ar grafiku un variable/horizon/provider filtriem. WeatherNext ir first-class; pending vai unavailable nerada fiktīvu līniju.
- [ ] Reizē salīdzināt vienādas quantities/units/valid times ar S1 helper. Dažādus init atklāt tooltip; snapshot diapazons ir starpmodelu izkliede, ne probabilistic uncertainty.
- [ ] Grafikiem X laiks, Y vienība, tekstuāla leģenda, krāsa + line pattern, keyboard/focus tooltip un tabulas alternatīva. Kvantiļu josla tikai no reālām attiecīgā provider kvantilēm; nepārnest vienu modeļu diapazonu uz citu.
- [ ] Accuracy pirmajā ekrānā rāda readiness, vērtēšanas periodu, lokāciju, n un coverage. MAE/bias u.c. paskaidrot vienā teikumā; lead buckets hronoloģiskā secībā.
- [ ] Ranking tikai salīdzināmam common sample un metodoloģijā definētai readiness. Fixed benchmark periodu nesaukt par “last 30 days”. Home bez truth avota nesaukt par measured home accuracy.
- [ ] Provenance/model-version un detalizētie quality gates paliek sasniedzami zem galvenā rezultāta.

**Pieņemšana:** fixtures par mixed units/times, provider missing, nepietiekamu n un pilnu common sample. Katras līnijas vērtības pārbaudāmas tabulā; nav nepamatota “best model” vai Brier no deterministic mm. Esošo verification aprēķinu rezultāti netiek mainīti tikai vizuālas pārbūves dēļ.

### S6 — ielāde, PWA un gala kvalitāte

- [ ] Pirms pārbūves saglabāt desktop/mobile veiktspējas baseline ar URL, commit/build, viewport, throttling, cache stāvokli un mērījuma laiku. Laboratorijas rezultāti nav CrUX lauka dati.
- [ ] Current/hourly/daily/warnings renderējas neatkarīgi. Health pieprasījums nav priekšnosacījums laikapstākļu parādīšanai. AbortController/timeout, stale response ignorēšana pēc vietas maiņas un kontrolēta atjaunošana.
- [ ] Saglabāt pēdējo derīgo saturu ar stale marķējumu; kļūda vienā provider neizdzēš pārējos. UI automātisks retry ir atsevišķs dokumentēts klienta darbības līgums, ne atļauja atkārtot operatora LIVE mutācijas.
- [ ] Sakārtot funkciju wrapping/MutationObserver/injected CSS pakāpeniski pie mainītajiem komponentiem. Viena state/render ownership; ES moduļi ar skaidrām import robežām. Nav vienā PR visu failu pārrakstīšanas.
- [ ] PWA kešā iekļaut visu reāli vajadzīgo app shell/import graph; salīdzināt ar faktiskajiem HTML scripts. Cache version/update UX novērš vecu HTML + jaunu JS sajaukumu. Radara kadrus un API datus nekašot neierobežoti.
- [ ] No tīra profila online install → aizvērt → offline reopen; pēc tam jaunās versijas update/activate. Ja API offline nav pieejams, to pasaka, nevis rāda svaigu statusu.
- [ ] Pabeigt zemāk minēto gala matrix, salīdzināt ar baseline un saglabāt pierādījumus PR.

**Pieņemšana:** lēns/hanging health neaptur current; 404/500/offline/timeout un ātra lokāciju maiņa neizraisa vecās vietas datu parādīšanu. Offline shell atveras ar visiem nepieciešamajiem moduļiem. Mērķi: LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1 lauka p75, kad pieejams pietiekams mērījums; līdz tam laboratorijas salīdzinājums un atklāts “field data nav”. Nepublicēt izdomātu Lighthouse punktu skaitu.

## 5. API līgumu pārbaude pirms komponentu būves

| Datu virsma | Pārbaudāmais līgums | UI uzvedība, ja trūkst |
|---|---|---|
| `/api/current` | observation time, avots, location, quantity/unit, null | Neitrāls unavailable; forecast nedrīkst kļūt par observation |
| `/api/hourly`, `/api/daily` | provider/model, init/valid/lead, unit/statistic, horizon, freshness | Daļējs provider skats ar skaidru iemeslu; nekāda slepena aizpildīšana |
| `/api/warnings` | area, DWD authority, issued/valid, severity, fetch/check time, error semantics | unknown/error/stale; nekad nepierādīts clear |
| `/api/radar` | rastra formāts, projection/bounds, unit, nodata, frame time, observed/nowcast | Teksts par datu nepieejamību, warning turpina darboties |
| `/api/verification/*` | periods, truth location, n/common-sample, metric, coverage/readiness, buckets/version | “Vēl nepietiek salīdzināmu datu”; nekāds uzvarētājs |
| `/api/health/providers` | ingest time pret observation/forecast valid time, error/freshness | Diagnostika papildina UI, nebloķē galveno saturu |

Tie ir nepieciešamie semantiskie līgumi, ne apgalvojums par pašreizējo JSON lauku nosaukumiem. Precīzos nosaukumus ņemt no aktuālās shēmas un testiem. Vajadzīgu backend izmaiņu aprakstīt ar fixture un backwards-compatible līgumu; corpus backfill/migrācija nav šīs UI piegādes automātiska daļa.

## 6. Pārbaudes un Definition of Done

| Joma | Minimālie scenāriji | Pierādījums |
|---|---|---|
| Responsive | 320, 390, 412×892, 1440×900; abas tēmas | Ekrānattēli, nav page overflow, salasāmi grafiki |
| Pieejamība | Tastatūra, fokusēšana, Back/Forward, 200% zoom, screen reader nosaukumi/states | Automātiska pārbaude + manuāla scenārija protokols; ne tikai score |
| Dati | fresh/stale/missing/error/pending, quantity atšķirības, provider failure | Mazi deterministiski fixtures un mērķēti testi |
| Brīdinājumi | 6 stāvokļi, expiry, active + error, vietas maiņa | State tests un screenshot; nav false-clear |
| Laiks | Europe/Berlin vasaras/ziemas pāreja, UTC joins, dažādi init/valid | Unikāli hour labels un precīza salīdzināšana |
| PWA | Clean install, offline restart, v10 → jaunā versija, cache eviction | Reāla pārlūka secība, ne vien string assert uz sw.js |
| Veiktspēja | Pirms/pēc ar vienādiem apstākļiem, lēns radar/health, cold/warm cache | Saglabāti mērījumi un atšķirtas lab/field robežas |
| Datu godīgums | Visible value → source details, WeatherNext pending, home bez truth | Provenance pārbaude; nav fabricated metrics |

Katram ieviešanas PR: sasaistīts posms + audita ID; before/after pierādījums; atbilstošie behavior testi; pieejamības pārbaude mainītajam UI; current CI; norādīts, kas paliek blocked/planned. Neveidot testus, kas tikai atkārto CSS tekstu, ja kļūda ir renderētā uzvedībā. Esošos source contract testus saglabāt, bet tie neaizstāj pārlūka scenārijus.

RPi5-hosted pixel verification gadījumā ievērot `.github/start-mode-routing.json` un svaigi nolasīt `RPi5_main/docs/VISUAL_VERIFICATION.md`; runtime rīku izmantošana prasa attiecīgo authority. Lokālie/sanitizētie preview pierādījumi jāmarķē kā tādi. UI apstiprinājums nav production rollout apstiprinājums.

## 7. Kā vadīt ieviešanu GitHub

1. Šis plāns un audits ienāk atsevišķā dokumentācijas PR. Darbu uzskaites issue paliek atvērts līdz S1–S6 pieņemšanai; dokumentācijas PR to neaizver.
2. Sākt ar S1. Pirms katra posma svaigi nolasīt `AGENTS.md`, aktuālo `main`, controller #9 un jau esošos atbilstošos PR/issues; dublikātus neveidot. Šis plāns nepārraksta controller režīmu un nerada AUTO-RUN FULL authority.
3. Posmu sadalīt mazos, vienam rezultātam atbilstošos source PR. Piemēram, S1-a warning lifecycle, S1-b time alignment; S4-a static raster proof, S4-b player. Katram ir konkrēts DoD no šā dokumenta.
4. FAST darbs var sagatavot source/docs/tests un PR. Merge ievēro repo exact owner gate; īstenošanas AUTO-RUN FULL jāaktivizē ar aktuālā kontrakta explicit issue-scoped komandu. Neizmantot vecus authorization receipts.
5. Pēc atļautas piegādes pārbaudīt precīzo build un atjaunot tracking checkbox ar PR/pierādījuma saiti. Source-complete un live-verified atzīmēt atsevišķi.
6. Parastais atļautais release izmanto esošo SIMPLE-DEPLOY ceļu. Šajā plānā netiek mainīti workflows, credentials, RPi5, Cloudflare, production DB vai private WeatherNext piekļuve. Pēc mutation kļūdas/neskaidrības ievērot repo STOP noteikumu.

## 8. Piemēru salīdzinājums un pārņemamie principi

| Avots | Ko pārņemt | Pielāgojums šim projektam | Posms |
|---|---|---|---|
| [Yr — Werl](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl) | Vietas, stundu un dienu ātra nolasāmība | Saglabāt observation/forecast izcelsmi un pirmās lapas Model Snapshot | S2, S3 |
| [meteoblue](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425) | Blīva, bet strukturēta prognožu un modeļu informācija | Provider/init/valid un pending WeatherNext paliek skaidri; neveidot fiktīvu consensus | S3, S5 |
| [Windy](https://www.windy.com/) | Karte kā galvenais interaktīvais saturs, slānis un laika vadība | Mazāks DWD radar player ar vienu skaidru uzdevumu, lazy load | S4 |
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Kontrasts, fokusēšana, reflow, nosaukumi un target size | AA kritērijus pārbaudīt faktiskajā renderā; 44 px ir produkta mērķis | S2, S6 |
| [Core Web Vitals](https://web.dev/articles/vitals) | Lietotāja uztvertās ielādes, reakcijas un stabilitātes mērījumi | Baseline pirms/ pēc, bez fiktīviem performance score | S6 |

Pilnie katra no 28 uzlabojumiem pierādījumi, koda saites, piemērs un pieņemšanas kritērijs ir [REPORT.md](REPORT.md); ekrānattēlu salīdzinājums ir [report.html](report.html).

## 9. Pilna audita pārklājuma matrica

| ID | Prioritāte | Uzlabojums | Posms | Statuss plāna izveidē |
|---|---|---|---|---|
| 01 | P0 | Brīdinājuma krāsa nedrīkst apsolīt drošību | S1 | Plānots; pirms ieviešanas reproducēt |
| 02 | P1 | DWD statusu pārbaudīt automātiski | S1 | Plānots; pirms ieviešanas reproducēt |
| 03 | P1 | “Radar” pārvērst īstā lietojamā kartē | S4 | Plānots; pirms ieviešanas reproducēt |
| 04 | P1 | Brīdinājumus lasīt kā ziņu, nevis API atbildi | S1 | Plānots; pirms ieviešanas reproducēt |
| 05 | P1 | Vietas nosaukumu padarīt cilvēkam saprotamu | S3 | Plānots; pirms ieviešanas reproducēt |
| 06 | P1 | Kompaktāks galvenais laikapstākļu bloks | S3 | Plānots; pirms ieviešanas reproducēt |
| 07 | P1 | Izlabot hidden un CSS konfliktu | S1 | Avota labojums #231; pārbaudīt regresiju |
| 08 | P1 | Datu izcelsmi saglabāt, bet mazināt atkārtojumus | S3 | Daļēji #231/#235; atlikusī hierarhija |
| 09 | P1 | Stundu kartītei vajag laikapstākļu detaļas | S3 | Plānots; pirms ieviešanas reproducēt |
| 10 | P2 | Dienu prognozei dot izvērsumu un skaidru horizontu | S3 | Plānots; pirms ieviešanas reproducēt |
| 11 | P2 | Tukšām metrikām jāpasaka iemesls | S3 | Plānots; pirms ieviešanas reproducēt |
| 12 | P1 | Modeļu lapā salīdzinājumu likt vispirms | S5 | Plānots; pirms ieviešanas reproducēt |
| 13 | P1 | Modeļu izkliedi aprēķināt vienā un tajā pašā laikā | S1 | Plānots; pirms ieviešanas reproducēt |
| 14 | P1 | Grafikiem vajag asis un pieejamu alternatīvu | S5 | Plānots; pirms ieviešanas reproducēt |
| 15 | P1 | Precizitāti sākt ar interpretējamu kopsavilkumu | S5 | Plānots; pirms ieviešanas reproducēt |
| 16 | P1 | Palielināt tekstus, kurus patiešām jālasa | S2 | Plānots; pirms ieviešanas reproducēt |
| 17 | P2 | Dekorāciju pieskaņot nozīmei | S3 | Plānots; pirms ieviešanas reproducēt |
| 18 | P1 | Saskaņot lapas valodu un terminoloģiju | S2 | Plānots; pirms ieviešanas reproducēt |
| 19 | P1 | Navigācijai vajag stāvokli, URL un fokusu | S2 | Plānots; pirms ieviešanas reproducēt |
| 20 | P2 | Kontrasts jāpārbauda uz faktiskajiem foniem | S2 | Plānots; pirms ieviešanas reproducēt |
| 21 | P2 | Desktop izkārtojumam izmantot pieejamo platumu | S2 | Plānots; pirms ieviešanas reproducēt |
| 22 | P2 | Laika zonu norādīt vienreiz saprotamā vietā | S3 | Plānots; pirms ieviešanas reproducēt |
| 23 | P1 | Ielādi neatkarīgos blokus neatkarīgi | S6 | Plānots; pirms ieviešanas reproducēt |
| 24 | P1 | PWA bezsaistes apvalks ir nepilnīgs | S6 | Daļēji #235; atlikušais shell/offline |
| 25 | P2 | UI slāņus padarīt vienkāršāk uzturamus | S6 | Plānots; pirms ieviešanas reproducēt |
| 26 | P2 | Saskaņot dizaina dokumentāciju ar pašreizējiem principiem | S2 | UI spec; continuation saskaņot ar #236 |
| 27 | P2 | Vienota komponentu un dizaina tokenu sistēma | S2 | Plānots; pirms ieviešanas reproducēt |
| 28 | P2 | Veiktspēju un PWA mērīt pirms pārbūves | S6 | Plānots; pirms ieviešanas reproducēt |

## 10. Darbi ārpus šā plāna

Weighted Combined, jauni AQI/pollen dati, push notifications, privātās mājas aktivizēšana, WeatherNext private access/collection, production corpus izmaiņas un framework pārrakstīšana nav nepieciešami šīs UI pieņemšanai. Tos uzsāk tikai kā atsevišķus, skaidri definētus darbus. Šis ir UI/UX ieviešanas plāns; tas nav pilns security vai WCAG sertifikācijas audits.
