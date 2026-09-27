# UI / UX

> **2026-09-26 plānotā attīstība:** [audits un ieviešanas plāns](audits/2026-09-26/README.md) sasaista 28 uzlabojumus ar sešiem izpildes posmiem. Zemāk saglabāta esošā #170 reference un sākotnējā specifikācija. Tās 10416/Combined/kvantiļu piemēri nav pierādījums pašreizējiem runtime datiem; aktuālās robežas un plānotā specifikācijas sakārtošana ir plānā. Overview izskata aktuālais lēmums: zemāk “Approved Overview A — 2026-09-27”; vecā #170 reference saglabāta vēsturei.

## Mērķis

Mobile-first privāts weather dashboard, kas informācijas ziņā ir tikpat ātri nolasāms kā tradicionāla weather app, bet papildus ļauj redzēt **modeļu atšķirības un WeatherNext 3 uncertainty/accuracy**.

Nav mērķa kopēt Meteo & Radar vizuālo dizainu. No tā izmantojam tikai ideju par:

- skaidru current section;
- hourly forecast;
- daily cards;
- ātri nolasāmiem precipitation/temperature indikatoriem.

## Historical consumer Overview visual reference — #170

Issue #170 consumer-weather implementation follows this approved mobile-first visual direction:

![Consumer weather Overview reference v1](./ui/consumer-weather-overview-reference-v1.webp)

Canonical asset: `docs/ui/consumer-weather-overview-reference-v1.webp`.

The reference fixes the intended **information hierarchy and visual direction**, not literal weather values. All temperatures, precipitation, conditions and model values visible in the mockup are illustrative UI placeholders only and must never be treated as real provider/WeatherNext data.

The implemented Overview should preserve these structural decisions:

- weather-first hero with large temperature, condition, feels-like and daily high/low;
- scannable next-hours forecast with temperature and precipitation;
- compact next-days forecast with min/max temperature range and precipitation;
- current-condition detail tiles;
- first-page `Model Snapshot` showing WeatherNext 3, ICON-D2, ECMWF IFS and AIFS side by side so disagreement is visible without opening `Models`;
- detailed provider/model analysis remains in `Models`;
- DWD warning state remains visually distinct and authoritative;
- `Overview`, `Models`, `Radar`, `Accuracy`, `Status` remain primary navigation destinations.

Provider-level values must remain attributable and must not be hidden behind a fabricated Combined value. WeatherNext 3 values are shown only when genuine data is available; otherwise the UI keeps an explicit pending/unavailable state.

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


## Approved Overview A — 2026-09-27

The owner approved the compact blue A variant for implementation, prioritizing Galaxy A55 and S25+ mobile layouts. This supersedes the #170 reference **for Overview appearance**; its source attribution and weather-first intent remain applicable. The #170 image above is historical evidence, not the current color/layout specification.

Implementation: `static/accepted_ui.css`, `static/ui_preferences.js`, `static/daily_trend.js` plus the existing API renderers. No backend, database or provider changes are required.

- Blue light/dark tokens, compact 14px cards, 70px mobile hero temperature, 54px hourly columns and 44px or larger primary controls. Model cards use two columns on mobile, four on desktop.
- Appearance selector: Auto / Light / Dark, persisted when browser storage is available. Auto uses **20:00–07:00 Europe/Berlin**, reevaluated each minute and on return to the tab. This is a fixed local-time schedule, not astronomical sunset. Provider daylight continues to govern weather icons independently.
- Daily min/max plot uses only one existing chosen provider's API aggregates, up to 14 returned days. Default is seven; 14-day control is disabled for shorter horizons. The actual available count is visible. Unknown values show `—`; temperature lines break on missing values and date gaps. Precipitation is mm, never probability.
- Day buttons expose the values to keyboard/screen-reader users; the expandable table includes init time/quality and retrieval timestamps. The daily provider/freshness surface remains visible. Hero high/low is today's forecast only, with no substitution from a later date.
- DWD warning summary is placed above the observation card. Its neutral unknown state makes no all-clear claim. Automatic loading, alert content and lifecycle remain technical-plan work.
- Service-worker shell cache advances to v11 and contains the new assets and previously omitted runtime/accuracy scripts.

Validation: dependency-free Node behavior tests cover theme boundaries including DST, provider separation, missing data, line gaps, source escaping and short horizons. Existing UI source contract tests remain. Local browser verification uses explicitly synthetic fixtures at 412px and 384px layout widths; this is not physical-device or production/RPi verification. The daily source table scrolls within the mobile card.

Follow-up stays with #237: full i18n, other-view redesign, radar, warning lifecycle, provenance expansion, API/loading and complete accessibility/performance acceptance. This Overview delivery does not close that epic or authorize deployment.
