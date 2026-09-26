# Rozkalns Weather — web UI audits

> **Vēsturiska audita momentuzņēmums.** Šis audits balstīts uz `d396b3d`; jaunākajā pārbaudītajā `main` (`48dd2cd`, 2026-09-26) PR #231/#235 jau labo 07 un daļēji 08/24. Pirms ieviešanas izmantot [aktuālo darbu plānu](IMPLEMENTATION_PLAN.md), nevis automātiski uzskatīt visus 28 punktus par neatrisinātiem. Live build atbilstība avota SHA nav pārbaudīta.


Datums: 26.09.2026.

Auditētais GitHub commit: `d396b3dfdbc8680b7e28e7606096ae204746ee04`. Produkcijas build atbilstība commit nav verificēta.

## Galvenais secinājums

Saglabāt datu godīgumu un WeatherNext pētniecisko mērķi; pārveidot informācijas hierarhiju, brīdinājumu stāvokļus, radaru un grafiku lietojamību. Web dokumentā ir ekrānattēli, filtri, koncepcija un pieņemšanas plāns.

## Robežas

Pārbaudīti pieci live skati un GitHub frontend kods. 390 un 320 px responsive pārbaude. Nav Lighthouse/CrUX mērījumu, pilna WCAG/ekrānlasītāja/zoom audita, offline restartēšanas vai penetrācijas testa.

## Visi ieteikumi

### 01. [P0] Brīdinājuma krāsa nedrīkst apsolīt drošību
Joma: Uzticamība · Pierādījums: Novērots + kods · Apjoms: M

**Pašlaik:** Sākotnējais Overview rāda “Official warning status not loaded”, taču bloks ir zaļš ar ķeksīti. updateOverviewWarning maina tekstu, nevis vizuālo stāvokli; tā pati zaļā noformējuma bāze paliek arī kļūdai vai aktīvam brīdinājumam. Aktīva brīdinājuma scenārijs dzīvajā sesijā netika saņemts.

**Risinājums:** Ieviest atsevišķus unknown, loading, clear, active, stale un error stāvokļus. Nezināms statuss — neitrāls “DWD statuss vēl nav pārbaudīts”. Zaļš tikai pēc svaigas DWD atbildes bez aktīviem brīdinājumiem. Aktīvu brīdinājumu pacelt virs temperatūras, norādot līmeni, vietu un derīguma periodu.

**Gatavs, kad:** Katram no 6 stāvokļiem atšķirīgs teksts un ikona; krāsa nav vienīgais signāls. Svaigs “nav brīdinājumu” izbeidzas pēc definēta derīguma termiņa. Offline nekad neatstāj “aktuāli”.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.js#L685) · [Piemērs / standarts](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl)

### 02. [P1] DWD statusu pārbaudīt automātiski
Joma: Uzticamība · Pierādījums: Novērots + kods · Apjoms: S–M

**Pašlaik:** Overview brīdinājums sākumā nav ielādēts. Radar sadaļā ir atsevišķa poga “Load current DWD warnings”; sākuma refresh() šo pieprasījumu neveic.

**Risinājums:** Automātiski ielādēt nelielu DWD kopsavilkumu neatkarīgi no pārējās prognozes. Poga kļūst par “Atjaunot”. Atgriežoties lapā, pārbaudīt statusa vecumu; parādīt pārbaudes laiku.

**Gatavs, kad:** Pēc lapas atvēršanas lietotājs bez klikšķa redz aktuālu rezultātu vai saprotamu kļūdu. Lēns radars nebloķē brīdinājumu.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.js#L585) · [Piemērs / standarts](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl)

### 03. [P1] “Radar” pārvērst īstā lietojamā kartē
Joma: Radars · Pierādījums: Novērots + kods · Apjoms: L

**Pašlaik:** Pēc “Load radar metadata” redzams garš JSON ar frames un precipitation_5 datiem. Karte, atskaņošana un laika slīdnis šajā skatā nav pieejami.

**Risinājums:** Rādīt publiskās references apkaimes karti, nokrišņu slāni, leģendu ar mērvienību, kadra laiku, atskaņot/pauzēt un laika slīdni. Novērojumus un nowcast skaidri nodalīt; nepublicēt privātās mājas koordinātas. JSON atstāt izvēršamās tehniskās detaļās.

**Gatavs, kad:** Var izvēlēties kadru ar peli un tastatūru; redzams pēdējā novērojuma laiks un nowcast sākums. Tukši, veci un kļūdaini kadri saņem savu stāvokli. Kartes izstrādei vispirms jāapstiprina datu dekodēšanas/ģeometrijas līgums.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.js#L701) · [Piemērs / standarts](https://www.windy.com/)

### 04. [P1] Brīdinājumus lasīt kā ziņu, nevis API atbildi
Joma: Radars · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** DWD sekmīgs rezultāts ir JSON ar no_active_alerts; lietotājam jāinterpretē atslēgas. Virs tā atkārtojas divi līdzīgi skaidrojumi par publisko references punktu.

**Risinājums:** Izveidot WarningCard: DWD nosaukums, bīstamības līmenis, notikums, apgabals, sākums/beigas, oficiālais apraksts un avota saite. Bez aktīviem brīdinājumiem — viena īsa rinda ar vietu un pārbaudes laiku.

**Gatavs, kad:** Dati nav jālasa JSON formā; visi aktīvie brīdinājumi ir atverami. DWD teksts un autoritāte paliek atšķirti no modeļu secinājumiem.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/index.html#L119) · [Piemērs / standarts](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl)

### 05. [P1] Vietas nosaukumu padarīt cilvēkam saprotamu
Joma: Pārskats · Pierādījums: Novērots · Apjoms: S–M

**Pašlaik:** Galvenais virsraksts ir “DWD CDC Werl 05480 · reference”. Vietas izvēle atrodas Status sadaļā, lai gan ietekmē prognozi.

**Risinājums:** Virsraksts “Werl”, zem tā “Publiskā references stacija · DWD 05480”. Atlasīto vietu rādīt visu skatu galvenē; mazu vietas izvēlni novietot turpat. “Mājas” piedāvāt tikai tad, ja konfigurētas. Werl nepārsaukt par izmērītiem laikapstākļiem mājās.

**Gatavs, kad:** Visos skatos skaidrs, par kuru vietu ir dati. Precizitāte paliek piesaistīta stacijas novērojumiem. Neviena privāta adrese vai precīzas koordinātas neparādās publiskā UI.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/index.html#L171) · [Piemērs / standarts](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl)

### 06. [P1] Kompaktāks galvenais laikapstākļu bloks
Joma: Pārskats · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** 390×844 skatā hero aizņem aptuveni 360 px. Avots atkārtojas vairākās rindās, bet vējš un praktiskā dienas aina atrodas zemāk. Temperatūra ir no novērojuma, mākoņainības teksts — no ICON-D2 prognozes.

**Risinājums:** Saglabāt lielu temperatūru, bet vienā rindā skaidri norādīt “DWD novērojums · 10:50”. Prognozes mākoņainību un šodienas min/max grupēt zem “Prognoze · ICON-D2”. Pievienot īsu, no datiem iegūtu dienas kopsavilkumu. Sajūtu temperatūru rādīt tikai ar derīgu avotu/aprēķinu.

**Gatavs, kad:** 390×844 pirmajā ekrānā redzama vieta, stāvoklis, temperatūra, brīdinājuma statuss un stundu sākums; nav jāsajauc novērota temperatūra ar prognozētu stāvokli.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/consumer_ui.js#L188) · [Piemērs / standarts](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl)

### 07. [P1] Izlabot hidden un CSS konfliktu
Joma: Pārskats · Pierādījums: Novērots + DOM · Apjoms: S

**Pašlaik:** Pārlūka DOM: currentState.hidden=true, bet aprēķinātais display ir inline-flex. Zaļais “DWD observation current” vizuāli paliek ekrānā, lai gan tam uzlikts aria-hidden.

**Risinājums:** Vienādot paslēpšanu ar komponentes noteikumu .hero-state[hidden]{display:none}. Pārskatīt visus statusus, lai CSS nepārraksta hidden. Neveidot atšķirīgu informāciju redzošam lietotājam un palīgtehnoloģijai.

**Gatavs, kad:** Ja hidden=true, elementam nav renderēta laukuma; fresh kopsavilkums nedublējas, bet stale/error statuss ir redzams un pieejams.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.css#L1) · [Piemērs / standarts](https://www.w3.org/TR/WCAG22/)

### 08. [P1] Datu izcelsmi saglabāt, bet mazināt atkārtojumus
Joma: Pārskats · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** Stundām un dienām ir garas FRESH joslas, ISO laiki un tehniskais teksts par quantity. 390 px avota rinda tiek saīsināta ar ellipsis.

**Risinājums:** Īsa metarinda “ICON-D2 · atjaunots 10:01”, plus “Datu izcelsme”. Detalizētā skatā glabāt init, valid, retrieved, statistic/member un modeļa versiju. Problēmas statusu rādīt pie skartā bloka; sekmīgam stāvoklim nevajag lielu zaļu joslu.

**Gatavs, kad:** Katras vērtības avots sasniedzams vienā darbībā, taču pirmais ekrāns nesatur ISO laikzīmes vai backend reason_code.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/provenance_v1.js#L1) · [Piemērs / standarts](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425)

### 09. [P1] Stundu kartītei vajag laikapstākļu detaļas
Joma: Pārskats · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** Klikšķis uz “Now” atver provenance ar “BLOCKED · MISSING_MODEL_VERSION” un “TRUTH_VALUE_NOT_FOUND”. Kartītes primārais rezultāts ir tehniskā diagnostika.

**Risinājums:** Pirmajā līmenī atvērt stundas detaļas: laiks, temperatūra, vējš, nokrišņu daudzums, avots. Zemāk atsevišķi “Izsekojamība”. Trūkstošu versiju skaidrot kā datu izcelsmes nepilnību. Nākotnes stundas vēl neesošu novērojumu saukt “Novērojums vēl nav pieejams”, ja tas ir atbilstošais iemesls.

**Gatavs, kad:** Klikšķis sniedz prognozes detaļas, kļūdas kods nav galvenā atbilde. “Svaigs” un “Pilnībā izsekojams” ir atsevišķi rādītāji. Šeit novērotā missing-version problēma jāizmeklē arī datu pusē.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/provenance_v1.js#L1) · [Piemērs / standarts](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl)

### 10. [P2] Dienu prognozei dot izvērsumu un skaidru horizontu
Joma: Pārskats · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** Redzamas trīs dienas; Next Days virsraksta bultiņa ir dekoratīvs span. Dienu rindas nav pogas. 320 px testā rindas platums 296 px pārsniedza paneļa 287 px platumu.

**Risinājums:** Izvēršamas dienas ar dienas/nakts detaļām un skaidru min/max. Norādīt faktiskā modeļa pieejamo horizontu. Garākai prognozei ļaut apzināti izvēlēties citu avotu; nepagarināt ICON-D2 ar neatzīmētu cita modeļa prognozi. Šaurā ekrānā sadalīt dienu divās rindās.

**Gatavs, kad:** 320 px izkārtojumā saturs nepārkāpj kartīti; visas darbību bultiņas ir īstas pogas. Nepieejamas dienas netiek izdomātas.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/index.html#L58) · [Piemērs / standarts](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425)

### 11. [P2] Tukšām metrikām jāpasaka iemesls
Joma: Pārskats · Pierādījums: Novērots · Apjoms: S

**Pašlaik:** Spiedienam, lietum pēdējā stundā un mākoņu segai redzams tikai “—”. Trīs no sešām detail kartītēm auditēšanas brīdī nesniedz atbildi.

**Risinājums:** Rādīt “Nav novērojuma” vai konkrēto datu ierobežojumu. Galvenajā rindā izcelt pieejamos novērojumus. Ja pievieno prognozes metriku, marķēt to atsevišķi, saglabājot novērojuma avotu un laiku.

**Gatavs, kad:** Neviens “—” nenozīmē gan nulli, gan trūkstošu mērījumu. 0 mm paliek derīgs skaitlis; trūkstošs daudzums nepārvēršas 0.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/index.html#L69) · [Piemērs / standarts](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425)

### 12. [P1] Modeļu lapā salīdzinājumu likt vispirms
Joma: Modeļi · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** Pirmajā Models panelī ir desmit provider kartītes ar ingest/freshness un iekšējiem kodiem. Temperatūras un nokrišņu salīdzinājumi atrodas zem šīs diagnostikas.

**Risinājums:** Sākt ar WeatherNext 3 statusu un salīdzinājuma grafiku. Pievienot mainīgā, horizonta un avotu izvēli. Darbības diagnostiku pārvietot uz Status; neaktīvos provider apvienot izvēršamā grupā. WeatherNext saglabāt redzamu arī pending stāvoklī.

**Gatavs, kad:** Vienā ekrānā saprotams, kuri modeļi salīdzināti un kur tie atšķiras. Nav jāizritina visu adapteru veselības katalogs.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/index.html#L99) · [Piemērs / standarts](https://www.windy.com/)

### 13. [P1] Modeļu izkliedi aprēķināt vienā un tajā pašā laikā
Joma: Modeļi · Pierādījums: Koda risks · Apjoms: M

**Pašlaik:** renderModelSnapshot katram provider atsevišķi izvēlas futureRows(...,1); izkliede ir šo vērtību max–min bez kopīga valid_time pārbaudes. Sesijā visi trīs rādīja 12:00, tāpēc nepareiza izkliede netika novērota.

**Risinājums:** Izvēlēties kopīgu valid_time, location un quantity. Rādīt katra modeļa init/run vecumu un skaidrot, vai salīdzina jaunākos vai vienāda cikla laidienus. Nesakrītošus laikus neiekļaut kopīgā spread; parādīt “Nav kopīga laika”.

**Gatavs, kad:** Tests ar iztrūkstošu 12:00 punktu nedrīkst salīdzināt 12:00 ar 13:00. Interpolācija tikai ar atsevišķu, redzamu metodiku. Spread nav kalibrēta varbūtība.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.js#L566) · [Piemērs / standarts](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425)

### 14. [P1] Grafikiem vajag asis un pieejamu alternatīvu
Joma: Modeļi · Pierādījums: Novērots + DOM · Apjoms: M–L

**Pašlaik:** Temperatūras salīdzinājuma SVG ir vispārīgs aria-label; tekstā ir provider ID, bet nav skaidru laika/temperatūras atzīmju. Overview mazā līkne nesniedz precīzu nolasāmu vērtību tabulu.

**Risinājums:** Rādīt X asi ar vietējo laiku, Y asi ar °C vai mm, skaidru leģendu ar modeļa krāsu un līnijas rakstu. Pievienot fokusa/pieskāriena rādītāju un “Skatīt tabulu”. WeatherNext p10–p90 tikai ar īstiem atbilstošiem datiem.

**Gatavs, kad:** Grafika secinājumu var iegūt arī bez krāsu atšķiršanas un bez peles hover. Tabulā sakrīt laiki, vienības un avoti. Nav jāizlasa simti SVG title elementu.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.js#L1) · [Piemērs / standarts](https://www.w3.org/TR/WCAG22/)

### 15. [P1] Precizitāti sākt ar interpretējamu kopsavilkumu
Joma: Modeļi · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** Accuracy rāda platu tabulu ar MAE/RMSE/Bias, unknown versijām un nepilnīgas truth datu kopas paziņojumu. Lead secība nav hronoloģiska: 6–12h parādās pēc 5–7d.

**Risinājums:** Saglabāt “Provizoriski — novērojumu pārklājums nepilnīgs”. Pievienot perioda robežas, n, pieejamo pārklājumu un metriku skaidrojumus. Pirms tabulas — kompakts attēls pa laika horizontiem. Hronoloģiska secība: 0–6h, 6–12h, 12–24h, 24–48h, 2–3d utt.

**Gatavs, kad:** Kamēr verification_ready=false, nav uzvarētāja nozīmītes vai apgalvojuma “labākais modelis”. MAE skaidro kā kļūdu attiecīgajā vienībā, nevis procentu precizitāti.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/index.html#L145) · [Piemērs / standarts](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425)

### 16. [P1] Palielināt tekstus, kurus patiešām jālasa
Joma: Vizuālais · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** DOM mērījumi: mobilās avota rindas 9.92–10.88 px, stundu laiki 11.36 px, apakšējās navigācijas etiķetes 10.24 px. Vairākas rindas ir sīkas un ar zemu vizuālo uzsvaru.

**Risinājums:** Pamatteksts 16 px, būtiski paskaidrojumi 14 px, navigācija 12–13 px, lieli skaitļi 56–72 px. Izmantot tabular-nums. Samazināt tekstu apjomu, lai lielāki burti nesabojā izvietojumu.

**Gatavs, kad:** 390 px redzami pilni būtiskie nosaukumi; 200% teksta palielinājumā funkcijas paliek pieejamas. Tas ir produkta lasāmības mērķis, nevis WCAG noteikts universāls 14 px minimums.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.css#L1) · [Piemērs / standarts](https://www.w3.org/TR/WCAG22/)

### 17. [P2] Dekorāciju pieskaņot nozīmei
Joma: Vizuālais · Pierādījums: Novērots + kods · Apjoms: S–M

**Pašlaik:** Galvenais stāvoklis rāda Overcast, bet hero augšējā labajā stūrī ir koša saules dekorācija. weather_ui.js dienas fonā ievieto sauli neatkarīgi no mākoņainības.

**Risinājums:** Laikapstākļa ikonu izmantot kā galveno semantisko signālu; fonu padarīt mierīgu vai sasaistīt ar atbilstošu stāvokli. Samazināt glow, stikla efektus un atkārtotas apmales; vizuālo uzmanību rezervēt vērtībām un brīdinājumiem.

**Gatavs, kad:** Apmācies/lietains skats nerada skaidri saulainas dienas iespaidu. Visi teksti saglabā kontrastu uz gaišākā faktiskā fona.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/weather_ui.js#L196) · [Piemērs / standarts](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl)

### 18. [P1] Saskaņot lapas valodu un terminoloģiju
Joma: Piekļūstamība · Pierādījums: Novērots + DOM · Apjoms: M

**Pašlaik:** html lang="lv", bet lielākā daļa interfeisa ir angliski; citviet latviešu un angļu termini ir vienā teikumā.

**Risinājums:** Izvēlēties konsekventu pamatvalodu (šī koncepcija latviski); i18n vārdnīca LV/EN, vēlāk DE pēc vajadzības. Mainīt html lang atbilstoši izvēlei. Tehniskus provider nosaukumus netulkot, bet stāvokļus skaidrot cilvēku valodā.

**Gatavs, kad:** Valodas marķējums atbilst dominējošajai valodai; jauktas valodas fragmentiem, kur nepieciešams, lang atribūts. Kritēriji 3.1.1 un 3.1.2.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/index.html#L2) · [Piemērs / standarts](https://www.w3.org/TR/WCAG22/)

### 19. [P1] Navigācijai vajag stāvokli, URL un fokusu
Joma: Piekļūstamība · Pierādījums: Novērots + kods · Apjoms: M

**Pašlaik:** Piecu navigācijas pogu aria-current/aria-selected ir null. Mainās tikai CSS active; URL paliek /. Pēc pārslēgšanas fokuss paliek uz apakšējās navigācijas pogas.

**Risinājums:** Izmantot navigācijas saites ar /#overview, /#models u.c. un aria-current="page" vai pilnu tab pattern. Skatu maiņā pārdomāti vadīt fokusu uz virsrakstu; atbalstīt Back un atsvaidzināšanu konkrētajā skatā. Pievienot “Pāriet uz saturu”.

**Gatavs, kad:** Var atvērt tiešu saiti uz Models un atgriezties ar Back. Tastatūra sasniedz skata saturu paredzamā secībā; redzams focus-visible un navigācija to neaizsedz.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.js#L234) · [Piemērs / standarts](https://www.w3.org/TR/WCAG22/)

### 20. [P2] Kontrasts jāpārbauda uz faktiskajiem foniem
Joma: Piekļūstamība · Pierādījums: Vēl jāmēra · Apjoms: S–M

**Pašlaik:** Sīkais pelēkzilais teksts un caurspīdīgie gradienti rada risku. Pilns kontrasta aprēķins katram dienas/nakts fonam šajā auditā nav veikts; apgalvojums par visas lapas AA neatbilstību netiek izdarīts.

**Risinājums:** Tekstam izvēlēties stabilas virsmas un izmērīt kontrastu visos stāvokļos. Parastam tekstam ≥4.5:1, lielam ≥3:1, būtiskiem vadības/grafiku elementiem ≥3:1. Fokusa indikators jāredz arī uz košā hero.

**Gatavs, kad:** Kontrasta matrica gaišam/tumšam, selected/hover/focus, warning/stale/error stāvokļiem. Atsevišķi pārbaudīt īsto gradienta fonu zem teksta.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.css#L1) · [Piemērs / standarts](https://www.w3.org/TR/WCAG22/)

### 21. [P2] Desktop izkārtojumam izmantot pieejamo platumu
Joma: Vizuālais · Pierādījums: Novērots · Apjoms: M

**Pašlaik:** Aptuveni 1366 px logā saturs paliek vienā ~900 px kolonnā ar telefona tipa apakšējo navigāciju. Garš hero un tehniskie paneļi atliek dienu kopsavilkumu.

**Risinājums:** No ~1024 px izmantot 12 kolonnu režģi: 8 kolonnas laikapstākļiem, 4 dienām un modeļu kopsavilkumam. Desktop navigācija augšā; mobilajā saglabāt piecus esošos galamērķus. WeatherNext kartīte paliek pārskatā.

**Gatavs, kad:** 1440 px vienlaikus redzams current, stundas un dienas. 768 px pāriet vienā kolonnā, 390 px nepazaudē nevienu funkciju.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.css#L1) · [Piemērs / standarts](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425)

### 22. [P2] Laika zonu norādīt vienreiz saprotamā vietā
Joma: Pārskats · Pierādījums: Novērots · Apjoms: S

**Pašlaik:** Katrai stundas kartītei atkārtojas GMT+2; mobilajā tas piespiež laiku divās rindās. Statusos vienlaikus ir lokāls un ISO UTC laiks.

**Risinājums:** Sadaļas galvenē “Vietējais laiks · Europe/Berlin”; kartītēs 13:00, 14:00. Pārejā uz jaunu dienu datums. UTC/init/lead saglabāt izcelsmes detaļās. DST atkārtotām stundām nepieciešams papildmarķējums.

**Gatavs, kad:** Stundu kartītes nesatur lieku atkārtojumu; DST 02:00 dubultošanās paliek nepārprotama. Attēlotais “pirms N min” atjaunojas, neatkārtojot visu API pieprasījumu.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/consumer_ui.js#L42) · [Piemērs / standarts](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425)

### 23. [P1] Ielādi neatkarīgos blokus neatkarīgi
Joma: Tehniskais · Pierādījums: Koda risks · Apjoms: M

**Pašlaik:** refresh() vispirms gaida provider health, pēc tam Promise.allSettled gaida visus četrus datu pieprasījumus pirms renderēšanas. apiWithFallback nav redzama AbortController timeout. Tas ir koda risks; lēnais tīkls netika simulēts.

**Risinājums:** Skaidri atrisināt vietas sākotnējo izvēli, pēc tam ielādēt un renderēt current/hourly/daily katru atsevišķi. Pievienot termiņu, atcelšanu vietas maiņai un skeleton ar rezervētu izmēru. Provider kļūda nepaslēpj citus datus.

**Gatavs, kad:** Lēns daily vai health pieprasījums neatstāj jau saņemtu current neredzamu bezgalīgi. Testā ar vienu aizturētu API pārējie paneļi pabeidz ielādi. Mērīt faktisko laiku līdz noderīgam saturam.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.js#L585) · [Piemērs / standarts](https://web.dev/articles/vitals)

### 24. [P1] PWA bezsaistes apvalks ir nepilnīgs
Joma: Tehniskais · Pierādījums: Koda risks · Apjoms: M

**Pašlaik:** index.html ielādē septiņus skriptus; sw.js precache sarakstā nav runtime_badge.js, accuracy_v3.js un provenance_v1.js. Fetch handler neliek jaunus tīkla rezultātus šajā kešā. Reāla offline restartēšana šajā sesijā nav veikta.

**Risinājums:** Veidot versijotu pilnu app-shell manifestu no faktiskajām atkarībām. Pēc apvalka izmaiņām atjaunot cache versiju. Datiem uzturēt atsevišķu last-known marķējumu; veci brīdinājumi nedrīkst izskatīties aktuāli.

**Gatavs, kad:** Pēc viena sekmīga apmeklējuma offline pārlāde ielādē visus UI skriptus bez resursu kļūdām. Pēc jaunas versijas nav sajauktu vecu/jaunu moduļu. Pārbaudīt arī instalāciju reālā Android/iOS ierīcē.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/sw.js#L1) · [Piemērs / standarts](https://web.dev/articles/vitals)

### 25. [P2] UI slāņus padarīt vienkāršāk uzturamus
Joma: Tehniskais · Pierādījums: Koda pārskats · Apjoms: M–L

**Pašlaik:** app.js ir ~39 KB, papildskripti pārtver globālās render funkcijas; consumer_ui.js izmanto arī MutationObserver. weather_ui.js injicē papildu stilus. Redzamā hidden kļūda ilustrē šo slāņu mijiedarbības risku.

**Risinājums:** Saglabāt vieglo FastAPI/SQLite un vanilla JS pieeju. Izdalīt API stāvokli, formatēšanu un skatu renderētājus ES moduļos; vienu datu view-model un vienu tokenu stilu avotu. Framework migrācija nav nepieciešama šim auditam.

**Gatavs, kad:** Komponentei viens renderēšanas īpašnieks. Nemainās provider normalizācija, novērojumu atšķiršana un vērtību izsekojamība. Veikt pa vienam vertikālam UI griezumam.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/consumer_ui.js#L247) · [Piemērs / standarts](https://web.dev/articles/vitals)

### 26. [P2] Saskaņot dizaina dokumentāciju ar pašreizējiem principiem
Joma: Tehniskais · Pierādījums: Novērots + dokuments · Apjoms: S

**Pašlaik:** docs/UI.md vēl satur vecu 10416 piemēru un Combined slēdzi, bet README nosaka 05480 kā current benchmark un AGENTS atliek weighted Combined. Esošā dokumentācija daļēji apraksta ieceri, nevis realizēto UI.

**Risinājums:** Atjaunot UI specifikāciju: 05480, skaidri nodalīts observed/forecast, piecas primārās sadaļas, pirmšķirīgs WeatherNext un bez mākslīga Combined. Marķēt “ieviests / plānots / bloķēts ar datiem”.

**Gatavs, kad:** UI docs, README un reālais interfeiss nerada pretrunīgus solījumus; katrai jaunai komponentei definēts datu avots un visi stāvokļi.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/index.html#L1) · [Piemērs / standarts](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/docs/UI.md)

### 27. [P2] Vienota komponentu un dizaina tokenu sistēma
Joma: Vizuālais · Pierādījums: Priekšlikums · Apjoms: M

**Pašlaik:** Vairāki paneļu, statusu, mazo fontu un ikonu stili ir izkaisīti CSS un skriptu ģenerētā stilā. Dekoratīvie Unicode simboli sajaucas ar laikapstākļu SVG.

**Risinājums:** Definēt krāsas, teksta izmērus, atstarpes 4/8/12/16/24/32, radius 12/16/24 un semantiskus statusus. Vienots SVG ikonu komplekts; informāciju nelikt tikai ikonā. Gaišo/tumšo režīmu ieviest pēc kontrasta pārbaudes, ievērojot sistēmas izvēli.

**Gatavs, kad:** Visām kartītēm vienoti header/meta/content/action elementi; touch mērķis 44×44 px kā produkta standarts. WCAG 2.2 AA 2.5.8 minimums ir 24×24 ar izņēmumiem; 44×44 nav vispārēja AA prasība.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.css#L1) · [Piemērs / standarts](https://www.w3.org/TR/WCAG22/)

### 28. [P2] Veiktspēju un PWA mērīt pirms pārbūves
Joma: Tehniskais · Pierādījums: Vēl jāmēra · Apjoms: M

**Pašlaik:** Auditā nav veikts Lighthouse/CrUX lauka datu vai akumulatora patēriņa mērījums. Var noteikt renderēšanas riskus, bet nevar piešķirt reālu Performance punktu skaitu.

**Risinājums:** Fiksēt sākuma LCP/INP/CLS un laiku līdz pirmajai derīgajai prognozei. Testēt aukstu/siltu cache, lēnu mobilo tīklu, API kļūdu un atgriešanos no fona. Kartes kodu ielādēt tikai Radar atvēršanā. Vietnei nav vajadzīga smaga bibliotēka tikai dekorāciju dēļ.

**Gatavs, kad:** Mērķi p75 reāliem apmeklējumiem: LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1. Privātam mazapmeklētam dashboard, ja CrUX nav datu, saglabāt laboratorijas mērījumus un minimālu privātumam atbilstošu mērījumu pieeju.

[Kods](https://github.com/rozkalnsandris/rozkalns_weather/blob/d396b3dfdbc8680b7e28e7606096ae204746ee04/src/rozkalns_weather/static/app.js#L616) · [Piemērs / standarts](https://web.dev/articles/vitals)

## Ieviešanas secība

1. Uzticamība, DWD stāvokļi, hidden, kopīgs valid time, valoda/navigācija — 2–4 dienas.
2. Overview, mobilais UI, dienas, provenance, tokeni — 4–6 dienas.
3. Radars, brīdinājumi, modeļu un accuracy grafiki — 5–10 dienas.
4. Neatkarīga ielāde, PWA, moduļi un kvalitātes pārbaudes — 3–5 dienas.

Kopā orientējoši 14–25 darba dienas vienam izstrādātājam; atkarīgs no radara līguma un datu pieejamības.

## Web piemēri

- [Yr](https://www.yr.no/en/forecast/daily-table/2-2810878/Germany/North%20Rhine-Westphalia/Regierungsbezirk%20Arnsberg/Werl)
- [meteoblue](https://www.meteoblue.com/en/weather/week/copenhagen_denmark_2618425)
- [Windy](https://www.windy.com/)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [Web Vitals](https://web.dev/articles/vitals)

Pilnais vizuālais dokuments: [weather-ui-audits.html](report.html).