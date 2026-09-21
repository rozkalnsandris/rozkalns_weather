# Production bootstrap execution evidence validator

The validator checks sanitized evidence from a future separately authorized production public-corpus bootstrap. It is verification-only: it does not initialize SQLite, advance checkpoints, perform provider backfill, retry production writes, restore/delete data, or create LIVE authority.

## Fixed identity after issue #159

The only accepted common bootstrap window is `2026-08-13..2026-08-26` with:

- benchmark location `station_05480`;
- DWD CDC truth station `05480`;
- deterministic models `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- run hours `00/06/12/18 UTC`;
- checkpoint namespace `fixed-window-20260813-20260826-v1`;
- a bootstrap fingerprint derived from the exact merged source SHA and fixed identity.

Pre-#159 fingerprints and the old `2026-04-02..2026-09-10` checkpoint are not reusable.

Invoke the source-side validator as:

```bash
python -m rozkalns_weather.production_bootstrap_evidence \
  --source-sha <EXACT_MERGED_SHA> \
  --start 2026-08-13 \
  --end 2026-08-26 \
  --recovery-decision verified_backup_available \
  < sanitized-bootstrap-evidence.json
```

## Bound evidence

Sanitized evidence must bind the exact source SHA, bootstrap fingerprint, target alias `rozkalns-weather-public-rpi5`, sanitized database identity, fixed dates, model set, run hours, `station_05480`, DWD CDC station `05480`, required truth-variable scope and selected recovery decision.

A filesystem database path is never an accepted identity.

## Schema and checkpoint evidence

Schema evidence must prove explicit `rozkalns-weather init-database` completion and no implicit migration.

Truth and each model must present duplicate-free ordered checkpoint prefixes. Each section's expected/present counts must match the fixed plan. Skip-ahead is not accepted.

A structurally clean incomplete prefix is `IN_PROGRESS`. It does not authorize an automatic retry or checkpoint advance. Completion requires all `56` runs for each deterministic model, the fixed truth chunk, and final corpus integrity PASS.

Fail-closed conditions include source/fingerprint/window/model/run-hour/station/recovery mismatch, checkpoint/database divergence, interrupted writes, duplicate/non-prefix checkpoints, unexpected runs, revision drift, count mismatch and missing final integrity evidence.

## Historical evidence

Rows from the old partial bootstrap remain immutable audit evidence. The execution validator binds only the new fixed common-window fingerprint; it never deletes, rewrites or relabels old rows.

## Privacy and authority

Evidence containing private paths, credentials/tokens/secrets, raw logs, or `HOME_LAT`/`HOME_LON` style fields is rejected without echoing private values.

`PASS` and `IN_PROGRESS` are evidence classifications only. They do not grant production writes, retry authority after a failed mutation, restore/delete/cleanup, RPi5 host mutation, Docker/systemd changes, recurring ingest, network changes or WeatherNext private access.
