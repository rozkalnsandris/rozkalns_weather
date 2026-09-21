# Production public corpus bootstrap contract

Issue #31 freezes source behavior for a later, separately authorized production SQLite bootstrap. This document does not authorize a database, corpus, host or runtime mutation.

## Current truth-transport gate

The first separately authorized #148 production truth attempt exposed a source-contract gap before any observation insert or checkpoint publication: the frozen Bright Sky `/weather` request for exact WMO `10416` and the first `2026-04-02..2026-04-15` chunk returned HTTP 404.

Issue #151 reviewed authoritative/public DWD metadata instead of retrying that request. The result is now frozen in `deploy/dwd-10416-historical-truth-decision.json` as `NO_VERIFIED_DWD_HISTORICAL_TRANSPORT`.

The reviewed evidence establishes all of the following without inventing an ID mapping:

- DWD publishes current forecast products under station namespace `10416`, including MOSMIX single-station products.
- DWD Climate Data Center (CDC) publishes versioned `historical/` and `recent/` observation archives using its own station identifiers and station-specific files.
- The reviewed CDC metadata did not provide an authoritative mapping from current WMO `10416` to a CDC station ID that covers the frozen `2026-04-02..2026-09-10` window. A legacy CDC Dortmund station ID `1032` exists in historical metadata but its listed coverage ends decades earlier and it is not treated as a mapping to current WMO `10416`.
- The operational DWD SYNOP product family is distinct from the CDC historical archive and was not verified as a 162-day exact-station archive for this bootstrap.
- Because exact station identity is unverified, the required truth-variable coverage (`temperature_2m`, `dew_point_2m`, `pressure_msl`, `relative_humidity_2m`, `wind_speed_10m`, `wind_gust_10m`, `precipitation_1h`, `cloud_cover`) is also not accepted as verified for the frozen exact-station window.

This is deliberately a **verification failure**, not a claim that DWD can never expose such data. It means the repository has no reviewed, evidence-backed DWD transport that satisfies the exact `station_10416` historical contract today.

The production descriptor therefore remains fail-closed with `SOURCE_BLOCKED_NO_VERIFIED_DWD_HISTORICAL_TRANSPORT`, `transport=none_verified`, `live_backfill_allowed=false`, and an explicit reference to the decision contract. The existing `production-bootstrap-plan` also remains blocked by `TRUTH_TRANSPORT_HISTORICAL_CAPABILITY_UNVERIFIED`; it must not be interpreted as LIVE/data-write readiness.

Do not retry the same Bright Sky historical request, infer a CDC station ID from WMO `10416`, select the nearest station, substitute a different station, synthesize observations, or silently change truth provider. Any truth-policy or benchmark-station change is a separate owner decision and source issue.

Official evidence reviewed for #151:

- `https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/10416/kml/`
- `https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/air_temperature/`
- `https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/subdaily/wind/timeseries_overview/ZeitReihen_fk_termin_GE_30Jahre_DK_TER.html`
- `https://opendata.dwd.de/weather/weather_reports/synoptic/germany/`

## Frozen first-bootstrap scope

- benchmark location: `station_10416`; DWD truth station: WMO `10416`;
- common archive start: `2026-04-02`;
- first rollout source window: `2026-04-02..2026-09-10` (162 inclusive days, hard maximum 180);
- forecast models: exactly `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- forecast cycles: exactly `00/06/12/18 UTC`;
- truth chunks: exact 14-day chunks, final chunk shortened only at the requested end date, but no truth write is allowed until a verified transport exists.

`deploy/production-public-corpus-bootstrap.json` is the machine bootstrap contract. `deploy/dwd-10416-historical-truth-decision.json` is the machine evidence/decision contract for the historical truth blocker. `build_production_bootstrap_plan()` produces a deterministic fingerprint over source SHA, bounds, station, models, run hours, truth transport state and owner recovery decision. Source planning grants no production-data authority and remains blocked by the historical truth-transport gate.

## Schema and backfill separation

Schema initialization is an explicit mutation: `rozkalns-weather init-database`. Historical backfill must start only after the required schema already exists and is ready. `python -m rozkalns_weather.backfill` must not implicitly initialize or migrate a database.

This means an old/incomplete production schema is a STOP condition. A future schema migration must be separately reviewed and authorized; a backfill command may not silently turn into a migration.

## Checkpoint and resume semantics

Checkpoint files use schema version 1 and atomic temporary-file replacement. Completed entries must be unique and form the exact ordered prefix of the requested truth chunks or forecast runs. Skipping ahead, unknown entries, duplicate checkpoint entries or a changed bootstrap fingerprint fail closed.

A crash after a database insert but before checkpoint publication is treated as an interrupted checkpoint. Same-payload forecast insertion remains idempotent through immutable payload-hash dedupe, but source validation does not silently repair or advance the checkpoint. Fresh resume evidence is required. If a repeated upstream run changes payload and creates a revision, production bootstrap integrity is blocked as revision drift rather than rewriting history.

## Integrity and destructive behavior

Completion requires zero missing runs, zero unexpected runs and zero revision drift for each frozen deterministic model, plus the complete exact-station truth chunk prefix from a separately reviewed transport. Immutable forecast snapshots remain mandatory.

There is no automatic delete, restore, cleanup, repair or SQLite rollback. Backup/restore is a separate mutation class. Application rollback never implies corpus rollback.

## Next owner decision

#151 does not authorize a replacement station or provider. Parent #148 remains blocked until the owner explicitly chooses a new truth-policy or station strategy, after which a separate source issue must review that choice and only then may production planning become write-ready.

Before another production corpus-write authorization is requested, source must contain an evidence-backed truth transport for the explicitly approved benchmark identity/policy. A fresh production bootstrap authorization must bind the reviewed merged Weather SHA and exact-SHA CI, exact production SQLite target, start/end dates, station, all three models, `00/06/12/18 UTC`, recovery decision, checkpoint fingerprint, verification postconditions and failure semantics. Any runtime/host/Docker/systemd mutation remains separately governed by the trusted `RPi5_main` boundary.
