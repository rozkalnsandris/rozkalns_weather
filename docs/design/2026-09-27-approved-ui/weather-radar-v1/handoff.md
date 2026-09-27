> Aktuālais lēmums — 2026-09-27: Andris pieņēma V2 un Models/Radar/Accuracy/Status dizaina virzienu kā pamatu ieviešanai. Zemāk esošās agrākās norādes par gaidītu dizaina apstiprinājumu ir aizstātas ar šo lēmumu. Vizuālā un integrācijas pārbaude vēl jāveic.

# Radar v1 — dizaina priekšlikums

Statuss: pieņemts kā pamats ieviešanai; production nav mainīts. Abas tēmas un darba platumi 412/384 px. Karte ir pašu veidota izdomāta SVG ilustrācija, ne ģeogrāfiska vai meteoroloģiska informācija.

Galvenā hierarhija: karte → kadra laiks → laika slīdnis → atskaņošana → leģenda → atsevišķa DWD brīdinājumu sadaļa. Slīdnis, kadru pogas, pauze un atgriešanās jaunākajā novērojumā darbojas ar demonstrācijas kadriem. Autoplay netiek sākts automātiski; paslēpjot dokumentu, atskaņošana apstājas.

## Integrācijas prasības Plus chat

- Saglabāt faktiskās projekcijas, encoding, vienību, nodata un kartes pārklājuma līgumus. Šīs ilustrācijas kustību vai krāsas nepārnest kā radara datu dekodēšanu.
- Viena kadra laiks ir autoritatīvs gan kartes slānim, gan laika uzrakstam; novērst asinhronu kadru sajaukšanos.
- Novērojums un nowcast ir atšķirīgi stāvokļi. Prognozes garumu un robežu ņemt no pieejamajiem kadriem, ne no maketa.
- Jaunākais atgriež uz jaunāko novērojumu; ne uz tālāko prognozes kadru.
- Trūkstošu/novecojušu/neielādētu karti norādīt skaidri; tukša karte nedrīkst nozīmēt “lietus nav”.
- Leģendā izmantot īsto produkta mērvienību un sliekšņus; saglabāt krāsu un slāņa datu atbilstību.
- DWD brīdinājumu saturs izmanto esošo oficiālo brīdinājumu līgumu. Karte nedod warning authority.
- Neizpaust privātās mājas koordinātas. Maketā nav lietotāja atrašanās vietas pieprasījuma.
- Reālajā implementācijā testēt tastatūru, kadra nosaukumu ekrānlasītājam, skārienus, palielinātu tekstu, orientāciju un abas tēmas. Pogu minimālais izmērs 44 px.

JavaScript pārbaudīts ar node --check; vizuālā/interakciju pārbaude pārlūkā vēl nav pabeigta. Dizaina virziens apstiprināts; pirms integrācijas pabeigšanas vajadzīga renderējuma validācija.
