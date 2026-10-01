# WeatherNext clustered BigQuery cost characterization

This document is a source-only diagnostic amendment for issue #122. It does not authorize private Google access, a real WeatherNext data query, a higher `maximum_bytes_billed`, or any production write.

## Why the current 1 GiB dry-run gate stopped

The WeatherNext 3 BigQuery guide recommends the same core query shape already used by this repository:

- exact `init_time` filter for partition pruning;
- selected columns rather than `SELECT *`;
- a spatial predicate against `geography_polygon`;
- bounded forecast hours.

WeatherNext documents the tables as partitioned by `init_time` and spatially clustered. BigQuery separately documents an important cost-control limitation: for clustered tables, the pre-execution bytes estimate is an upper bound because the storage blocks that can be pruned are not known until execution. As a result, `maximum_bytes_billed` can reject a clustered query even when its eventual billed bytes would be lower.

References:

- https://developers.google.com/weathernext/guides/bigquery
- https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables
- https://docs.cloud.google.com/bigquery/docs/clustered-tables
- https://docs.cloud.google.com/bigquery/docs/best-practices-costs
- https://docs.cloud.google.com/bigquery/docs/running-queries

Therefore the #122 failure is not evidence that the point SQL lost its partition filter or spatial predicate. The failure proves that the existing source contract incorrectly treated a clustered-table pre-execution upper bound as a precise per-query cost measurement.

## Safe correction

Do not raise the 1 GiB real-query ceiling by guesswork.

First run a separately owner-authorized **dry-run-only characterization** using the exact two #122 queries with no per-job `maximum_bytes_billed` value. BigQuery documents dry runs as uncharged. A project-level default, if configured, remains an independent provider-side control and is not bypassed by this helper. The helper added for this purpose is:

```bash
python -m rozkalns_weather.weathernext_cost_characterization \
  --init <EXACT_UTC_INIT> \
  --hours-limit 6
```

The helper:

- fixes `station_05480` through `BENCHMARK_LOCATION`;
- keeps the exact `init_time` partition predicate;
- keeps the spatial predicate and selected-column query contract;
- executes only `dry_run=True` BigQuery jobs;
- disables client/job retries;
- never sets a per-job `maximum_bytes_billed` on the characterization jobs;
- emits only sanitized byte estimates plus an explicit `pre_execution_upper_bound_for_clustered_table` interpretation;
- does not emit project ID, dataset ID, coordinates, SQL, credentials, or WeatherNext values;
- never executes a real query and never touches SQLite.

## What the characterization can and cannot prove

The resulting `total_bytes_processed` value is the BigQuery pre-execution estimate. For a clustered table it is a conservative upper bound and can exceed the actual billed bytes after spatial block pruning.

The result is sufficient to answer the next policy question: what explicit pre-execution cap would BigQuery require for the exact query shape? It is **not** sufficient to claim that the same number would actually be billed.

The current 1 GiB real-query ceiling remains unchanged until an explicit owner decision. `bounded_canary_query` stays blocked.

## Next owner decision after characterization

After fresh sanitized estimates exist, choose one of these reviewed paths instead of silently widening the gate:

1. Keep the BigQuery canary and set a new explicit real-query `maximum_bytes_billed` at or above the required clustered-table pre-execution upper bound, with the worst-case cost stated before authorization.
2. Add a separate Google Cloud custom query quota as a second cost-control layer. This is a Google Cloud quota/IAM mutation and therefore needs its own owner gate. Google documents custom query quotas as an additional safeguard, not an exact byte guarantee.
3. If the required upper bound is operationally unacceptable, stop BigQuery first-access and evaluate a different WeatherNext access surface in a separate scoped issue. Do not substitute another source inside #122 without an explicit scope decision.

BigQuery on-demand pricing currently documents the first 1 TiB per month per billing account as free and subsequent query processing at USD 6.25/TiB, but pricing must be refreshed before any monetary authorization.

## Fail-closed boundary

A characterization failure, source/runtime drift, private-binding ambiguity, or unexpected BigQuery state is STOP. No retry, alternate dataset, real query, cap increase, quota mutation, credential change, or production write is implied by this helper.
