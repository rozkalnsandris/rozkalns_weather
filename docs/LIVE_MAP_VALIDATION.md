# Live map validation contract

`live-map-validation-v1` is a source-only, network-independent harness for the later private home-centered DWD warning/radar map validation. It does not fetch live data, persist coordinates, mutate runtime state, or grant LIVE authority.

## Authority and separation

- DWD official warnings remain the severe-weather warning authority in Germany.
- Warning evidence must identify `authority=DWD`, `official=true`, and `kind=official_warning`.
- Forecast/model output, including WeatherNext, must never substitute for or be styled as an official DWD warning.
- Radar observed/nowcast is validated as a separate DWD-derived layer and is explicitly not model-forecast output.
- The packaged PWA must retain the dedicated warning panel and the textual distinction between warnings, radar and model forecasts.

DWD publishes CAP warning data separately from radar products. The source contract therefore validates CAP geometry/lifecycle independently from radar observed/nowcast freshness.

## Privacy boundary

The private point is injected only in the validator input. It is used in memory to test map bounds and warning-polygon coverage and is never copied to the output. Warning geometry and raw provider payloads are also excluded from output evidence.

The output privacy contract always reports:

```json
{
  "coordinates_exposed": false,
  "geometry_exposed": false,
  "credentials_exposed": false,
  "raw_payload_exposed": false
}
```

Do not commit a real home point or captured private runtime evidence. Tests use synthetic coordinates only.

## Invocation

Run from a reviewed source checkout:

```bash
python -m rozkalns_weather.map_validation \
  --now 2026-09-12T10:00:00Z \
  < sanitized-map-evidence.json
```

The validator performs no network access and no runtime mutation. `--now` is explicit so fixtures and later operator evidence are reproducible.

A minimal **synthetic** input shape is:

```json
{
  "location": {"lat": 50.0, "lon": 8.0},
  "map_bounds": {"south": 49.0, "west": 7.0, "north": 51.0, "east": 9.0},
  "warnings": {
    "authority": "DWD",
    "official": true,
    "kind": "official_warning",
    "alerts": [
      {
        "identifier": "fixture-warning-1",
        "sent": "2026-09-12T09:00:00Z",
        "effective": "2026-09-12T09:00:00Z",
        "expires": "2026-09-12T12:00:00Z",
        "lifecycle": "active",
        "polygon": "49.5,7.5 49.5,8.5 50.5,8.5 50.5,7.5 49.5,7.5"
      }
    ]
  },
  "radar": {
    "not_model_forecast": true,
    "frames": [
      {"timestamp": "2026-09-12T09:50:00Z", "kind": "radar_observed"},
      {"timestamp": "2026-09-12T10:30:00Z", "kind": "radar_nowcast"}
    ]
  }
}
```

The coordinates above are test fixtures and are not a private home location.

## PASS / WARN / BLOCKED

`PASS` means the injected point is inside map bounds, warning authority/lifecycle/geometry is internally consistent, radar evidence is usable, and the packaged PWA preserves warning/radar/model separation.

`WARN` is reserved for degraded-but-interpretable evidence such as missing radar evidence, a missing nowcast layer, an observed radar frame older than the project freshness tolerance, or warning geometry outside the current map viewport. Warning states do not alter provider data.

`BLOCKED` is used for privacy/identity/authority/geometry/lifecycle/bounds/radar-contract contradictions, including absent injected coordinates, invalid map bounds, a map center outside the viewport, non-DWD official-warning claims, malformed or colliding warning revisions, malformed polygons, model/radar conflation, future "observed" radar, malformed frame time/kind, or nowcast horizons beyond the supported envelope.

Machine-readable reason codes are stable output; alert identifiers, coordinates and geometry are not output.

## Warning lifecycle and revisions

The harness accepts either:

- CAP polygon strings in CAP order `lat,lon lat,lon ...`; or
- GeoJSON `Polygon` / `MultiPolygon` geometry using `lon,lat` coordinates.

Polygon rings must contain at least four points and be explicitly closed. The injected point is tested against the latest revision geometry without exporting the geometry.

Warnings are grouped by `id`/`identifier`. Revision ordering uses `updated` or `sent`; the latest revision is authoritative for validation. Two different payloads with the same identifier and revision timestamp fail closed as a revision collision. Lifecycle is recomputed from `effective`/`onset` and `expires`; a supplied lifecycle label must match the recomputed state.

## Radar semantics

Radar frames are restricted to:

- `radar_observed` — timestamp at or before validation time;
- `radar_nowcast` — timestamp after validation time and no more than 120 minutes ahead.

The 120-minute ceiling follows the DWD RADVOR nowcasting product horizon (5-minute steps up to two hours). The validator treats the absence of a nowcast as `WARN`, not as a fabricated forecast.

For operational map freshness this project uses a **20-minute observed-radar tolerance**. This is a project policy, not a DWD product definition. Older observed radar produces `WARN: RADAR_OBSERVED_STALE` while retaining the timestamp/provenance outside this sanitized validator output.

## Source references

- DWD CAP warnings: <https://opendata.dwd.de/weather/alerts/cap/>
- DWD radar Open Data: <https://opendata.dwd.de/weather/radar/>
- DWD RADOLAN/RADVOR product documentation: <https://www.dwd.de/DE/leistungen/radolan/radolan.html>

These references describe upstream products only. The source validator does not contact them during CI or runtime validation.

## Explicit exclusions

This contract does **not** authorize or perform live map mutation, network access, Cloudflare changes, service restart/reload, runtime secret access, coordinate persistence, production database writes, or WeatherNext warning substitution. A later real home-centered validation still requires the appropriate private-runtime/LIVE authority.
