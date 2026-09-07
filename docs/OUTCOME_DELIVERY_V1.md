# Outcome Delivery v1 — rozkalns_weather

Status: **ACTIVE after merge to main**
Machine contract: `.github/outcome-delivery-v1.json`

Optimize for time from approved outcome to verified outcome, not PR count. Default unit:

```text
one outcome issue
  -> one outcome branch
  -> 2-5 closely related same-risk work items
  -> one Outcome PR
  -> required CI/review convergence
  -> one merge decision model
  -> optional separately authorized bounded LIVE
  -> verified outcome
```

Keep implementation, wiring/integration, focused tests, operator/preflight and docs/provenance together when they are required for one independently useful outcome. Split only for an independently valuable outcome, different risk/trust boundary, different runtime target/owner decision or genuine reviewability boundary.

Native stacked PRs are not the default because current policy forbids force/history rewrite and GitHub stack maintenance relies on rebases/force-with-lease. Do not weaken main rules for throughput.

FAST requires separate exact `MERGE rozkalns_weather #<pr> HEAD=<sha>` authorization. AUTO-RUN FULL v2 activation is already issue-scoped merge authority for its frozen canonical Outcome PR, subject to fresh exact-head diff, required CI, review/thread, mergeability and ruleset checks.

Merge never authorizes weather LIVE. RPi5 deploy/runtime, Docker/systemd/timers, private configuration, credentials, Google/BigQuery access, Cloudflare and production SQLite/corpus mutation remain separate exact gates under current repository/trust-boundary rules.

Every terminal work-cycle response ends with exactly one command: genuine owner gate -> exact ACTION REQUIRED command; waiting mutable state -> `SYNC rozkalns_weather`; safe same-scope continuation -> `turpini`; completed outcome -> `START rozkalns_weather`.
