> Aktuālais lēmums — 2026-09-27: Andris pieņēma V2 un Models/Radar/Accuracy/Status dizaina virzienu kā pamatu ieviešanai. Zemāk esošās agrākās norādes par gaidītu dizaina apstiprinājumu ir aizstātas ar šo lēmumu. Vizuālā un integrācijas pārbaude vēl jāveic.

# Models v1 — mobilā dizaina priekšlikums

Statuss: lietotājs apstiprinājis kā pamatu ieviešanai. Gaišā/tumšā palete pārņemta no pieņemtā Overview A. Visi skaitļi ir izdomāti demonstrācijas dati; WeatherNext vērtības netiek izdomātas.

## Hierarhija

1. Vieta un salīdzināmais lielums: temperatūra / lietus / vējš.
2. Viens kopīgs prognozes laiks ar Europe/Berlin norādi.
3. WeatherNext kā primary research modelis ar explicit pending; atsevišķas ICON-D2, IFS un AIFS rindas.
4. Skaitliska modeļu atšķirība; nav accuracy, varbūtība vai ticamības intervāls.
5. Atveramas avotu/izlaidumu detaļas.

Interaktīvais makets ļauj mainīt lielumu un laiku. A55 412 px un S25+ 384 px ir darba platumi, ne pilna ierīču emulācija. Navigācija uz neizstrādātajām lapām nav pieslēgta.

## Tehniskajai integrācijai Plus chat

- Salīdzināt tikai vienas vietas un exact valid-time vērtības, katra lieluma vienības un semantiku saglabājot.
- Nelietot tuvāko pieejamo laiku kā klusētu aizvietojumu. Trūkstošam avotam rādīt —.
- Nokrišņiem jāsakrīt arī akumulācijas intervālam; mm nav lietus varbūtība.
- Izlaiduma/model-version/retrieval/lead-time/statistic metadatus saglabāt katram avotam. “Nav zināms” nepārrakstīt ar izdomātu vērtību.
- Pieejamo avotu skaitu aprēķināt no reālajiem datiem. Modeļu atšķirību rādīt tikai ar vismaz diviem salīdzināmiem avotiem.
- Pending WeatherNext nav kļūda pārējiem avotiem. Neizsecināt “labāko” modeli no mazākas modeļu atšķirības.
- Stāvokļus pieslēgt V2 komponentu līgumam pēc tā pieņemšanas. Pārbaudīt garus nosaukumus, lielu tekstu, fokusu un abas tēmas.

## Validācija

Inline JavaScript sintakses pārbaude veikta ar node --check. Automatizēta vizuālā pārbaude nav pabeigta, jo iepriekšējo lokālā faila atvēršanu bloķēja pārlūka URL politika. Šis nav production integrācijas vai pilna a11y audita pierādījums.


## WeatherNext 3 prioritātes precizējums

Pēc lietotāja norādes WeatherNext 3 izcelts atsevišķā kartītē skata augšdaļā ar pilnu nosaukumu un “Galvenais pētniecības modelis” lomu. Overview kartīte seko pašreizējam novērojumam, pirms stundu prognozes; Models un Accuracy tā atrodas pirms filtriem. Pieejamības teksts maketā ir demonstrācija, ne runtime diagnoze. Reālajā integrācijā statusu ņem no aktuālā API; pēc datu pieejamības kartīte rāda īstās vērtības ar provenance. Accuracy saglabā atsevišķu verification readiness prasību. Primārā pētniecības loma nenozīmē pierādītu augstāku precizitāti vai DWD brīdinājumu autoritāti.
