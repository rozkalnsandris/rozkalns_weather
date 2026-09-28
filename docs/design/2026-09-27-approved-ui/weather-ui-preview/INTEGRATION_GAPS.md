# Pieņemtā dizaina integrācijas atlikums

Pārbaudītā source versija: `2c7b5c9e45acc25076599dda66b013f111d44d6c`. Šis ir koda struktūras salīdzinājums, ne production ekrānattēlu audits. Pirms ieviešanas atsvaidzināt main un aktīvos PR.

## Galvenais secinājums

Pieņemtie maketi nav tas pats, kas ieviestās lapas. Overview zilie tokeni, tēmas un dienu grafiks jau ir source. Pārējo skatu pieņemtā informācijas hierarhija vēl jāintegrē esošajā lietotnē. Tehniskā ieviešana paliek Plus chat; izskata lēmumi paliek dizaina sarunā.

| Secība | Jau ir source | Vēl jāintegrē no pieņemtā dizaina |
| --- | --- | --- |
| 1. Kopīgais pamats | accepted_ui.css, tēmas, navigācija un fokusa regresijas | Vienots pirmā līmeņa WeatherNext bloks; nepārveidot maršrutēšanu vai atkārtoti ieviest tokenus |
| 2. Overview | Kompaktais zilais A, stundas, dienas, novērojumi; Model Snapshot aiz detaļām | Maketā WeatherNext prioritātes bloks ir pirms stundu prognozes; to saskaņot ar esošo Model Snapshot, neradot divus konkurējošus salīdzinājumus |
| 3. Models | Provider klases, temperatūras/nokrišņu grafiki, uncertainty sadaļa | Izcelts WeatherNext, kompakts salīdzinājums un pieņemtās filtru/vienību vadīklas; esošos grafikus/detalizēto izcelsmi saglabāt pieejamu |
| 4. Status | Lokācijas izvēle, provider health/freshness un reference skaidrojumi | WeatherNext prognožu pieejamība un verification readiness atsevišķi; kompaktas neatkarīgu avotu rindas; tehnisko informāciju izvērst |
| 5. Accuracy | 30/90 dienu izvēle, common-sample tabula, lead buckets un drilldown | Pieņemtā MAE kopsavilkuma hierarhija, mērvienības un izlase; saglabāt esošās tabulas kā detalizētu skatu. Demo koeficientus nepārnest |
| 6. Radar | DWD warnings un radara metadatu ielādes paneļi | Īsta karte, leģenda, kadra laiks un player tikai pēc tehniskā raster/time/nodata līguma; maketa SVG nav ieviešanas dati |

## Konkrētais nākamais tehniskais posms

Kopīgais WeatherNext komponents + Overview/Models prioritātes integrācija vienā source PR. Lietot esošās API pieejamības pazīmes, saglabājot trūkstošus datus kā trūkstošus. Forecast readiness un verification readiness nesapludināt. Saglabāt exact-time salīdzinājumu un visas provider vērtības atsevišķi.

Pieņemšanas pierādījumi: abas tēmas 384/412 px, loading/missing/error/stale, īss augstums, tastatūra, esošās navigācijas un hidden regresijas. Ja source līgums nesniedz kādu maketa lauku, nerādīt izdomātu aizvietojumu; dokumentēt trūkumu.

## Svarīgas robežas

- Dortmund ir attēlojamā vieta; Werl / DWD CDC 05480 paliek faktiskais novērojumu un verification reference. Stacijas datus nepārsaukt par Dortmund mērījumiem.
- Izskata maketi pārsvarā latviski, source satur LV/EN sajaukumu. Pilna i18n un noklusētā valoda jāsaskaņo tehniskajā posmā; šis salīdzinājums nepieņem jaunu valodas lēmumu.
- DWD oficiālie brīdinājumi saglabā savu autoritāti un prioritāti.
- Ekrānlasītājs, īsts 200% palielinājums un fiziskās ierīces vēl nav pilnībā validētas. Maketu pārbaudes nepierāda production atbilstību.

## Pārbaudītie source faili

`src/rozkalns_weather/static/index.html`, `accepted_ui.css`, `accuracy_v3.js`, kā arī atbilstošās renderētāju atsauces `app.js`, `weather_ui.js`, `consumer_ui.js`. `docs/UI.md` un pieņemtais `IMPLEMENTATION_HANDOFF.md` nosaka pašreizējo lēmumu kontekstu.

## Teksts Plus chat darba turpināšanai

Turpini #237 pieņemtā mobilā UI integrāciju pēc docs/design/2026-09-27-approved-ui. Vispirms svaigi salīdzini main ar maketiem un aktīvajiem PR. Sāc ar kopīgo WeatherNext prioritātes komponentu un Overview/Models informācijas hierarhiju, saglabājot pieņemto kompakto zilo A, abas tēmas, esošos API/renderētājus un navigācijas līgumu. Backend vai provider vērtības nefabricēt; private access, deploy un merge autoritāti ievērot atsevišķi. Tehniskā integrācija neizvēlas jaunu dizaina virzienu. Šis teksts nav nosūtīts citai sarunai.
