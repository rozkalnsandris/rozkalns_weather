# Optional WeatherNext 3 full-ensemble contract

Issue #51 adds the network-free `weathernext_ensemble` contract. It does not assert
that private WeatherNext access currently exposes members. All test values and
source identities are explicitly synthetic fixtures, never real WeatherNext data.

`MemberSourceEvidence` must come from separately reviewed upstream documentation
and schema evidence: exact model version, schema SHA-256, source surface,
resolution, full native member roster (including control when supplied), and a
SHA-256 reference to that evidence. `native_members_verified` must be true. This
is an admission precondition, not an access check or a cryptographic attestation.
A future adapter must preserve upstream identity; renaming quantiles to members
or setting this flag without defensible evidence is prohibited.

Each candidate `ForecastRun` must preserve provider/model/version, native init,
retrieval, raw payload SHA-256, surface/schema/resolution, station location and
member evidence reference. Metadata declares `member_origin=provider_native` and
an integer `ensemble_size` equal to the reviewed roster. Each value retains valid
time, exact lead hours, native member statistic, canonical variable/unit and
accumulation window. One admitted slice has one model/init/retrieval identity.
Different model versions or product surfaces must be evaluated separately.

`admit_members` requires every declared member exactly once at the selected
variable/valid time; missing, duplicated, inferred or summary values fail closed.
It never fills gaps or modifies the forecast corpus. Supported scalar quantities
follow the existing variable semantics; upstream probability variables and unknown
variables are not member-valued quantities. Member values and lead hours must be
finite. Event metrics are currently limited to the existing hourly precipitation
contract: fraction of members >= 0.1 mm over the same 60-minute window.

`verification_eligibility` reports metric eligibility with stable rejection reasons.
CRPS and empirical intervals require admitted members. Event probability, Brier
and reliability additionally require supported precipitation semantics.
`verify_member_slice` calls the existing probabilistic primitives only after
admission and finite, location/time/unit/window-matched station truth checks.
Its reliability bins contain one sample; they do not imply calibration sufficiency
or a model ranking. Callers must retain normal report sample-sufficiency gates.

When members are unavailable or inadmissible, route separately to the existing
`mean/p10/p25/p50/p75/p90` summary-quantile verification. The fallback label is not
an assertion that summary input is valid: existing summary admission still applies.
No CRPS, Brier, empirical member probabilities or synthetic members may be derived
from summary quantiles. Existing summary collection and reports remain unchanged.

This source contract performs no BigQuery query, credential access, production
write or runtime activation. Private-home forecasts remain forecast-only; this
measured contract admits only `station_10416`. DWD remains the official warning
authority. Future real source access and deployment require their existing gates.
