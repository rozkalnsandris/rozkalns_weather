# AUTO-RUN FULL v2 — event-driven issue-to-DONE orchestration

Status: **ACTIVE after merge to main**

Canonical machine contract: `.github/auto-run-full-v2.json`
Outcome packaging: `.github/outcome-delivery-v1.json` and `docs/OUTCOME_DELIVERY_V1.md`
Roadmap: `rozkalns_weather#8`
Durable controller: `rozkalns_weather#9`
Trusted runtime boundary: `rozkalnsandris/RPi5_main`

## Operating model

`AUTO-RUN FULL` is the normal implementation lane. FAST-LANE v2.2 remains discovery/audit/non-FULL continuation.

The owner starts one frozen issue with:

```text
AUTO-RUN FULL rozkalns_weather #<issue>
```

Default delivery is one frozen outcome issue -> one outcome branch -> 2-5 closely related same-risk work items -> one Outcome PR -> CI/review convergence -> guarded exact-head merge -> post-merge verification -> DONE.

Routine source work is technical execution, not a new owner gate. FULL may provide merge authority only for the exact frozen issue and canonical PR. Repository ruleset remains authoritative; no bypass, force merge, reset/rebase/force-push or history rewrite.

## Activation

Before activation freshly read `AGENTS.md`, `.github/start-mode-routing.json`, `.github/auto-run-full-v2.json`, `.github/outcome-delivery-v1.json`, exact target issue/DoD, current main, relevant PR/CI/review state, dependencies and controller #9. Activation fails closed if another issue is active.

Materialize an owner-identity target-issue receipt with schema `rozkalns.auto-run-full-authorization.v2`. Freeze repository, issue/DoD, allowed source actions, merge authority, any already-declared live classes/targets, retry/rollback semantics and exclusions. Later issue edits never silently expand authority.

## Resume architecture

GitHub is canonical. Preferred resume is GitHub event-triggered ChatGPT Work for supported PR activity. Fallback is one hourly ChatGPT Scheduled watchdog that reads controller #9 and stays silent while IDLE. A session ending, CI wait or review wait is resumable state, not failure. `turpini` is resume-only.

## Guarded merge

Before native auto-merge or direct exact-head fallback, freshly require: target/receipt match, canonical PR, exact current head, final diff/scope review, required CI green, zero unresolved actionable review findings, acceptable mergeability and ruleset satisfaction. A changed head invalidates readiness and requires fresh review/checks. Native stacked PRs remain disabled under current no-history-rewrite policy.

## Weather trust boundary

AUTO-RUN FULL is source+issue-scoped merge authority, not blanket LIVE authority. Merge never authorizes LIVE.

Private RPi5 deployment/runtime, Docker/systemd/timers, `.env`, exact home point, secrets/credentials, Google Cloud/BigQuery private access, Cloudflare, production SQLite/corpus mutation, filesystem permissions/ownership and host/root/sudo/network changes require separate exact authority under current weather and `RPi5_main` rules unless that exact mutation class/target was validly frozen by a stricter current contract before mutation.

WeatherNext real values must never be fabricated. DWD remains the authoritative severe-weather warning source. Provider provenance and immutable forecast history remain mandatory.

After any live mutation starts, only predeclared recovery is allowed. Otherwise error/ambiguity is `STOP_ERROR` with no retry/rollback/cleanup/alternate path. New authority class is `STOP_SCOPE_OR_RISK`.

## Completion

DONE requires target DoD proven from current evidence, exact post-merge main verification, final GitHub receipt and controller #9 returned to IDLE. Notify only on DONE, STOP_SCOPE_OR_RISK, STOP_ERROR or platform approval requiring owner action.
