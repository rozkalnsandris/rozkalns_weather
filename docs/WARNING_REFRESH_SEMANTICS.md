# DWD warning refresh semantics

DWD remains the authoritative severe-weather warning source. WeatherNext/model output is never an official warning.

## Refresh triggers

The client requests `/api/warnings` on application startup, when network connectivity returns, when a hidden tab becomes visible again, and when the user explicitly refreshes warnings. Concurrent triggers share one in-flight request; they do not create duplicate warning fetches.

## Retrieval time versus source publication time

`retrieved_at_utc` is the weather app's successful warning-fetch time. It is used only to display how long ago the client last checked the warning endpoint. It is not the DWD CAP publication timestamp and does not prove a fixed DWD publication/update interval.

No fixed client-side freshness TTL is asserted. A cached successful DWD response is rendered as last-known/stale evidence until a new valid official DWD response succeeds. Only a fresh valid response can establish current `active` or `clear`; malformed/non-DWD responses and fetch failures cannot erase last-known warning evidence.

The warning controller refreshes on relevant lifecycle events instead of inventing an unverified DWD update cadence.

## Human-readable warning content

The primary Warnings surface renders the normalized official DWD evidence as readable text: headline, severity, lifecycle, effective/onset and expiry times, description, instruction, DWD authority, transport attribution, and the privacy-safe `reference_location` supplied by the API contract.

`reference_location` is the public reference point used for the warning query. It is labelled **Reference location** and must not be presented as the warning's affected area. The current normalized backend contract does not expose a defensible per-alert affected-area field or per-alert official source URL, so the client must not invent either field.

The raw warning payload remains available only in an optional `Technical warning JSON` `<details>` disclosure for diagnostics. The primary user-facing warning content must not be a JSON dump. All displayed warning strings and diagnostic payloads are assigned with `textContent`; warning payload text is not injected as HTML.
