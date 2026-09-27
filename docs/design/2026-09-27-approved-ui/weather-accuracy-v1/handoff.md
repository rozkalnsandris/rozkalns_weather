> Aktuālais lēmums — 2026-09-27: Andris pieņēma V2 un Models/Radar/Accuracy/Status dizaina virzienu kā pamatu ieviešanai. Zemāk esošās agrākās norādes par gaidītu dizaina apstiprinājumu ir aizstātas ar šo lēmumu. Vizuālā un integrācijas pārbaude vēl jāveic.

# Accuracy v1 — mobilā maketa handoff

Statuss: pieņemts kā pamats ieviešanai. Nav production izmaiņu. Visi skaitļi ir izdomāti un redzami marķēti kā demo. Gaišā/tumšā tēma; 412 un 384 px darba platumi.

## Dizaina izvēles

Pirms rezultātiem parāda periodu, kopīgo paraugu skaitu un DWD novērojumu avotu. Modeļiem ir stabila secība bez “uzvarētāja” medaļas. MAE vienības parāda blakus skaitlim; paskaidrojums pieejams atveramās detaļās. WeatherNext nav slēpts un nesaņem izdomātu precizitāti. Prognozes soļa izvēle ietver nepietiekamu datu piemēru.

## Tehniskajai ieviešanai

- Lietot esošo verification API un readiness līgumu. Demo vērtības, izlases un reizinātājs nekādā veidā nav analītikas implementācija.
- Reālos lead buckets un periodus ņemt no kanoniskās metodoloģijas; maketa filtru robežas nav jauns backend līgums.
- Atbilst vieta, exact valid time, vienība, statistic un nokrišņu akumulācijas intervāls. Katram filtram kopīgo izlasi veido no salīdzināmiem forecast/truth pāriem.
- Parādīt faktisko n un exclusion/coverage iemeslus. Pietiekamības slieksni neizdomāt UI. Ja izlase nav salīdzināma, nereitingot.
- Model-version periodus neapvienot bez metodoloģijas. DWD 05480 ir publiskais mērījumu etalons; tas nav measured home accuracy.
- Nokrišņu daudzuma kļūda mm nav probability accuracy; CRPS/Brier neprasīt no deterministiskām vērtībām.
- Joslām kopīga skala vienā skatā un vienmēr skaitliskā alternatīva. Pirms production vēl izvērtēt fiksētu ass skalu un filtru maiņas uzvedību, lai vizuāli nemaldinātu.
- Loading/error/stale/empty izmantot V2 stāvokļu līgumu pēc dizaina pieņemšanas. Keyboard/native select, teksta palielinājums un kontrasts jāpārbauda reālajā renderējumā.

## Pārbaudes

Abu lapu inline JavaScript sintakse pārbaudīta ar node --check. Pārlūka vizuālā pārbaude nav pabeigta; iepriekš lokālu failu atvēršanu bloķēja URL politika. Dizaina virziens apstiprināts; integrācijas validācija vēl jāveic.


## WeatherNext 3 prioritātes precizējums

Pēc lietotāja norādes WeatherNext 3 izcelts atsevišķā kartītē skata augšdaļā ar pilnu nosaukumu un “Galvenais pētniecības modelis” lomu. Overview kartīte seko pašreizējam novērojumam, pirms stundu prognozes; Models un Accuracy tā atrodas pirms filtriem. Pieejamības teksts maketā ir demonstrācija, ne runtime diagnoze. Reālajā integrācijā statusu ņem no aktuālā API; pēc datu pieejamības kartīte rāda īstās vērtības ar provenance. Accuracy saglabā atsevišķu verification readiness prasību. Primārā pētniecības loma nenozīmē pierādītu augstāku precizitāti vai DWD brīdinājumu autoritāti.
