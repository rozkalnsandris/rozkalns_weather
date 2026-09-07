# AGENTS.md

## Source of truth

GitHub ir projekta canonical source of truth. Pirms darba nolasi šo failu, relevant README/docs/continuation, current `main`, un tikai current work item nepieciešamo issue/PR/CI/review state. Mutable SHA/status/authorization no chat history vai Memory nav authority.

## Project intent

Šis ir privātām mājas vajadzībām paredzēts weather dashboard/forecast-verification projekts Dortmund-Wickede apkārtnei. Galvenais pētniecības objekts ir **Google WeatherNext 3**, salīdzināts ar DWD un ECMWF.

## WeatherNext 3 priority

- WeatherNext 3 ir first-class `primary_research` provider, nevis dekoratīvs papildinājums.
- Saglabā raw provider/model provenance: model version, init time, forecast valid time, lead time, retrieval/publication time un statistic/member.
- Nedrīkst pārrakstīt vai izlīdzināt provider vērtības tā, ka salīdzinājums vairs nav reproducējams.
- Combined forecast nedrīkst slēpt provider-level prognozes.
- WeatherNext accuracy vērtē atsevišķi, tostarp lead-time buckets un model-version periods.

## Safety / warning authority

- WeatherNext ir eksperimentāla forecast sistēma, nevis official warning source.
- DWD CAP/oficiālie DWD brīdinājumi ir autoritatīvie severe-weather warnings Vācijā.
- UI nedrīkst prezentēt AI/model output kā oficiālu brīdinājumu.
- WeatherNext real values nekad nefabricē. Ja private access nav gatavs, saglabā explicit pending/error state.

## Privacy

- Necommitot precīzu mājas adresi, `HOME_LAT`, `HOME_LON`, `.env`, API/Google/Cloudflare credentials, tokens, private runtime config vai sensitive logs/data.
- Repo visibility pārbaudi pirms lokācijas detaļu pievienošanas.
- `.env.example` satur tikai tukšus/non-secret placeholderus.

## GitHub / runtime authority

- Pirms GitHub write nosaki exact repo, target, current base/head, operation un scope.
- `turpini` autorizē tikai safe FAST-LANE source-level continuation; tas neautorizē merge vai LIVE.
- FAST merge prasa atsevišķu exact owner komandu.
- Repository settings/rulesets/permissions/secrets/variables prasa atsevišķu exact owner authorization.
- Private RPi5 deploy/runtime, Docker/systemd/timers, `.env`, credentials, Google Cloud/BigQuery private access, Cloudflare, production SQLite/corpus write/migration/restore/delete, permissions/ownership un host/network mutation ir LIVE/STRICT un prasa exact authority saskaņā ar current weather + `rozkalnsandris/RPi5_main` trust boundary.
- Pēc pirmās autorizētās mutation kļūdas, timeout, drift vai ambiguity savāc tikai read-only evidence un STOP; bez jaunas authority nav retry/rollback/cleanup/alternate path.

## Implementation principles

- Minimum-sufficient architecture: Python/FastAPI + SQLite + viegls web/PWA.
- Provider adapters tur atsevišķi no normalization/verification slāņa.
- Forecast snapshot/history ir reproducējams un netiek klusām pārrakstīts.
- Provider failure ir izolēts; citu provider data nedrīkst pazust.
- Data layer timestamps ir UTC; UI timezone `Europe/Berlin`.
- Vienības normalizē konsekventi un katram datu punktam saglabā provenance.
- Weighted Combined forecast paliek ārpus scope, kamēr nav pietiekama verification corpus, transparent versioned weights un backtest.

## Startup command routing

Pirms mode izvēles nolasi `.github/start-mode-routing.json`.

- Bare `START`, `START rozkalns_weather`, `SYNC rozkalns_weather`, `turpini` => **FAST-LANE v2.2**.
- `GITHUB-ONLY` un `LIVE-ALL` aktivizējas tikai ar explicit current-command tokenu.
- `AUTO-RUN FULL` aktivizējas tikai ar exact explicit `AUTO-RUN FULL rozkalns_weather #<issue>` un pēc tam jālasa `.github/auto-run-full-v2.json` + `docs/AUTO_RUN_FULL_V2.md`.
- Neinferē režīmu no issue nosaukuma, controller state, deploy queue, historical chat, executor availability vai veca receipt.

<!-- BEGIN FAST-LANE-V2.2-MANAGED -->
## FAST-LANE v2.2 Composite

Read `docs/FAST_LANE_V2_2.md` as active local FAST contract. Canonical shared policy is pinned from `rozkalnsandris/ops-workflows` and checked by CI.

- Human approves risk/decision; automation executes safe technical steps.
- FAST is discovery/audit/non-FULL continuation and may carry source/docs/tests/policy through Draft PR, CI/review convergence and Ready.
- Batch 2-5 closely related same-risk items when that creates one coherent outcome; up to two scope-preserving corrective commits.
- Read-only validation, CI/review inspection, exact-head/diff checks and safe corrections are not owner gates.
- FAST merge remains a separate exact owner decision. Merge never implies LIVE.
- STRICT includes private RPi5 runtime, credentials, host/root, Cloudflare, production DB/corpus and equivalent live authority.
- Authorization is consumed at first authorized mutation; later error/ambiguity/drift => evidence + STOP unless recovery was pre-authorized.

Weather privacy, provider provenance and DWD warning authority remain stricter where applicable.
<!-- END FAST-LANE-V2.2-MANAGED -->

<!-- BEGIN AUTO-RUN-FULL-V2-MANAGED -->
## AUTO-RUN FULL v2

Canonical local contract: `.github/auto-run-full-v2.json` and `docs/AUTO_RUN_FULL_V2.md`. Outcome packaging: `.github/outcome-delivery-v1.json`. Durable controller: issue `#9`. Roadmap: issue `#8`.

- `AUTO-RUN FULL rozkalns_weather #<issue>` is the normal implementation lane and one explicit issue-scoped owner decision. It is never inferred from START/turpini/chat/controller state.
- Before activation freshly read repository rules, exact target issue/DoD, current `main`, active PR/CI/review state, relevant dependencies and controller #9.
- Materialize an owner-identity `rozkalns.auto-run-full-authorization.v2` receipt on the target issue before using FULL authority. Freeze repository, issue/DoD, source actions, merge authority, any already-declared live classes/targets, retry/rollback semantics and exclusions. Later issue edits never silently expand authority.
- Inside the frozen source envelope, analysis/source/docs/tests, branch/commit/push, canonical Outcome PR work, CI/review convergence and ordinary conflict correction without history rewrite require no additional owner nudge.
- The explicit FULL command is merge authority only for that frozen issue's canonical PR. Final exact-head scope review, required CI, reviews/threads, mergeability and ruleset requirements must all be fresh. Changed head invalidates readiness.
- Prefer GitHub native auto-merge only after final exact-head readiness and only if repository capability is enabled; otherwise use exact-head guarded direct merge fallback when supported. Never bypass rulesets, force merge, reset/rebase/force-push or rewrite history.
- Source FULL does **not** imply weather LIVE authority. Private RPi5 deploy/runtime, Docker/systemd/timers, `.env`, credentials, Google Cloud/BigQuery private access, Cloudflare, production SQLite/corpus mutation, filesystem/ownership, root/sudo/network changes remain separate exact gates unless a stricter current contract validly froze that exact class/target before mutation.
- WeatherNext real data must never be fabricated; DWD warning authority, privacy and provenance rules remain authoritative.
- Preferred resume is supported GitHub-event-triggered ChatGPT Work; hourly Scheduled Task is fallback/watchdog. Neither creates authority. `turpini` is resume-only.
- Three materially identical failures without a new safe hypothesis => `STOP_ERROR`.
- Normal terminal state is `DONE` only after DoD proof, exact post-merge main verification, final GitHub receipt and controller #9 return to `IDLE`.
<!-- END AUTO-RUN-FULL-V2-MANAGED -->

<!-- BEGIN GITHUB-ONLY-LIVE-ALL-V1-MANAGED -->
## GITHUB-ONLY / LIVE-ALL v1

Canonical shared contract: `rozkalnsandris/ops-workflows/docs/GITHUB_ONLY_LIVE_ALL.md` with machine invariants in `policy/github-only-live-all-v1.json`.

- `GITHUB-ONLY` permits fresh GitHub/source/docs/test/deploy-prep work but never the first live/runtime mutation.
- Deferred rollout state lives in public-safe `[DEPLOY-QUEUE]` issues in `ops-workflows`, never chat/Memory.
- Merge is separate explicit authority unless an exact active FULL contract supplies issue-scoped merge authority; merge never implies LIVE.
- `LIVE-ALL` snapshots only open READY queue items present at command start and revalidates exact SHA/target/baseline.
- Secrets/credentials, exact home point, Cloudflare, host/root, production DB/corpus and other stricter classes remain separately gated.
- After selected live mutation starts, error/ambiguity => evidence + STOP; no undeclared retry/rollback/cleanup/alternate path.
<!-- END GITHUB-ONLY-LIVE-ALL-V1-MANAGED -->

<!-- BEGIN START-GITHUB-ONLY-V1-MANAGED -->
## START_GITHUB_ONLY_V1 deterministic bootstrap amendment

Startup contract: `rozkalnsandris/ops-workflows/docs/START_GITHUB_ONLY_V1.md`. Repository manifest: `.github/start-github-only.json`.

- `START rozkalns_weather GITHUB-ONLY` refreshes local rules/README/roadmap, pinned shared policy, current default branch, active PRs/issues/dependencies and relevant deploy queue before selecting one canonical lane.
- Revalidate mutable GitHub state immediately before state-dependent writes.
- No open issue alone is not a STOP. Do not invent speculative work.
- Unresolved equally authoritative lanes => `AMBIGUOUS_CANONICAL_LANE`.
- Session-only executor availability never rewrites READY eligibility.
<!-- END START-GITHUB-ONLY-V1-MANAGED -->

<!-- BEGIN AGENT-WORK-CYCLE-V1-MANAGED -->
## Agent Work Cycle v1

Shared contract: `rozkalnsandris/ops-workflows/docs/AGENT_WORK_CYCLE_V1.md`; local rules may be stricter.

- START retrieves minimum-sufficient state for one lane: current rules, relevant README/roadmap/continuation, current default-branch SHA and only required issue/PR state.
- SYNC is incremental refresh, not repo-wide audit. `turpini` resumes same safe scope.
- For a current PR inspect exact head, required checks, reviews and unresolved threads; deepen only on failure/conflict.
- Safe FAST source work proceeds through Draft PR/CI/review/Ready. FAST MERGE remains explicit.
- FULL uses only its freshly activated frozen issue envelope.
- LIVE/deploy/runtime/credential/permission/production-data mutations require separate exact authority unless current stricter contract explicitly froze that class/target.
- Every terminal response ends with exactly one command: real owner gate => exact ACTION REQUIRED; waiting mutable state => `SYNC rozkalns_weather`; safe continuation => `turpini`; completed outcome => `START rozkalns_weather`.
<!-- END AGENT-WORK-CYCLE-V1-MANAGED -->
