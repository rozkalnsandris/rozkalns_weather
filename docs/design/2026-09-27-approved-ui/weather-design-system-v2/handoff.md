> Aktuālais lēmums — 2026-09-27: Andris pieņēma V2 un Models/Radar/Accuracy/Status dizaina virzienu kā pamatu ieviešanai. Zemāk esošās agrākās norādes par gaidītu dizaina apstiprinājumu ir aizstātas ar šo lēmumu. Vizuālā un integrācijas pārbaude vēl jāveic.

# Weather V2 — komponentu priekšlikums

Statuss: dizaina virziens apstiprināts ieviešanas sagatavošanai; nav production izmaiņa. Pamats: pieņemtais kompaktais zilais Overview A. Dati ir demonstrācijas vērtības.

## Tokeni

Krāsas pārņemtas no Overview A `accepted_ui.css`, nevis izveidots jauns virziens.

| Loma | Gaišs | Tumšs |
|---|---|---|
| Fons | #f0f5fa | #101b29 |
| Karte | #ffffff | #18293b |
| Teksts | #203b54 | #e7f0f8 |
| Palīgteksts | #586f82 | #a8bed1 |
| Akcents | #286f9e | #8bc2ef |
| Robeža | #dce6ef | #304960 |

Teksts: system-ui; pamats 14 px, virsraksti 15 px, metadati 11–12 px, temperatūra 70 px. Kartes: 14 px rādiuss, 13 px iekšējā atstarpe, 9 px vertikālā atstarpe. Pogu skāriena laukums vismaz 44 × 44 px. Fokuss: 2 px akcents ar 3 px nobīdi.

## Stāvokļu līgums

- Pieejams: datu vērtības, avots un mērījuma vecums.
- Ielāde: stabils vietturis, bez izdomātas temperatūras; animācija nav nepieciešama.
- Nav datu: domuzīme un īss skaidrojums; nekad nulle kā aizvietotājs.
- Novecojis: saglabā pēdējos datus, skaidri parāda to vecumu. Dzintara krāsa un teksts.
- Kļūda: lokāls kļūdas paziņojums ar atkārtotas ielādes darbību; citu avotu datus neslēpj.
- DWD brīdinājums: atšķirīga semantiska krāsa, avots, spēkā esamības laiks un cilvēkam lasāms teksts. Reālā severity/krāsa jāsaista ar DWD līgumu; paraugs rāda vienu ilustratīvu stāvokli.

Tehniskā izcelsme paliek pieejama atveramās detaļās. Brīdinājumu un trūkstošu datu nozīmi nenodod tikai ar krāsu. Tab/Enter izmanto native button/select/details elementus. Navigācija paraugā ir tikai izskata demonstrācija.

## Integrācijas robeža

Tēmas politika paliek Auto 20.00–07.00 Europe/Berlin ar manuālu izvēli. Šī lapa salīdzina abas tēmas; tā nepārslēdz production iestatījumus. Faktiskā ielāde, request dedupe, stale sliekšņi, avotu kļūdas, i18n un PWA paliek Plus chat tehniskajam darbam. Pirms integrācijas jāapstiprina stāvokļu izskats un jāvalidē kontrasts, tastatūra un ekrānlasītājs reālajos komponentos.

## Pārbaudes — 2026-09-27

Aprēķināts 12 teksta/fona pāru relatīvais kontrasts: visi vismaz 4.5:1; zemākais pārbaudītais pāris ir gaišās tēmas palīgteksts uz maigā zilā fona (4.63:1). Rezultāti `contrast-check.json`. Tas nav pilns WCAG audits: gradienti, visi komponentu stāvokļi, fokuss un reāli renderētie elementi vēl jāpārbauda pārlūkā.

Abu HTML failu inline JavaScript iztur `node --check`. Vizuālā un interakciju pārbaude nav pabeigta: automatizētā pārlūka lokālā faila atvēršanu bloķēja URL drošības politika.

## Plus chat integrācijas kontrolsaraksts

Šī ir specifikācija, ne atļauja jaunas production versijas izvietošanai. Pārņemt pēc stāvokļu dizaina pieņemšanas šajā sarunā.

1. Lietot esošos Overview A CSS tokenus. Nepievienot otru atšķirīgu krāsu sistēmu un nekopēt parauglapas demonstrācijas datu loģiku production.
2. Kartēm piemērot vienādas atstarpes/rādiusus; saglabāt 44 px interaktīvos laukumus arī kompaktajā izskatā.
3. Katra datu bloka statusu sasaistīt ar tā paša avota stāvokli. Viena avota kļūda nepadara visus rādījumus tukšus.
4. Ielādes laikā izmantot vietturi tikai tad, ja nav iepriekšēju datu; atsvaidzinot saglabāt pēdējās vērtības ar skaidru statusu.
5. Missing/null attēlot ar domuzīmi; nulle ir tikai reāla vērtība. Nokrišņiem saglabāt mm, ne izdomātu varbūtību.
6. Novecojušiem datiem parādīt faktisko laiku/vecumu. Slieksni ņemt no avota līguma, ne no šī maketa.
7. Kļūdas darbībai pieslēgt esošo ielādes mehānismu, atkārtoto pieprasījumu novēršanu un pieejamu statusa paziņošanu.
8. DWD brīdinājumus piesaistīt esošajai severity, lifecycle un cilvēkam lasāmā satura implementācijai. Demo tekstu nepublicēt kā īstu brīdinājumu.
9. Tehniskās detaļas atstāt atveramas; avotu, datu vecumu un būtisku kļūdas nozīmi rādīt arī aizvērtā stāvoklī.
10. Pirms PR gatavības pārbaudīt 384 un 412 px platumu, palielinātu tekstu, abas tēmas, tastatūru un visus stāvokļus. Pārbaudīt esošo navigāciju un tēmas izvēles saglabāšanu.

## Pieņemšanas robeža

Overview A virziens jau ir pieņemts. V2 un V3 maketi pieņemti kā pamats ieviešanai; vizuālā un integrācijas validācija paliek nepabeigta.


## WeatherNext 3 prioritātes precizējums

Pēc lietotāja norādes WeatherNext 3 izcelts atsevišķā kartītē skata augšdaļā ar pilnu nosaukumu un “Galvenais pētniecības modelis” lomu. Overview kartīte seko pašreizējam novērojumam, pirms stundu prognozes; Models un Accuracy tā atrodas pirms filtriem. Pieejamības teksts maketā ir demonstrācija, ne runtime diagnoze. Reālajā integrācijā statusu ņem no aktuālā API; pēc datu pieejamības kartīte rāda īstās vērtības ar provenance. Accuracy saglabā atsevišķu verification readiness prasību. Primārā pētniecības loma nenozīmē pierādītu augstāku precizitāti vai DWD brīdinājumu autoritāti.
