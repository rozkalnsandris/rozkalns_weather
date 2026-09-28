# Apstiprinātais Weather mobilais UI — 2026-09-27

Andris šajā dizaina sarunā apstiprināja: “Jā, pieņemam un gatavojam ieviešanu”. Tas aptver V2 komponentus un Models/Radar/Accuracy/Status maketus ar izceltu WeatherNext 3 kā galveno pētniecības modeli. Overview A ir agrāk pieņemtais pamats.

- [Vienotais interaktīvais priekšskatījums](weather-ui-preview/index.html)
- [Integrācijas atlikums pret source — 2026-09-28](weather-ui-preview/INTEGRATION_GAPS.md)
- [Mobilā maketa pārbaudes un atlikušās robežas](weather-ui-preview/MOBILE_VALIDATION.md)
- [Ieviešanas handoff un secība](weather-ui-preview/IMPLEMENTATION_HANDOFF.md)
- [Pārskatīšanas saraksts](weather-ui-preview/review.md)
- [V2 tokeni un komponenti](weather-design-system-v2/handoff.md)
- [Models](weather-models-v1/handoff.md), [Radar](weather-radar-v1/handoff.md), [Accuracy](weather-accuracy-v1/handoff.md), [Status](weather-status-v1/handoff.md)

GitHub HTML rāda kā avota kodu. Lejupielādēt šo direktoriju ar visām apakšmapēm un atvērt `weather-ui-preview/index.html` lokālā pārlūkā. Saglabāt relatīvo failu struktūru. Nav ārēju fontu, API vai bibliotēku pieprasījumu.

Visi demonstrācijas skaitļi un statusi ir izdomāti un skaidri marķēti. WeatherNext vērtības netiek fabricētas. Radar SVG nav īsta karte. Overview paraugs ir komponentu stāvokļu demonstrācija, ne pilnīga production Overview kopija.

## Pierādījumi un atlikums

JS sintakse un statiskās lokālās saites pārbaudītas; 12 V2 teksta/fona pāri sasniedz vismaz 4.5:1. Pārlūka renderējuma, tastatūras, pilns a11y un fizisku ierīču audits nav pabeigts. Darba platumi 384/412 px nav fizisko ierīču emulācija. Dizaina pieņemšana nenozīmē, ka V3 vizuālās validācijas vai visa #237 DoD ir pabeigta.

Source pamats sagatavošanas brīdī: `0c5226cf7edccd926b49863964527c2581df2fbe` (PR #244 exact-time alignment jau main). PR #245 hidden renderējuma pārbaude ir atsevišķs tehniskais darbs; šo pakotni ar to nedublēt.

Part of #237. UI izskata lēmumi paliek šajā dizaina sarunā; tehniskā integrācija paliek Plus chat. Šī dokumentācijas publikācija nemaina application source, API, production, private access, DB vai deployment politiku.
