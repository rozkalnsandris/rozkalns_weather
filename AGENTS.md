# AGENTS.md

## Source of truth

GitHub ir projekta canonical source of truth. Pirms darba vienmēr nolasi šo failu, aktuālo README/docs, current `main`, aktīvo issue/PR un tikai attiecīgajam work item nepieciešamo CI/review stāvokli.

## Project intent

Šis ir privātām mājas vajadzībām paredzēts weather dashboard/verification projekts. Galvenais pētniecības objekts ir **Google WeatherNext 3**, salīdzināts ar DWD un ECMWF avotiem konkrētam mājas punktam Dortmund-Wickede apkārtnē.

## WeatherNext 3 priority

- WeatherNext 3 jābūt first-class provider, nevis dekoratīvam papildinājumam.
- Saglabā raw provider metadata: model version, init time, forecast valid time, lead time, retrieval time, statistic/member information.
- Nedrīkst pārrakstīt vai izlīdzināt WeatherNext vērtības tā, ka vairs nevar veikt reproducējamu salīdzinājumu ar citiem modeļiem.
- Combined forecast nedrīkst slēpt provider-level prognozes.
- WeatherNext accuracy jāvērtē ar atsevišķiem verifikācijas rādītājiem un lead-time buckets.

## Safety / authority

- WeatherNext ir eksperimentāla forecast sistēma, nevis oficiāls warning source.
- DWD CAP/oficiālie DWD brīdinājumi ir autoritatīvi severe-weather warnings Vācijā.
- UI nedrīkst prezentēt AI model output kā oficiālu brīdinājumu.

## Privacy

- Precīzu mājas adresi, `HOME_LAT`, `HOME_LON`, API credentials, Cloudflare credentials un citus privātus runtime parametrus necommitot.
- Repo pašreizējā redzamība jāpārbauda pirms jebkādu lokācijas detaļu pievienošanas.
- `.env` nedrīkst commitot; tikai `.env.example` ar tukšiem placeholderiem.

## GitHub workflow

- Pirms GitHub write nosaki precīzu repo, branch/target un darbību.
- `turpini` autorizē safe/read-only/source-level darbu līdz nākamajam Ready/STOP punktam; tas neautorizē merge/deploy/runtime mutation.
- Merge prasa atsevišķu skaidru lietotāja autorizāciju.
- Production/host/DB mutation, deploy, restart, secrets, permissions vai repository settings izmaiņas prasa atsevišķu skaidru autorizāciju.
- Pēc pirmās autorizētās mutation kļūdas vai būtiskas neskaidrības saglabā evidence un STOP; neveic automātisku alternate mutation path.

## Implementation principles

- Sāc ar minimum-sufficient architecture: Python/FastAPI + SQLite + viegls web/PWA.
- Provider adapters saglabā atsevišķi no normalization/verification slāņa.
- Saglabā gan forecast snapshot, gan observation truth data; nepārraksti vēsturiskos snapshotus ar jaunāku run.
- Laiki datu slānī glabā UTC; UI attēlo `Europe/Berlin`.
- Vienības normalizē uz SI/meteoroloģiski skaidru formu (`°C`, `mm`, `m/s` vai konsekventi izvēlēts display `km/h`, `hPa`).
- Katram datu punktam saglabā provenance.
- Provider failure nedrīkst izraisīt citas prognozes pazaudēšanu; UI rāda freshness/status.

## Out of scope until explicitly added

- Publisks weather service.
- Komerciāla izplatīšana.
- Automātiski severe-weather lēmumi tikai no WeatherNext.
- Sarežģīts ML ensemble weighting pirms pietiekama lokāla verification corpus.

<!-- BEGIN FAST-LANE-V2.2-MANAGED -->
## FAST-LANE v2.2 Composite

Read `docs/FAST_LANE_V2_2.md` as the active local startup contract. Canonical shared policy is pinned from `rozkalnsandris/ops-workflows` and checked by CI.

**Primary rule:** human approves the **RISK / DECISION**; automation executes the **TECHNICAL STEPS**.

- `START`, `turpini`, or equivalent continuation may carry source-only work through Ready when there is no live deploy/restart/runtime or trust-boundary activation.
- FAST may batch 2-5 closely related same-risk work items and use up to two scope-preserving corrective commits for CI/review findings.
- Normal delivery has at most two owner gates: explicit **MERGE**, then one bounded **COMPOSITE LIVE** only when deploy/runtime mutation is actually required.
- Read-only validation, evidence refresh, CI/review inspection, candidate verification and reconciliation are technical steps, not owner gates.
- Composite Live must bind exact SHA, target, allowed mutation categories, practical limits, explicit exclusions and expected baseline when relevant.
- Authorization is consumed at the first authorized mutation. Any later error, ambiguity or drift requires evidence preservation and STOP; no automatic retry, rollback, cleanup or alternate mutation path unless explicitly pre-authorized.
- **STRICT** includes production deploy, service/runtime mutation, secrets/credentials, host/root, Cloudflare and equivalent live authority.
- Merge remains explicit owner authority and never authorizes production deployment/runtime mutation.

Weather privacy, official-warning and provider-provenance rules above remain stricter where applicable.
<!-- END FAST-LANE-V2.2-MANAGED -->

<!-- BEGIN GITHUB-ONLY-LIVE-ALL-V1-MANAGED -->
## GITHUB-ONLY / LIVE-ALL v1

Canonical shared contract: `rozkalnsandris/ops-workflows/docs/GITHUB_ONLY_LIVE_ALL.md` with machine invariants in `policy/github-only-live-all-v1.json`.

- `GITHUB-ONLY` means fresh GitHub state and source/docs/test work through deploy preparation, but never the first live deploy/runtime mutation.
- Persist deferred rollout state as public-safe `[DEPLOY-QUEUE]` issues in `rozkalnsandris/ops-workflows`; chat or memory is never the queue.
- Merge remains separately explicit. Neither `GITHUB-ONLY` nor `LIVE-ALL` authorizes merge.
- A GitHub write whose deterministic side effect changes production/runtime counts as live work and must not run under `GITHUB-ONLY`.
- Queue `READY` requires final exact deployable SHA, exact target/entrypoint/preflight/verification/allowed mutations and no outstanding separate prerequisite owner gate.
- `LIVE-ALL` snapshots only open `READY` items present at command start, freshly revalidates exact SHA/target/baseline and may execute only ordinary predeclared live mutations inside that exact envelope.
- Secrets/credentials, host/root, Cloudflare infrastructure, exact home coordinates and equivalent separately gated authority remain excluded unless separately explicitly authorized.
- After any selected live mutation starts, error/ambiguity requires public-safe evidence preservation and STOP; no automatic retry/rollback/cleanup/alternate mutation path unless explicitly pre-authorized.
- Repository-local weather privacy and warning-source rules remain authoritative and stricter where applicable.
<!-- END GITHUB-ONLY-LIVE-ALL-V1-MANAGED -->

<!-- BEGIN START-GITHUB-ONLY-V1-MANAGED -->
## START_GITHUB_ONLY_V1 deterministic bootstrap amendment

Startup contract: `rozkalnsandris/ops-workflows/docs/START_GITHUB_ONLY_V1.md`.
Repository manifest: `.github/start-github-only.json`.

- `START rozkalns_weather GITHUB-ONLY` refreshes local rules/README/roadmap, pinned shared policy, current default branch, active PRs, active issues/dependencies and relevant deploy-queue items before selecting the canonical lane.
- Revalidate mutable GitHub state immediately before every state-dependent write.
- The absence of an open issue alone is NOT a STOP condition. Do not invent speculative work.
- If declared tie-breakers cannot resolve equally authoritative lanes, report `AMBIGUOUS_CANONICAL_LANE` instead of choosing arbitrarily.
- Final routing is one of `READY_FOR_MERGE`, `PARKED`, `STOP_ERROR`, `NEW_SCOPE_OR_RISK`, `AMBIGUOUS_CANONICAL_LANE`, or `IDLE`.
- `PARKED` is session-only. Executor availability is session capability, not READY rollout eligibility.
- Executor unavailability alone must not change READY to BLOCKED; use BLOCKED only for rollout eligibility or contract failure.
- Repository-local privacy, weather provenance and official-warning rules remain authoritative.
<!-- END START-GITHUB-ONLY-V1-MANAGED -->

<!-- BEGIN AGENT-WORK-CYCLE-V1-MANAGED -->
## Agent Work Cycle v1

Shared governance contract: `rozkalnsandris/ops-workflows/docs/AGENT_WORK_CYCLE_V1.md` with machine invariants in `policy/agent-work-cycle-v1.json`. Repository-local rules remain authoritative and may be stricter.

### Canonical state and minimum-sufficient retrieval

- GitHub is canonical for mutable source, branch, SHA, issue/PR, CI/review and authorization-continuity state. Never reuse mutable state from chat history without a fresh read.
- `START rozkalns_weather` bootstraps only enough state to identify one current work item/lane/gate: current `AGENTS.md`, README/roadmap or explicit continuation when relevant, current default-branch SHA, and only the issue/PR state required by that lane.
- For a current PR, inspect only the current exact head, required checks, reviews and unresolved threads unless a failure or conflict requires deeper evidence.
- `SYNC rozkalns_weather` is incremental refresh of the current lane, not a repo-wide audit.
- `turpini` resumes the same scope with incremental retrieval. It never creates MERGE, LIVE, retry, rollback, cleanup, credential, permission or runtime authority.
- Do not enumerate unrelated work or historical CI/log/comment/review history during normal START/SYNC. Broaden retrieval only demand-driven or under an explicit audit mode.

### Work execution and owner gates

- Prefer the smallest coherent fix and carry safe source/docs/tests/policy work through Draft PR, exact-head CI/review convergence and Ready when repository-local rules permit it.
- Technical intermediate steps such as CI polling, exact-head/diff checks, read-only preflight, evidence refresh and scope-preserving correction are not owner gates.
- MERGE remains an explicit owner decision unless a repository-local explicitly activated FULL mode grants issue-scoped merge authority. Merge never implies LIVE/deploy authority.
- LIVE/deploy/runtime/credential/permission/production-data mutations require separate exact authorization.
- Authorization is consumed at the first authorized mutation. After mutation begins, any error, timeout, drift, ambiguity or authorization uncertainty is fail-closed: collect only necessary read-only evidence and STOP. No retry, rollback, cleanup or alternate mutation without fresh explicit authority unless pre-authorized.

### Terminal response — exact next command

Every user-visible work-cycle response that ends or pauses repository work must finish with exactly one copy-pasteable command as the final actionable content.

- Use `ACTION REQUIRED` only for a genuine owner authorization/decision gate.
- When a real owner gate exists, output the exact authorization command with current issue/PR identifiers and exact SHA/target bindings where applicable.
- When no owner gate exists and mutable state must be refreshed, output `SYNC rozkalns_weather`.
- When no owner gate exists and same-scope safe technical continuation is immediately available, output `turpini`.
- When the current outcome is complete and no same-scope continuation remains, output `START rozkalns_weather`.
- Give exactly one recommended command, not a menu.
<!-- END AGENT-WORK-CYCLE-V1-MANAGED -->
