# UI / UX

## Mērķis

Mobile-first privāts weather dashboard, kas informācijas ziņā ir tikpat ātri nolasāms kā tradicionāla weather app, bet papildus ļauj redzēt **modeļu atšķirības un WeatherNext 3 uncertainty/accuracy**.

Nav mērķa kopēt Meteo & Radar vizuālo dizainu. No tā izmantojam tikai ideju par:

- skaidru current section;
- hourly forecast;
- daily cards;
- ātri nolasāmiem precipitation/temperature indikatoriem.

## Primary navigation

Minimum tabs/sections:

- `Overview`
- `Models`
- `Radar`
- `Accuracy`
- `Sources/Status`

## Overview

```text
Home — Dortmund-Wickede
Updated 22:15 · Europe/Berlin

CURRENT
19.2 °C   Mostly cloudy
DWD observation · station 10416

NEXT HOURS
22  23  00  01  02  03
19  18  18  17  17  16 °C
      precipitation bars

MODEL CONSENSUS
DWD ICON-D2      ━━━━━━━━━
WeatherNext 3    ┅┅┅┅┅┅┅┅
ECMWF IFS        ┄┄┄┄┄┄┄┄

WEATHERNEXT 3 UNCERTAINTY
mean: 18.4 °C
p10 ├───────●────────┤ p90

TODAY / NEXT DAYS
[day cards]

DWD WARNINGS
No active warnings
```

## WeatherNext prominence

WeatherNext 3 jābūt redzamam bez nepieciešamības iet dziļā settings ekrānā.

Overview jāparāda vismaz:

- WeatherNext current chosen forecast value;
- init time / freshness;
- p10–p90 uncertainty band;
- indikators, cik tālu WeatherNext atšķiras no DWD/ECMWF consensus.

Models view jābūt WeatherNext-first detalizētam salīdzinājumam.

## Models view

Filtri:

- variable: temperature / precipitation / wind;
- horizon: 24 h / 48 h / 5 d / 10 d / 15 d;
- providers toggle.

Grafikā:

- atsevišķa līnija katram provider;
- WeatherNext p10–p90 shaded band;
- provider init time tooltip;
- dashed/stale presentation, ja dati veci;
- observation overlay vēsturiskajā daļā.

## Accuracy view

Galvenā sadaļa projekta pētniecības mērķim.

Cards:

- Temperature MAE last 30d;
- Rain Brier Score last 30d;
- Best provider 0–24 h;
- Best provider 2–5 d;
- WeatherNext trend vs previous 30d;
- current WeatherNext model version.

Charts:

- MAE by lead-time bucket;
- bias by provider;
- WeatherNext p10–p90 coverage;
- precipitation reliability;
- monthly model ranking.

Jārāda sample size `n` un period.

## Radar view

V2 pēc forecast MVP.

Minimum:

- DWD radar map centered on home location;
- home marker;
- time slider;
- observed precipitation layer;
- optional forecast/nowcast extension tikai ar skaidru label.

## Warning UX

DWD warnings vienmēr augstākas prioritātes nekā model disagreement cards.

Warning card rāda:

- official DWD label;
- severity;
- valid period;
- area;
- headline;
- last update.

WeatherNext vai Combined nedrīkst radīt vizuāli identisku “official warning” card.

## Daily cards

Daily summary jāatbalsta provider switch:

```text
Combined | DWD | WeatherNext | ECMWF
```

Katram day card:

- max/min temperature;
- dominant condition;
- precipitation probability/amount;
- sunshine duration, ja pieejama;
- wind/gust summary;
- model disagreement badge, ja atšķirība būtiska.

## Model disagreement

Lietotājam jāredz, ja modeļi nepiekrīt.

Piemēram:

```text
Forecast spread: HIGH
Temperature range across models: 17–22 °C
Rain probability: 20–75%
```

Nedrīkst slēpt disagreement aiz viena “combined” skaitļa.

## Freshness

Katram provider:

```text
WeatherNext 3
Init: 12:00 UTC
Retrieved: 20:16 UTC
Status: fresh
```

Ja provider stale/unavailable, UI to skaidri parāda.

## PWA

MVP mērķis:

- installable home-screen app;
- responsive Android/desktop;
- cached app shell;
- forecast dati var prasīt network;
- vēlāk push notifications tikai DWD warning/useful rain triggers, ja tas tiek atsevišķi autorizēts/ieviests.

## Accessibility / clarity

- nebalstīt nozīmi tikai uz krāsu;
- °C/mm/kmh/hPa skaidri norādīti;
- tooltip/legend modeļu līnijām;
- local time vienmēr `Europe/Berlin`;
- “AI forecast” un “official warning” semantiski nošķirti.
