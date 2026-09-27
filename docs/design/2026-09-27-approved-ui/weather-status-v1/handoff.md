> Aktuālais lēmums — 2026-09-27: Andris pieņēma V2 un Models/Radar/Accuracy/Status dizaina virzienu kā pamatu ieviešanai. Zemāk esošās agrākās norādes par gaidītu dizaina apstiprinājumu ir aizstātas ar šo lēmumu. Vizuālā un integrācijas pārbaude vēl jāveic.

# Status v1

Dizaina priekšlikums: WeatherNext 3 pirmajā kartītē, atsevišķa forecast availability un verification readiness. Publiskajiem avotiem neatkarīgi statusi un datu vecums. Native select pārslēdz trīs demonstrācijas scenārijus.

Integrācijā statusus ņemt no aktuālajiem provider/readiness līgumiem. Novecošanas sliekšņi ir avotam specifiski. Pēdējā saņemšana un prognozes/novērojuma laiks nav viens lauks. Kopīgs “viss darbojas” nedrīkst aizsegt avota kļūdu. Nekad neatklāt privātus žurnālus, tokenus vai koordinātas. DWD brīdinājumu avota pieejamība nenozīmē, ka nav aktīvu brīdinājumu.

Makets nav monitorings. Visi statusi ir ilustratīvi. Production nav mainīts; dizaina pieņemšana un renderējuma/a11y pārbaude vēl jāveic. JavaScript sintakse pārbaudīta ar node --check.
