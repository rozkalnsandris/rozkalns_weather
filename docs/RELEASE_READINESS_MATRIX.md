# Release-readiness acceptance matrix

Issue #53 introduces a deterministic, source-only acceptance matrix for the weather stack. The matrix aggregates already-sanitized capability evidence; it does not inspect the live RPi5, query production data, read private configuration, or grant any merge/LIVE/data/secret/network authority.

The executable contract is `src/rozkalns_weather/release_readiness.py` (`weather-release-readiness-matrix.v1`). It can be evaluated with:

```bash
python -m rozkalns_weather.release_readiness < sanitized-evidence.json
```

## Why there is no single global PASS

The project has four different readiness questions and they must not be collapsed into one state:

| Track | Meaning |
| --- | --- |
| `public_release` | Public-only source/runtime/corpus/provider/verification/reporting/PWA/DWD safety coherence |
| `weathernext_research` | WeatherNext 3 research readiness and no-fabrication boundary |
| `private_activation` | Later private-home + WeatherNext activation eligibility |
| `production_data_write` | Source-side readiness for a later, separately authorized production data mutation |

Each track is independently `PASS`, `WARN`, or `BLOCKED`. A public `PASS` therefore cannot be used as evidence that private activation or production data mutation is authorized or ready.

## Capability matrix

`public_release` contains:

- `source_contracts`
- `public_runtime`
- `public_corpus`
- `provider_health`
- `verification`
- `reporting_exports`
- `pwa`
- `dwd_safety_radar`

The remaining tracks contain `weathernext_research`, `private_home_runtime`, and `production_data_write` respectively.

The dependency graph is fail-closed. For example, a blocked `public_corpus` propagates to provider-health/verification-dependent capabilities, while a blocked `weathernext_research` blocks `private_home_runtime` without falsely blocking the independent public-release track.

## Required evidence properties

Every capability evidence record is bound to the exact matrix `source_sha`, includes an explicit `evidence_ref`, a UTC `checked_at_utc`, a bounded evidence TTL, a declared state, structured reason codes, and an exact invariant schema.

The matrix converts otherwise-positive evidence to `BLOCKED` when evidence is stale, from the future beyond the allowed skew, bound to another source SHA, missing, dependency-incomplete, or violates a required invariant. A `PASS` record containing warning/block reasons is rejected as contradictory input rather than silently normalized.

The short `handoff_summary` contains only track states plus public blocked/warn capability IDs. It intentionally does not carry mutable authorization, coordinates, credentials, host paths, raw provider payloads, or private runtime configuration.

## Safety invariants

The acceptance matrix enforces the following project boundaries:

- DWD remains the official severe-weather warning authority; model output may not substitute for an official warning.
- DWD radar remains distinct from model forecast output.
- WeatherNext 3 remains a first-class research model, and fabricated WeatherNext values are a hard blocker.
- Station `10416` remains the measured verification truth location; private-home display must not claim measured home accuracy.
- Forecast/history provenance must remain immutable where required, and provider-level provenance must remain explicit.
- Public runtime must stay `public-only` and independent of private runtime.
- The matrix itself never grants merge, LIVE/runtime, production-data, credential/secret, Cloudflare, or network authority.
- Exact home coordinates, credential material, private host paths, raw logs, SQL/query material, and related private fields are rejected by the evidence schema.

## Evidence producers

The matrix is an aggregator, not a replacement for existing evidence contracts. Relevant producers include `post_rollout_acceptance.py`, `provider_health.py`, `corpus_reporting.py`, `verification.py` / `verification_drilldown.py`, `monthly_public_report.py`, `map_validation.py`, `weathernext_access.py`, `weathernext_snapshot_admission.py`, and `private_runtime_activation.py`.

Callers should map those sanitized outputs into the exact capability invariants and provide evidence references that identify the source contract/report used. The matrix deliberately does not reach into live services or production storage by itself.

## Regression coverage

`tests/test_release_readiness.py` covers independent track states, mixed source SHAs, stale evidence, missing capability evidence, dependency propagation, private-field/path leakage, contradictory states, DWD authority drift, WeatherNext fabrication, immutable-corpus provenance drift, handoff-summary privacy, and unexpected invariant fields.

This contract is preparatory evidence only. Any later public rollout, private runtime activation, credential/configuration change, Cloudflare/network change, or production DB/corpus mutation remains subject to its separate exact owner gate and fresh read-only preflight.
