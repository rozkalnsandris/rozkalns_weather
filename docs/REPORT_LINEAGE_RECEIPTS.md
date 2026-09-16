# Verification report lineage receipts

Issue #64 adds a deterministic, source-only lineage contract for benchmark/report artifacts.

The canonical implementation is `src/rozkalns_weather/report_lineage.py` with contract id `verification-report-lineage-v1`.

## Purpose

A machine-readable report artifact is not considered reproducibly identified by its visible values alone. Its receipt binds all of the following in one deterministic identity:

- exact reviewed 40-character Weather source SHA;
- report schema name/version;
- exact corpus provenance-manifest contract, aggregate checksum, schema identity and canonical manifest checksum;
- exact report date window, which must match the corpus manifest window;
- provider/model/version identities, including explicit unknown/`null` model version where that is the defensible source state;
- lead filters, sample filters and metric configuration;
- common-sample identity and per-slice sample counts;
- separate metric eligibility for deterministic forecasts, genuine ensemble members and WeatherNext summary quantiles;
- SHA-256 of the complete machine-readable report artifact;
- one repository-relative logical reference to the corresponding human-readable output.

The receipt itself receives a deterministic `lineage_identity_sha256`. Identical frozen inputs reproduce the same receipt. Any material artifact/configuration/corpus change produces a different identity.

## Fail-closed rules

Receipt construction rejects:

- non-exact or malformed source SHAs;
- unsupported or `BLOCKED` corpus manifests;
- manifests that are not explicitly read-only evidence;
- missing corpus aggregate/schema provenance;
- report windows that do not exactly match the frozen corpus-manifest window;
- missing provider/model/version provenance;
- mixed source identities;
- mixed configuration identities;
- missing common-sample identity or invalid sample counts;
- missing distinction between deterministic, genuine ensemble-member and WeatherNext-summary metric eligibility;
- unknown metric-eligibility classes, including synthetic probability/member semantics;
- absolute/private filesystem references, external URLs or parent traversal in the human-readable artifact reference;
- non-finite or otherwise non-canonical JSON values.

`validate_report_lineage_receipt(...)` rechecks the machine-readable artifact checksum, corpus-manifest identity and receipt lineage identity before a receipt is trusted later.

## Metric semantics

The receipt records eligibility; it does not change verification formulas or create new metric authority.

- `deterministic`: MAE/RMSE/bias and other deterministic metrics only when the report configuration explicitly selects them.
- `ensemble_members`: CRPS, empirical intervals/WIS and member-fraction probability/Brier/reliability only for genuine stored ensemble members.
- `weathernext_summary_quantiles`: summary-quantile interval/coverage-style evidence only. WeatherNext summary quantiles are never converted into synthetic ensemble members or event probabilities.

Sample counts and the common-sample identity are first-class lineage inputs. A report receipt therefore cannot silently retain the same identity when the matched sample set changes.

## Privacy and authority

Receipts are public-safe metadata only. They intentionally contain no exact home coordinates, credentials, database paths, raw logs or provider payloads. A human-readable output is referenced only by a repository-relative logical identifier.

A `PASS` lineage validation proves reproducibility of the frozen report identity only. It does **not** authorize:

- production corpus writes, migrations, repair or rehash;
- artifact publication;
- RPi5 deploy/runtime mutation;
- WeatherNext private BigQuery access;
- credential, secret, Cloudflare, permission or network changes.

Those remain separate exact owner gates under `AGENTS.md` and the trusted `RPi5_main` boundary.
