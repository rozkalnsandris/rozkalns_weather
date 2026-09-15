# WeatherNext FINAL-LIVE PLAN — issue #125

**Next state: BLOCKED_BY_EXTERNAL_SOURCE_CAPABILITY.**

WeatherNext access approval is established by [#122](https://github.com/rozkalnsandris/rozkalns_weather/issues/122).
No real Google request, credential inspection, host operation or production SQLite
write was performed by #125. Approval is not evidence of a linked dataset or a
working private runtime. #122 remains the canonical private read-only first-access gate.

## Exact source bindings

The deterministic public-safe artifact is `deploy/weathernext-final-live-plan.json`.
Validate it offline with:

```bash
python -m rozkalns_weather.weathernext_final_live_plan --validate deploy/weathernext-final-live-plan.json
```

Weather SHA must be resolved to the exact merged main containing this plan and
bound to successful exact-SHA CI in the final #125 receipt. Embedding its own
future merge SHA in the file would be self-referential. The plan instead requires
fresh resolution before any later authorization.

Inspected `RPi5_main` source: `8182bb24545fd676843a9177e69177502c34214c`, merged
[PR #544](https://github.com/rozkalnsandris/RPi5_main/pull/544). Its exact-main
`validate`, `source-contract` and `deterministic-wheelhouse` checks passed during
source inspection. This is timestamped source evidence, not durable CI/runtime
truth. Refresh source/checks/reviews again before the next owner gate.

## Readiness evidence

| Stage | Classification | Executable proof or concrete gap |
|---|---|---|
| Private execution bridge | EXTERNAL_SOURCE_CAPABILITY_MISSING | `materialize_reviewed_runtime` explicitly is not wired into LIVE; no production call site was found in the relevant executor/scripts. A trusted identity-only dispatcher, artifact staging and exact Weather application source binding are required. |
| `weathernext_private_runtime_materialization` | SOURCE_READY | `weather_private_bigquery_runtime_materialization.py` validates and extracts a pinned offline closure. Its dedicated workflow builds the digest-bound artifact. The function is not installed/wired merely by merge. |
| `google_auth_binding` | EXTERNAL_SOURCE_CAPABILITY_MISSING | `weather_private_bigquery_contract.py` declares the class but `plan_later_owner_gate` returns execution-disabled metadata. No binding implementation is provided by the materializer. |
| `google_project_binding` | EXTERNAL_SOURCE_CAPABILITY_MISSING | Same contract-only gap; a class name does not bind private runtime state. |
| `analytics_hub_link_create` | EXTERNAL_SOURCE_CAPABILITY_MISSING | No reviewed linkage implementation; the materializer explicitly excludes Google control-plane operations. |
| `read_only_private_bigquery` | SOURCE_READY | Weather `read_first_access_canary` implements capped schema → exact-query dry-run → six-hour station canary → provenance/statistic validation. It still needs earlier private bindings and trusted dispatch plus #122 authorization. |
| Later `production_sqlite_forecast_snapshot_write` | SOURCE_READY | `prepare_first_snapshot_run` + admission validation + `Database.insert_forecast_run`; one snapshot preserves both native surfaces. Requires a separate exact data gate and trusted invocation, never included in #122. |

`SOURCE_READY` proves executable source, not an installed or authorized operation.
`LIVE_BINDING_REQUIRED` may be used only after the executable mechanism exists and
fresh evidence shows that private binding is the remaining work. Current auth/link
stages do not qualify merely because their names appear in a contract.

The dependency wheelhouse targets Linux/aarch64 CPython 3.13 / cp313. It contains
BigQuery dependencies, not an installation of the Weather application. A future
bridge must prove the actual Python baseline, application/dependency closure and
fixed artifact cache before using the materializer. Do not compensate with agent
sudo, arbitrary pip/apt, environment readout or a generic shell executor.

The open public Weather v7 delivery issue `RPi5_main#543` is a different capability;
its scope does not authorize private Google binding or WeatherNext access.

## Weather source proof

- `test_weathernext_first_access_execution.py`: exact SQL/init/location/hour binding;
  distinct dry-run surfaces; unknown/negative/over-cap estimates rejected; capped
  schema; disabled SDK retries; no SQLite use; exceptions stop the sequence;
  incomplete statistics, invalid lead provenance and out-of-window responses rejected.
- Existing access/admission tests now require the actual expected schema fingerprint
  and numeric dry-run evidence, rather than trusting `within_cap=true` alone.
- `test_api.py`: two native surfaces prepared as one immutable snapshot, idempotent
  disposable fixture insertion, complete native provenance retained, station-only
  hourly statistics visible without home config, no cross-location fallback, daily
  precipitation counted once using mean, and invalid location rejected.
- API defaults remain `home`; `location_id=station_10416` explicitly selects the
  benchmark forecast. PWA defaults to station when home is not configured, labels
  the selected point, separates cached locations and exposes p10–p90 uncertainty.
- Provider pending/failure remains isolated; WeatherNext is `primary_research`.
  DWD alone is the severe-weather warning authority. Station measured verification
  remains distinct from private-home forecast comparison.
- FINAL-LIVE PLAN tests reject extra/private fields, host/scope/cap/retry expansion,
  changed source bindings and failed CI. The validator never echoes rejected input.

All numeric test inputs are synthetic fixtures, not claimed real WeatherNext data.
Ordinary ingest/diagnose/fallback are not the bounded first-access entrypoint.

## Later authorization order

After the external source gap is resolved and reviewed, refresh this plan and bind
exact merged Weather/RPi5 SHA, CI, artifact digest/size/platform, trusted host alias
`rpi5`, fresh sanitized baseline, operation identities, mutation budgets, verification
and replay/expiry evidence. Only then can a final LIVE authorization be concrete.

Runtime materialization and private auth/project/link setup precede #122. First
access has one init, `station_10416`, `HOURS=6`, both product surfaces and an explicit
cap no greater than `1073741824` bytes/query; choose the smallest defensible real
cap from fresh matching dry-run evidence. Home scope and SQLite writes are disabled.
The first production snapshot write remains a later separate exact authorization.

After the first authorized operation, timeout/error/drift/lock/permission/schema/
cost/health ambiguity means sanitized evidence and STOP. No undeclared retry,
cleanup, rollback, credential substitution, alternate dataset or mutation path.
Private identifiers, credentials, exact home coordinates, raw values and runtime
logs never belong in the plan or GitHub receipts.

## One next owner command

This authorizes one external source issue and Draft PR for the missing private
bridge/binding mechanisms after fresh `RPi5_main` rules and state checks. It does
not authorize merge, install, private Google access or host mutation.

```text
AUTHORIZE RPi5_main WEATHERNEXT-PRIVATE-EXECUTION-BRIDGE CREATE-ONE-SOURCE-ISSUE-AND-DRAFT-PR NO-MERGE NO-LIVE
```
