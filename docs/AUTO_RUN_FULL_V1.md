# AUTO-RUN FULL v1 — compatibility contract

Status: **COMPATIBILITY; v2 is canonical**

Machine contract: `.github/auto-run-full-v1.json`
Roadmap: `rozkalns_weather#8`
Durable controller: `rozkalns_weather#9`

`AUTO-RUN FULL rozkalns_weather #<issue>` is explicit issue-scoped authority. It is never inferred from `START`, `SYNC`, `turpini`, chat history, controller state or a previous receipt. GitHub is the durable state and authorization plane.

The frozen activation may carry routine source analysis, edits, tests, branch/commit/push, Outcome PR creation/update, CI/review correction and exact-head merge for that exact issue without repeated owner nudges. A changed head requires fresh readiness evidence but does not widen scope.

Weather LIVE authority remains separate. The command does not by itself permit RPi5 deploy/runtime mutation, Docker/systemd/timers, `.env`, secrets/credentials, Google Cloud/BigQuery private access, Cloudflare, production SQLite/corpus writes, filesystem permissions or arbitrary host/root/sudo/shell work. Current `AGENTS.md`, v2 policy and `RPi5_main` trusted runtime boundary are authoritative where stricter.

Three materially identical failed attempts without a new safe hypothesis produce `STOP_ERROR`. Real new scope or trust-boundary authority produces `STOP_SCOPE_OR_RISK`.

V1 remains only for compatibility and historical receipt interpretation. New activations use v2.
