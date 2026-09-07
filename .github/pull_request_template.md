## Outcome

- Observable outcome / Definition of Done:
- Refs issue/work item:
- Delivery mode: FAST-LANE / AUTO-RUN FULL
- If FULL: activation receipt + frozen issue:

## Scope

- Implementation / wiring included:
- Tests / operator-preflight included:
- Docs / provenance included:
- Why this is one coherent Outcome PR:

## Safety

- [ ] No exact home address, `HOME_LAT`, `HOME_LON`, `.env`, credentials or protected runtime data is included.
- [ ] WeatherNext real values are not fabricated and model output is not presented as official DWD warning authority.
- [ ] Provider provenance / immutable forecast-history semantics are preserved where relevant.
- [ ] No production/runtime/Cloudflare/credential/DB-corpus mutation is performed by this PR.
- [ ] No force-push/history rewrite/ruleset bypass is required.

## Validation

- [ ] Exact-head tests/CI are green.
- [ ] `FAST-LANE Merge Gate` is green.
- [ ] Final diff/scope review matches the issue/outcome.
- [ ] Reviews / unresolved threads are converged.
- [ ] Mergeability and current base/head were freshly checked.

## Runtime classification

Production/live change REQUIRED: NO

If YES later, source merge does not authorize LIVE; bind exact reviewed SHA, target and mutation class under the separate current weather/RPi5 trust-boundary contract.
