# First public Web UI rollout readiness

Issue `#140` reconciles the already-implemented public PWA/API with the completed Weather-v9 recovery/control-plane closure. This document is a **source-side handoff**, not proof that Weather is deployed and not LIVE authorization.

## What is already ready in Weather source

The public-only UI path contains the Overview, Models, Accuracy and Warnings-Radar surfaces. Runtime packaging remains `deploy/docker-compose.public.yml` with:

- `WEATHER_RUNTIME_MODE=public-only`;
- `DATABASE_INIT_MODE=require-existing`;
- no WeatherNext private BigQuery credentials;
- no `HOME_LAT` / `HOME_LON`;
- DWD as the authoritative severe-weather warning source.

The Issue `#140` reconciliation anchor is Weather `main=9e903b0e1d129856c4b1533b48487b7f5c36737d`. That is a point-in-time source anchor only. The final LIVE candidate must be resolved again from the exact merged `main` after `#140`.

## Control-plane state at reconciliation

At the source reconciliation boundary on `2026-09-19`:

- `RPi5_main/main=84e129909831bd8111c4f4c1f6618b7fff2a803b`;
- the Weather-v9 recovery/control-plane lane is closed;
- the stale v7 delivery/install gate is superseded;
- `ops-workflows#46` is blocked specifically on Weather source-handoff reconciliation;
- no source snapshot is accepted as proof of current operator installation, current runtime baseline, deployment or readiness.

This repository intentionally does **not** freeze mutable host facts such as an `operator_host_installed=false` snapshot into `deploy/rollout-readiness.json`. The existing JIT preflight owns that proof.

## Required sequence after Issue #140 merge

1. Resolve the exact newly merged Weather `main` SHA.
2. Reconcile `ops-workflows#46` to that exact SHA under `ops-workflows` rules. The queue remains eligibility-only and grants no LIVE authority.
3. Refresh Weather and `RPi5_main` exact-SHA CI.
4. Collect fresh sanitized operator-installation proof and a fresh runtime baseline.
5. Run `rozkalns-weather rollout-live-preflight-validate`.
6. Only with zero blockers request a new bounded Composite STRICT LIVE authorization.
7. Under that separate LIVE gate, execute schema initialization, DWD truth + ICON-D2/IFS/AIFS corpus bootstrap, integrity checks, enable recurring public ingest **last**, and verify `/ready=200` plus UI/provider endpoints.

The source issue itself does not retarget the queue, does not create READY state, does not create or consume LIVE authorization, and performs no runtime mutation.

## JIT invariants

The machine gate still requires all of the following at evaluation time:

- exact current merged Weather SHA and green exact-SHA CI;
- exact current `RPi5_main` SHA and green required CI;
- matching `ops-workflows#46` `OPEN_READY` queue identity;
- fresh sanitized operator installation proof;
- exact-match runtime baseline token;
- fixed reviewed contract identities;
- bounded dates, exact model set/run hours and WMO `10416`;
- explicit recovery decision;
- exact release/supplemental/read-only budgets;
- owner/TTL/raw-body/replay authorization evidence.

Missing or stale evidence returns `BLOCKED`; source merge is never a substitute.

## WeatherNext and privacy boundaries

WeatherNext 3 remains `primary_research` and is not required for the first public-only Web UI. No WeatherNext values are fabricated. DWD remains warning authority.

Exact home coordinates, credentials, `.env`, private paths and raw runtime logs must not enter GitHub evidence. Production SQLite/corpus writes, systemd/Docker changes, Cloudflare/network changes and private WeatherNext/Google Cloud activation remain separate owner-gated mutation classes.
