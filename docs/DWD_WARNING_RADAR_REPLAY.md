# DWD warning and radar replay

`dwd-warning-radar-replay-v1` is a source-only, fixture-driven safety regression harness for the DWD warning and radar/nowcast surfaces.

It exists so warning lifecycle, radar degradation and PWA/API presentation transitions can be tested deterministically without live DWD access, private runtime access or a real home point.

## Authority boundary

DWD remains the official severe-weather warning authority. Replay evidence never promotes model output, including WeatherNext, into an official warning. Radar evidence is explicitly `radar_observed` / `radar_nowcast` and remains separate from model forecast output.

The replay orchestrator delegates geometry, lifecycle, radar freshness/horizon and UI-separation checks to the existing `live-map-validation-v1` validator. It does not create a second warning-authority implementation.

## Input

A replay scenario contains:

- a safe scenario identifier;
- synthetic injected `location` and `map_bounds` coordinates;
- strictly increasing UTC replay steps;
- warning actions: `issue`, `update`, `cancel`, `expire`;
- optional radar frame snapshots containing only `radar_observed` and `radar_nowcast` evidence accepted by the map validator.

Synthetic coordinates and warning geometry are validation inputs only. They are never returned in replay output.

The canonical regression fixture is `tests/fixtures/dwd_warning_radar_replay.json`. It exercises:

1. warning issue with fresh observed + nowcast radar;
2. warning update plus overlapping second warning;
3. geometry update moving one warning away from the synthetic map point, with stale/missing-nowcast radar;
4. explicit expiry plus missing radar frames;
5. cancellation and radar recovery;
6. final warning removal with fresh radar.

## Output

Each replay step emits only sanitized machine-readable evidence:

- `PASS`, `WARN` or `BLOCKED`;
- stable blocking/warning reason codes;
- warning and radar counts;
- privacy-safe `api_state` and `pwa_state` projections;
- DWD authority and model/radar separation presentation evidence.

The overall result also includes a deterministic SHA-256 identity of the input scenario, event counts and explicit proof that no network access, runtime mutation or LIVE authority was used.

Replay output intentionally omits coordinates, geometry, credentials and raw warning/radar payloads.

## Failure semantics

Invalid event order or malformed replay structure fails closed with `REPLAY_*` reason codes. Examples include update/cancel/expire without a base warning, duplicate issue, non-increasing replay time and malformed radar-frame input.

The underlying map validator reason codes are preserved, including `RADAR_OBSERVED_STALE`, `RADAR_OBSERVED_MISSING`, `RADAR_NOWCAST_MISSING`, warning geometry/lifecycle failures and DWD-authority separation failures.

## Running locally

The harness reads one scenario from stdin and writes sanitized JSON evidence to stdout:

```bash
python -m rozkalns_weather.dwd_replay < tests/fixtures/dwd_warning_radar_replay.json
```

Exit status is `2` only for an overall `BLOCKED` replay; `PASS` and `WARN` are valid replay outcomes.

## Later live-map comparison boundary

A future runtime validation may compare **sanitized** live evidence with this source contract, but that requires the applicable separate runtime/LIVE authorization. The comparison should bind:

- the reviewed source SHA containing this contract;
- `contract_version=dwd-warning-radar-replay-v1` and delegated `live-map-validation-v1` semantics;
- sanitized warning/radar state and reason-code classes only;
- proof that DWD remains official warning authority and radar remains distinct from model forecast output.

That future validation must not copy the private point, raw geometry, credentials, private runtime paths or raw provider payloads into GitHub evidence. This source issue does not authorize live polling, Cloudflare/network changes, deployment, production data mutation or any WeatherNext warning substitution.
