# FAST-LANE v2.2 Composite — rozkalns_weather

This is the active local FAST-LANE startup contract for `rozkalnsandris/rozkalns_weather`.

Canonical shared decision record: `rozkalnsandris/ops-workflows/docs/FAST_LANE_V2_2_DECISION_RECORD.md`.
Machine policy: `rozkalnsandris/ops-workflows/policy/fast-lane-v2.2.json`.
The repository CI pins the shared reusable policy workflows to exact immutable `ops-workflows` commit `3836da03685e0feca9232d5ddb914497ac72a2f7`.

## Core rule

**The human approves the RISK / DECISION. Automation executes the TECHNICAL STEPS.** Read-only checkpoints never create owner gates; STRICT is a live-risk classification, not a prompt-per-command workflow.

## FAST

`START`, `SYNC`, `turpini`, or equivalent continuation may carry safe source/docs/test work from fresh canonical GitHub state through Draft PR, CI/review convergence and Ready. Up to two scope-preserving corrective commits are allowed. Closely related same-risk work may be batched when coherent. Merge remains explicit owner authority.

## Composite STRICT

Normal delivery has at most two owner gates: **MERGE**, then **COMPOSITE LIVE** only when deploy/runtime mutation is required. Before the live gate, gather all read-only evidence. The live authorization must bind exact SHA, target, allowed mutation categories, limits, exclusions and expected baseline where relevant.

For this weather repository, STRICT includes production/runtime deployment, service restart/reload, host/root mutation, secrets/credentials, exact private home coordinates, Cloudflare changes, database mutation and any other live state mutation.

## Weather-specific stricter rules

- Never commit exact home address, `HOME_LAT`, `HOME_LON` or credentials.
- DWD official warnings remain authoritative; WeatherNext output must never be presented as an official severe-weather warning.
- Preserve provider-level forecast provenance and immutable historical snapshots.
- Repository is public unless freshly proven otherwise; public-safe evidence only.

## Failure behavior

Authorization is consumed at the first authorized mutation. Any later error, ambiguity or drift requires evidence preservation and STOP. No automatic retry, rollback, cleanup or alternate mutation path unless explicitly pre-authorized.

Merge never authorizes deploy/runtime mutation.
