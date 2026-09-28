# Maketu pieejamības pārbaude — 2026-09-27

Tvērums: statiska lokālo maketu HTML/CSS/JavaScript pārbaude. Nav pārlūka, ekrānlasītāja vai pilna WCAG audita pierādījums. Dizaina virziens ir apstiprināts; šie divi lokālie labojumi nemaina izskatu.

## Atrastās un lokāli labotās problēmas

| Komponents | Problēma | Labojums | Pārbaudes atlikums |
|---|---|---|---|
| Radara laika slīdnis | Native range vērtība 0–6 pati nepasaka kadra laiku un observed/forecast nozīmi | `aria-valuetext` tagad satur laiku, novērojums/prognoze un demo norādi | Pārbaudīt ar ekrānlasītāju un bulttaustiņiem |
| Vienotais iframe priekšskatījums | Pārslēgšanās no iframe apakšējās navigācijas iznīcina fokusēto elementu | Pēc pārbūves fokuss pāriet uz izvēlētās sadaļas pogu priekšskatījuma augšējā navigācijā | Pārbaudīt fokusa redzamību un tālāko Tab secību |

## Avotā konstatētais

- Filtri izmanto native select/button; aktīvā lieluma izvēle izmanto aria-pressed.
- Kartes ilustrācijai ir teksta alternatīva un skaidra demo norāde.
- Shared navigācijā ir aria-current un nosaukumi; aktīvais skats nav norādīts tikai ar krāsu.
- Radara atskaņošana sākas tikai pēc lietotāja darbības, tai ir pauze, un paslēpjot dokumentu tā apstājas.
- V2 pārbaudītie 12 teksta/fona pāri pārsniedz 4.5:1. Tā nav visu komponentu vai netekstuālā kontrasta pārbaude.
- 44 px vadīklas ir dizaina mērķis; to reālie renderētie izmēri šajā pārbaudē nav izmērīti. WCAG 2.1 2.5.5 ir AAA, ne AA prasība.

## Nepabeigtais V3

Jāpārbauda reālais renderējums abās tēmās, 384/412 px, šaurāks skats un 200% palielinājums. Jānovērtē teksta nogriešana, horizontāls overflow, fixed navigācijas pārklāšanās, fokusa redzamība, visu stāvokļu kontrasts un screen-reader paziņojumi. Automātiska lokāla faila atvēršana iepriekš tika bloķēta ar pārlūka URL politiku; šis dokuments to neapiet un neapgalvo vizuālu validāciju.

Šis dokumentācijas PR publicē abus maketu labojumus; production lietotne netiek mainīta. PR #251 pārbauda īstās lietotnes navigāciju; tas nav šo atsevišķo dizaina maketu vizuāls pierādījums.
