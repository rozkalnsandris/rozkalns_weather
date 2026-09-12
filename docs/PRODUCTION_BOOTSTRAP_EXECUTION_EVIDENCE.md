# Production bootstrap execution evidence validator

Issue #47 adds a deterministic source-side validator for sanitized evidence from a future separately authorized production public-corpus schema/bootstrap/backfill execution.

## Scope

The validator is verification-only. It does not initialize SQLite, advance checkpoints, perform backfill, retry writes, restore/delete data, inspect host paths, or create LIVE/data authority.

It is invoked as:

```bash
python -m rozkalns_weather.production_bootstrap_evidence \
  --source-sha <EXACT_MERGED_SHA> \
  --start YYYY-MM-DD \
  --end YYYY-MM-DD \
  --recovery-decision verified_backup_available \
  < sanitized-bootstrap-evidence.json
```

The source SHA, date window and recovery decision are first frozen through the existing `build_production_bootstrap_plan()` contract. Evidence is then validated against that exact plan.

## Bound identity

Sanitized evidence must bind all of the following:

- exact lowercase 40-character merged Weather source SHA;
- exact `bootstrap_fingerprint`;
- target alias `rozkalns-weather-public-rpi5`;
- sanitized database identity `rozkalns-weather-public-corpus-sqlite-v1`;
- exact start/end dates;
- exact deterministic model set `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- exact UTC run hours `00/06/12/18`;
- DWD WMO truth station `10416`;
- the exact previously selected recovery decision.

A filesystem database path is never an accepted identity.

## Schema evidence

Schema evidence must prove:

- `state=ready`;
- explicit `rozkalns-weather init-database` completion;
- no implicit migration.

This validator never runs that command itself.

## Checkpoint and count semantics

Truth chunks and each model's completed run list must be a duplicate-free ordered prefix of the frozen plan. Every section also declares its expected and present count; those counts must agree with the frozen plan and the reported completed-prefix length.

A clean incomplete prefix is `IN_PROGRESS`. It is not a failure and the validator does not advance it.

The following are fail-closed `BLOCKED` conditions:

- checkpoint/database divergence in either direction;
- interrupted-write evidence;
- duplicate/non-prefix checkpoints;
- expected/present count mismatch;
- unexpected runs;
- revision drift;
- wrong source/fingerprint/window/model/run-hour/station/recovery binding;
- missing final corpus-integrity proof at completion.

A complete prefix for truth and all three models plus `integrity.ok=true` is `PASS`.

## Privacy

Evidence is rejected when it contains private-path, credential/token/secret, raw-log, or `HOME_LAT`/`HOME_LON` style fields. The validator returns only stable reason codes and sanitized bound identities; it never echoes rejected private values.

## Authority

`PASS` and `IN_PROGRESS` are evidence classifications only. They do not grant:

- production SQLite/corpus write authority;
- retry authority after a failed mutation;
- automatic restore/delete/cleanup;
- RPi5 host/runtime, Docker/systemd or network authority.

Any future production write, retry, restart, rollback, restore or delete remains subject to the current exact owner gate and fail-closed rules.
