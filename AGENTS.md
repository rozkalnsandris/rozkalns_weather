# AGENTS.md

## Source of truth
GitHub is canonical for source, tests, reviews, CI and release metadata. Live RPi5 is canonical only for deployed/runtime state.

## Product
This repository is a **simple private weather app** for the Dortmund-Wickede area.

Keep only what directly supports:
- current weather;
- hourly and daily forecasts;
- ICON-D2, ECMWF IFS and ECMWF AIFS comparison;
- WeatherNext 3 as optional research data;
- DWD official warnings;
- DWD/Bright Sky radar/nowcast;
- basic forecast accuracy against DWD CDC station 05480;
- provider freshness/status;
- a mobile-first PWA;
- one simple RPi5 deployment path.

Do not rebuild a project-local deployment platform, controller, queue, receipt system or rollout state machine.

## Safety and privacy
- DWD remains the authoritative severe-weather warning source in Germany.
- WeatherNext/model output is never an official warning.
- Never commit exact home address, HOME_LAT, HOME_LON, .env, credentials, tokens or private runtime logs.
- Preserve provider/model/init/retrieval/valid/lead/statistic provenance for stored forecasts.
- Store timestamps in UTC; display in Europe/Berlin.
- Do not fabricate WeatherNext values.

## Data model
Use Python + FastAPI + SQLite. Forecast history is immutable because verification needs historical model snapshots. Provider failures must be isolated.

Canonical measured benchmark: station_05480 / DWD CDC 05480.
Private home: forecast/radar display location only unless a defensible home observation truth source is added.

## Work flow
Read this file, README.md, docs/ROADMAP.md and current main before repository work.

START / SYNC / turpini use FAST-LANE v2.2:
- safe source/docs/tests work may continue through branch, commit, PR, CI/review correction and Ready;
- merge always requires an explicit owner MERGE command;
- merge does not imply arbitrary LIVE authority.

AUTO-RUN FULL activates only with an explicit `AUTO-RUN FULL rozkalns_weather #<issue>` command and uses the small local contract in `.github/auto-run-full-v2.json`.

Separate explicit LIVE authority is still required for secrets/credentials, Cloudflare/network, DB/schema/data mutation, systemd/host changes and non-standard runtime changes.

Ordinary application releases use shared SIMPLE-DEPLOY. Do not add another Weather-specific deploy chain.
