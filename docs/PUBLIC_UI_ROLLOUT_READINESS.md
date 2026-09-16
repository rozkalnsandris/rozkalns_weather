# First public Web UI rollout readiness

Issue `#127` reconciles the already-implemented public PWA/API with the current external rollout dependencies. This document is a source-side handoff, not proof that Weather is deployed.

## What is already ready in Weather source

The public-only UI path already contains the Overview, Models, Accuracy and Warnings-Radar surfaces. The runtime packaging remains `deploy/docker-compose.public.yml`, with `WEATHER_RUNTIME_MODE=public-only` and `DATABASE_INIT_MODE=require-existing`. The public UI does not require WeatherNext private BigQuery credentials, `HOME_LAT`, `HOME_LON`, or a first real WeatherNext snapshot. DWD remains the authoritative severe-weather warning source.

The current source reconciliation anchor for `#127` is `26f704692c202827206cd370b5f5112864bb3b1b`. That SHA is evidence for this reconciliation only. A later LIVE decision must resolve the exact then-current merged Weather `main` and its exact-SHA CI again.

## Current external blockers — 2026-09-16 snapshot

`RPi5_main/main` was observed at `1741cfa076d00a11f609356fee37179226bb9753` with its exact-main CI green. The remaining public-operator recovery lane is `RPi5_main#543`; canonical PR `RPi5_main#545` is still open Draft at head `41d25c46cee40a2d0bee034a44c031b721df1740`, and that exact head currently has a failing `validate` check. Therefore Weather source cannot claim the required trusted public-runtime capability is ready for a fresh rollout.

`ops-workflows#46` is open in `STOP_ERROR` and still embeds Weather candidate `867b9dc82622bef55ffa2cb1a866c5206dfae74f`, not the current Weather source. Its prior failed/consumed authorization is historical evidence only and cannot be reused. Issue `#127` does not have authority to rewrite the shared queue or finish the separate `RPi5_main#543` lane.

A read-only host check in the `#127` activation session observed `rpi5` online with no Weather Docker container, Weather systemd service or Weather timer. That observation is point-in-time only. It did not re-check privileged operator installation state and must not be reused as a later LIVE baseline.

The machine-readable snapshot is `deploy/public-ui-rollout-reconciliation.json`.

## Required sequence before the UI can be deployed

1. Converge `RPi5_main#543` / PR `#545` under that repository's own authority and verify the required Weather public operator capability with fresh sanitized read-only host evidence.
2. Reconcile `ops-workflows#46` to the then-current exact Weather candidate. Do not reuse any failed or consumed authorization.
3. Refresh exact Weather and `RPi5_main` SHAs plus exact-SHA CI and a sanitized runtime baseline.
4. Run the existing `rollout-live-preflight-validate` path against those fresh inputs. Source snapshots do not substitute for this JIT evidence.
5. Only after the preflight passes, request one exact Composite STRICT LIVE authorization for the reviewed host/source/target/mutation envelope.

The actual deployment, Docker/systemd/timer changes, production SQLite initialization/backfill, WeatherNext private access, credentials, Cloudflare/network changes and any host mutation remain outside issue `#127`.

## Terminal classification for #127

Until the two external blockers above are resolved, the correct source outcome is `BLOCKED_EXTERNAL_RPI5_SOURCE_AND_QUEUE_RECOVERY`, not `READY_FOR_STRICT_LIVE`. This is intentionally fail-closed: source merge can improve continuity and prevent stale readiness claims, but it cannot manufacture host capability, queue eligibility or LIVE authority.
