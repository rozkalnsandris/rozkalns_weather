# DWD warning refresh semantics

DWD remains the authoritative severe-weather warning source. WeatherNext/model output is never an official warning.

## Refresh triggers

The client requests `/api/warnings` on application startup, when network connectivity returns, when a hidden tab becomes visible again, and when the user explicitly refreshes warnings. Concurrent triggers share one in-flight request; they do not create duplicate warning fetches.

## Retrieval time versus source publication time

`retrieved_at_utc` is the weather app's successful warning-fetch time. It is used only to display how long ago the client last checked the warning endpoint. It is not the DWD CAP publication timestamp and does not prove a fixed DWD publication/update interval.

No fixed client-side freshness TTL is asserted. A cached successful DWD response is rendered as last-known/stale evidence until a new valid official DWD response succeeds. Only a fresh valid response can establish current `active` or `clear`; malformed/non-DWD responses and fetch failures cannot erase last-known warning evidence.

The warning controller refreshes on relevant lifecycle events instead of inventing an unverified DWD update cadence.
