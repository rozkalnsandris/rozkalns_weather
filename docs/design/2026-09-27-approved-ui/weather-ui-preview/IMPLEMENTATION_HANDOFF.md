# Weather UI — vienotais ieviešanas handoff

Statuss: 2026-09-27 Andris apstiprināja V2 komponentus un Models, Radar, Accuracy, Status kā pamatu ieviešanai ar izceltu WeatherNext 3: “Jā, pieņemam un gatavojam ieviešanu”. Dizaina apstiprinājums neaizvieto renderējuma pārbaudi vai aktuālos repozitorija merge/deploy noteikumus.

## Saglabājamais virziens

Kompakts zilais Overview A, gaišā/tumšā tēma, mobilā prioritāte. WeatherNext 3 ir galvenais pētniecības modelis; tas nenozīmē pierādītu augstāku precizitāti un neaizvieto DWD oficiālos brīdinājumus. Ja īstu datu nav, saglabā skaidru pending stāvokli. Dati no citiem modeļiem netiek pārsaukti par WeatherNext.

## Ieviešanas secība

| Posms | Rezultāts | Robeža / pieņemšanas pierādījums |
|---|---|---|
| 1. Kopīgie komponenti | Esošie zilie tokeni, kartes, pogas, fokuss, statusi un tēmas | Saglabāts esošais Overview; native vadīklas; 384/412 px un palielināts teksts |
| 2. WeatherNext prioritāte | Kartīte Overview, Models, Accuracy, Status | Faktiska API pieejamība; forecast un verification readiness atsevišķi; nav demo skaitļu |
| 3. Models | Vienas vietas/laika salīdzinājums un avotu detaļas | Exact valid-time, atbilstoši intervāli/vienības, katram modelim provenance |
| 4. Status | Neatkarīgi avotu statusi un pēdējo datu vecums | Viena avota kļūda neslēpj pārējos; noslēpumi un privātie dati netiek eksponēti |
| 5. Accuracy | MAE, periods, kopīgā izlase, readiness | Faktiska verification API; nepietiekamiem datiem nav reitinga; WeatherNext netiek fabricēts |
| 6. Radar | Karte, kadra laiks, novērojums/nowcast, player un leģenda | Atkarīgs no īstā encoding/projection/unit/nodata līguma; demo SVG netiek izmantots |
| 7. Kopīgā validācija | Pabeigti skati abās tēmās | Pārlūka/keyboard/a11y pārbaude, esošo testu pārbaude, source un LIVE pierādījumi atsevišķi |

Ieteicamas nelielas saistītas PR daļas, saglabājot #237 kā umbrella līdz visam DoD. Pirms darba svaigi nolasīt GitHub main un aktuālās izmaiņas, lai nedublētu Plus chat darbu. Šeit norādītā secība ir dizaina integrācijas priekšlikums; tā neaizvieto tehnisko atkarību pārbaudi.

## Failu karte

- `weather-ui-preview/index.html`: kopīgais interaktīvais priekšskatījums.
- `weather-ui-preview/navigation.js`: tikai lokāla maketu navigācija.
- `weather-design-system-v2/`: Overview komponentu paraugi un stāvokļi, ne pilna production Overview kopija.
- `weather-models-v1/`: modeļu salīdzinājums.
- `weather-radar-v1/`: ilustratīva karte un vadīklas.
- `weather-accuracy-v1/`: demonstrācijas verification skats.
- `weather-status-v1/`: demonstrācijas provider statusi.
- Katras sadaļas `handoff.md`: konkrētās integrācijas prasības un robežas.

## Ko nekopēt production

Nekopēt izdomātos skaitļus, datu vecumus, statiskos statusus, simulēto karti, Accuracy reizinātāju un demo laika intervālus. Šeit esošie JavaScript faili demonstrē interakcijas, ne API vai metodoloģijas implementāciju. Nepārnest iframe apvalku kā production lietotnes arhitektūru.

## Esošie pierādījumi

Veiktas JavaScript sintakses un lokālo statisko saišu pārbaudes. Pārbaudīti 12 V2 teksta/fona pāri, minimums 4.63:1. Nav pabeigta vizuālā/interakciju pārbaude pārlūkā, pilns WCAG audits vai reālu ierīču pārbaude. Dizaina avoti ir šajā dokumentācijas pakotnē; tie nav production izmaiņa.
