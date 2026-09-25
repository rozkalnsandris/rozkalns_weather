# Ensemble member completeness and identity

`ensemble-member-completeness-v1` is the source-side admission contract for member-derived probabilistic verification.

## Supported identities

The contract follows the identities already exposed by the project ensemble provider definitions:

- `icon_d2_eps` / `ICON-D2-EPS`: 20 total identities.
- `ecmwf_ifs_ens` / `IFS ENS 0.25°`: 51 total identities.
- `ecmwf_aifs_ens` / `AIFS ENS 0.25°`: 51 total identities.

The canonical control identity is `control`. Transport/database spellings `member_00` and `member00` are aliases for that control identity. Numbered perturbations normalize from `member_NN` or `memberNN` to canonical `memberNN`. The raw identity is retained in evidence; normalization does not replace source provenance.

## States and metric admission

A `complete` set contains exactly the expected canonical member identities with no duplicates, unexpected members, model-version mixing, or expected-size drift. Only a complete set is eligible for CRPS, empirical member intervals, member-fraction probabilities, Brier score, and reliability.

A `partial` set is missing one or more expected identities or is explicitly marked as retention-truncated. It remains visible as evidence but is not admitted to those metrics. Missing members are never synthesized.

A `blocked` set contains structurally conflicting evidence such as duplicate IDs, a control/member collision, unexpected IDs, mixed model versions, or a changed declared ensemble size. A run whose discovered member set changes between slices is also blocked with `MEMBER_SET_CHANGED`.

An `unsupported` set has no registered ensemble identity contract and is not admitted to member-derived probabilistic metrics.

## Provenance and reporting

Completeness evidence carries provider/model identity plus the supplied model version, init time, valid time, lead, variable and source-surface provenance. Reporting must count total member groups separately from metric-eligible groups and expose stable reason codes for excluded groups. A completeness PASS proves member-set eligibility only; it does not grant production corpus-write, provider mutation, WeatherNext private-query, or LIVE authority.
