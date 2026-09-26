# FAST-LANE v2.3 work-cycle adoption — Weather canary

**Status:** source/governance canary for `ops-workflows#124`  
**Repository:** `rozkalnsandris/rozkalns_weather`  
**Accepted shared source:** `rozkalnsandris/ops-workflows@274d58f2d9d3cb86feded2751b8f9009a4501f6b`

This file is a thin consumer adoption adapter. It does not copy the shared implementation and it does not grant source, merge, LIVE, retry, rollback, cleanup, settings, credential, database, or runtime authority.

## Canonical shared contracts

The accepted shared revision provides:

- `docs/AGENT_WORK_CYCLE_V1.md`;
- `docs/GITHUB_API_ACCESS_V1.md`;
- `docs/WRITE_PREFLIGHT_COMPACT_V1.md`;
- `docs/AUTO_RUN_FULL_SINGLE_ISSUE_STATE_V2.md`.

Repository-local `AGENTS.md` remains authoritative and may be stricter.

## START / SYNC / continuation

Normal bare `START rozkalns_weather`:

1. reads `.github/agent-bootstrap.json`;
2. validates routing metadata and local stricter rules;
3. freshly reads current `main` and only the mutable GitHub facts needed to choose exactly one canonical lane;
4. automatically executes all immediately safe same-scope technical work;
5. stops only at a genuine owner gate, an external wait that cannot be safely advanced, a fail-closed error/drift/ambiguity, or DONE.

`SYNC rozkalns_weather` refreshes only the selected lane. `turpini` preserves the exact same scope and creates no new authority. `AUDIT-HANDOFF` remains an explicit deeper mode where supported.

A terminal work-cycle response is compact: `STATE`, at most four decisive `EVIDENCE` facts, `DONE`, optional `NOT DONE / BLOCKER`, and exactly one final actionable command. `ACTION REQUIRED` appears only for a real owner decision.

Weather's existing FAST merge rule remains unchanged: FAST source work may proceed through PR/CI/Ready, but merge requires a separate exact owner command. Explicit repository-local `AUTO-RUN FULL rozkalns_weather #<issue>` retains its own frozen issue-scoped merge semantics.

## WRITE_PREFLIGHT_COMPACT

Weather adopts the shared write-preflight extension through `.github/github-api-access-v1.json`; there is no second local write-preflight implementation.

Before deterministic GitHub object writes such as branch, PR, or durable controller/run creation:

- exact existing identity + exact intended state => `RECONCILE_OR_NOOP`;
- conflicting intent => `STOP`;
- stale writer/run => `STOP`;
- predictable duplicate mutation is not used as recovery.

The synthetic fixture `tests/fixtures/work_cycle_v23_write_preflight_cases.json` proves branch/PR/controller exact-match and collision dispositions without mutating GitHub.

## Normalized single-issue AUTO-RUN FULL state

Weather supports single-issue FULL, so new explicit FULL activations after this adoption use the shared normalized state ownership defined by `AUTO_RUN_FULL_SINGLE_ISSUE_STATE_V2`.

- target issue managed state owns run/work scope, phase, branch/PR pointers, correction count, blockers/gates and completion summary;
- controller owns only the one-writer lock / active issue+run pointer and transition identity;
- mutable CI/review/thread/mergeability facts are freshly read from GitHub;
- receipts are evidence only, not mutable control state;
- stale or out-of-order writers fail closed;
- exact replay is idempotent only when identity and resulting state are identical.

Controller issue `#9` and all historical receipts remain preserved. Its current legacy `IDLE` state is not rewritten by this rollout. The first future explicit FULL activation may materialize the normalized target/controller managed state only after fresh identity/scope preflight; any collision stops rather than overwriting legacy evidence.

This adoption does not activate Queue vNext `ops-workflows#96`.

## Deployment and safety boundary

`deployment_profile: simple-deploy` in the bootstrap manifest is routing metadata only. This rollout does not perform a SIMPLE-DEPLOY cutover, trigger production deployment, mutate RPi5 runtime, Docker/systemd, Cloudflare, credentials, or production SQLite/corpus data.

Weather privacy, provider provenance, DWD warning authority, exact LIVE/STRICT gates, and all repository-local stricter rules remain unchanged.
