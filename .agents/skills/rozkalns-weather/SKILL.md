---
name: rozkalns-weather
description: Use for repository-specific work in rozkalnsandris/rozkalns_weather: WeatherNext/DWD/ECMWF provider work, forecast provenance, FastAPI/UI changes, verification, GitHub workflow, AUTO-RUN FULL routing, and deploy-gate preparation. This skill never grants merge or LIVE authority.
---

# rozkalns_weather workflow

Follow repository `AGENTS.md` first. This skill is guidance only and must never weaken or replace repository authority.

## 1. Resolve authority before work

1. Read `AGENTS.md` and `.github/start-mode-routing.json`.
2. Identify the exact current user command and do not infer a stronger mode from chat history, controller state, issue names, deploy queues, or old receipts.
3. Refresh current `main` and only the issue/PR/CI/review state required for the current work item.
4. For explicit `AUTO-RUN FULL rozkalns_weather #<issue>`, read `.github/auto-run-full-v2.json`, `docs/AUTO_RUN_FULL_V2.md`, the exact issue/DoD, controller state, and current relevant PR/CI/review state before any activation write.
5. Treat GitHub as canonical for mutable project state.

Never use this skill itself as merge, LIVE, retry, rollback, cleanup, credential, permission, production-data, or runtime authority.

## 2. Preserve weather-domain invariants

- Keep WeatherNext 3 as a first-class `primary_research` provider.
- Preserve raw provider/model provenance: model version, init time, valid time, lead time, retrieval/publication time, and statistic/member where applicable.
- Keep provider adapters separate from normalization and verification logic.
- Never fabricate WeatherNext values or hide provider-level values behind a combined result.
- Preserve reproducible forecast history/snapshots.
- Treat DWD official warnings as the authoritative severe-weather warning source for Germany; never present experimental model output as an official warning.
- Keep data timestamps in UTC and UI presentation in `Europe/Berlin` where the repository contract requires it.

## 3. Protect privacy and production boundaries

Do not read, commit, log, or expose exact home coordinates, `.env`, API/Google/Cloudflare credentials, tokens, private runtime configuration, or sensitive logs/data.

Private RPi5 runtime/deploy, Docker/systemd/timers, Google Cloud/BigQuery private access, Cloudflare mutation, production SQLite/corpus mutation, filesystem ownership/permissions, root/sudo, host/network changes, and equivalent live actions remain STRICT unless separately and exactly authorized by the current repository contracts.

After a live mutation starts, an error, timeout, drift, or ambiguous result means preserve read-only evidence and STOP unless the exact recovery path was already authorized.

## 3a. Current deployment platform

For ordinary Weather application releases, treat Weather as a SIMPLE-DEPLOY v1 consumer. The canonical shared revision for issue #142 is `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c` and the reviewed generic host source is `RPi5_main@ff20fcf64ba62c95e5f15eeb481c3c66bb5c9708`. Weather may own only the tiny caller, `.simple-deploy.json`, Dockerfile/Compose application identity, health/readiness, persistence and exclusion contract.

Do not revive or extend the historical Weather broker/operator/queue/JIT/Composite chain as a current ordinary-release prerequisite. Before the one-time cutover, stricter existing LIVE rules remain in force; after successful activation only the reviewed `AUTO_DEPLOY_SAFE` application path may proceed automatically. Sensitive data/private/network/secret/host classes remain separately exact-gated.

## 4. Implement the smallest coherent source change

1. State the verified problem or acceptance target in one sentence.
2. Read only the source and tests that own that behavior.
3. Make the smallest coherent change; do not opportunistically redesign adjacent providers, UI, persistence, or automation.
4. Add or update a focused regression test when practical.
5. Run the narrowest relevant checks first, then broader repository checks only when required by the touched boundary or release gate.
6. Inspect the final diff for unrelated files, privacy leaks, generated artifacts, and secrets.

For UI/browser work, use the installed Playwright skill/CLI when available for functional verification, snapshots, console/network evidence, and visible-button flows. Do not persist browser auth/session state in Git.

## 5. Use current external documentation when semantics can drift

WeatherNext, Google Cloud, DWD, GitHub, Cloudflare, browser, and Codex capabilities can change. When behavior depends on current platform semantics, retrieve current authoritative documentation rather than relying on remembered syntax or old issue text.

## 6. Respect the active GitHub lane

- FAST may carry safe source/docs/tests/policy work through focused branch/commit/push, Draft PR, CI/review convergence, and Ready when `AGENTS.md` allows it.
- FAST merge remains a separate exact owner decision.
- FULL authority exists only after a valid exact issue-scoped activation and frozen receipt under the repository contract.
- Merge never implies Weather LIVE authority.
- Do not bypass rulesets, force-push, rewrite history, reset/rebase destructively, or invent recovery authority.

## 7. Report compactly with evidence

Return:

- problem/root cause or acceptance target;
- exact files changed;
- tests/checks and exact results;
- source/runtime evidence boundary;
- privacy/security/deploy impact;
- remaining uncertainty or blocker;
- the single next command required by the current `AGENTS.md` work-cycle contract.
