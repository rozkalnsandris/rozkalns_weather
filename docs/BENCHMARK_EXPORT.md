# Reproducible public benchmark export

Issue #44 defines a deterministic, privacy-safe export surface for the public `station_10416` benchmark corpus. The export is read-only with respect to SQLite and never initializes, migrates, repairs, backfills, or deletes corpus data.

## Command

```bash
python -m rozkalns_weather.benchmark_export \
  --source-sha <EXACT_40_CHAR_MERGED_SHA> \
  --start 2026-04-02 \
  --end 2026-04-30 \
  --output ./benchmark-export-2026-04
```

The database is taken from the normal `DATABASE_URL` environment setting. `--output` must name a new directory. The command prints only a sanitized PASS/BLOCKED summary; the database path is never written into the bundle.

## Bundle contract

`public-benchmark-export-v1` writes five deterministically ordered files:

- `manifest.json` — source SHA, export/corpus schema identity, common-window bounds, deterministic/ensemble provider roles, exact model-version identities and verification configuration.
- `forecasts.ndjson` — public station forecast rows with provider/model/init/retrieval/valid/lead/statistic/revision/unit provenance. Raw provider metadata and private runtime fields are deliberately excluded.
- `observations.ndjson` — DWD WMO `10416` truth rows only.
- `metrics.json` — deterministic common-sample MAE/RMSE/bias plus genuine-ensemble CRPS, interval coverage/width/WIS and precipitation Brier summaries where eligible members exist.
- `checksums.json` — SHA-256 for every other file. SHA-256 of this canonical checksum file is the bundle fingerprint.

There is no generation timestamp or output path inside the bundle, so the same source SHA + corpus/config produces byte-stable files where Python/SQLite numeric serialization is identical.

## Fail-closed rules

The export is BLOCKED when any forecast row lacks required provenance, contains a non-public location/private field, has a malformed content hash or inconsistent lead time, or mixes model versions for the same provider. Model-version boundaries must therefore be exported separately rather than silently combined. All three deterministic comparison providers (`icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`) must be present. Ensemble providers are optional, but if present they must contain genuine `member_N` statistics; summary quantiles or synthetic members are rejected.

Truth rows must be `DWD` / WMO `10416` / `station_10416`. `HOME_LAT`, `HOME_LON`, credentials/tokens, database/runtime paths, raw logs and `source_metadata_json` are never part of the export contract.

## Independent reproduction

Use only the files in one verified bundle:

1. Verify every entry in `checksums.json`, then verify the bundle fingerprint supplied by the command/transport layer.
2. Read `manifest.json` and enforce its source SHA, common window, model-version identities, lead buckets and statistic roles before calculating any metric.
3. For deterministic comparison, retain the latest immutable revision for each provider/model/init, then within each provider + variable + lead bucket + valid time select the smallest lead (latest forecast opportunity). Intersect valid times across the deterministic providers and require a matching DWD truth row. On exactly that common sample calculate:
   - `MAE = mean(abs(forecast - observed))`
   - `RMSE = sqrt(mean((forecast - observed)^2))`
   - `bias = mean(forecast - observed)`
4. For genuine ensemble groups, calculate CRPS from the exported members. For temperature, the contract uses an empirical 80% interval (`alpha=0.2`) plus width/coverage and the existing WIS-style primitive. For `precipitation_1h`, event probability is the member fraction at or above `0.1 mm`, then Brier Score is calculated against the observed binary event.
5. Sample-size/sufficiency state follows `common-sample-sufficiency-v1`. Deterministic and ensemble metrics remain separate; unsupported probability, CRPS or Brier values must not be inferred from deterministic precipitation or summary quantiles.

The exported derived metrics are a reproducibility cross-check, not a substitute for recomputation from the exported station rows.
