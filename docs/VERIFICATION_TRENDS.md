# Verification trends v1

`verification-trends-v1` is the source-side, read-only trend contract for public benchmark evidence. It composes the existing `verification-drilldown-v1` semantics rather than introducing a second metric implementation.

## Purpose

The report answers how verification evidence changes over time while keeping unlike samples separate. It emits three deterministic period families:

- `monthly`: calendar-month slices, clipped to the requested/common benchmark window;
- `seasonal`: meteorological `DJF`, `MAM`, `JJA`, `SON` slices, also clipped at window boundaries;
- `rolling`: 30-day windows every 7 days by default, with a final clipped window when necessary.

Every deterministic or ensemble trend point keeps the dimensions `provider`, `model_version`, exact comparison cohort, `init_cycle_utc`, `lead_bucket` and `variable`. The underlying drilldown still performs strict common-valid-time matching inside the relevant provider class before metrics are emitted.

## Samples and metrics

Deterministic trend points preserve:

- `n` and `sample_sufficiency_state`;
- exact missingness/attrition evidence;
- MAE, RMSE and bias;
- deterministic event summaries where already eligible.

Ensemble trend points are emitted only from the genuine `member_N` inputs accepted by `verification-drilldown-v1`. They may contain CRPS, interval coverage/width, WIS, Brier and reliability evidence only where the existing semantic rules permit those metrics. Deterministic precipitation amounts never become probabilities.

The existing sample thresholds are retained: fewer than 30 matched samples is `insufficient_sample`, 30-99 is `limited_sample`, and 100+ is `usable_sample`.

## Version boundaries and historical clipping

Exact model-version cohort identity is part of a trend series. A model-version change starts a different series and is not treated as a skill improvement/degradation across the boundary.

The common public comparison window starts on `2026-04-02`. Any earlier requested interval is represented separately as `historical_ifs_only` and is never mixed into common-model trend metrics. A wholly pre-common request returns `WARN/HISTORICAL_IFS_ONLY` with no common trend periods.

## Descriptive shift evidence

`material_shifts` is descriptive evidence, not model ranking or weighting. The frozen thresholds live in `contracts/verification-trends-v1.json` and are mirrored by `SHIFT_POLICY` in the implementation.

Current v1 rules include:

- deterministic/CRPS/WIS metric change: at least 25% relative and at least 0.10 absolute;
- missing-fraction change: at least 0.20;
- interval-coverage change: at least 0.15;
- Brier change: at least 0.05;
- provider-freshness age change: at least 25% relative and at least 2 hours absolute;
- freshness-state changes are reported directly using the frozen severity ordering.

Skill/calibration shift detection is suppressed when either adjacent trend point has `insufficient_sample`. Model-version boundaries are never compared. `direction` is descriptive (`improved`, `degraded`, or `changed`) and does not create an overall winner.

Provider freshness can be supplied as already-sanitized snapshots with `provider`, timestamp, `freshness_state` and optional `source_age_hours`. Only period-level state/count/age summaries are emitted; raw logs, transport payloads or provider details are not part of this contract.

## Safety and provenance

The builder is pure/read-only over supplied rows. It does not initialize or mutate SQLite, retry providers, backfill data, start a scheduler or change runtime state. WeatherNext remains explicitly pending until a defensible real corpus exists; no WeatherNext value is synthesized for trend output.

The report always declares:

- no overall winner;
- no Combined weighting;
- no automatic model weighting;
- no production-data authority;
- no LIVE/runtime authority.

A later report-lineage receipt may bind this trend artifact to exact source/corpus/config identities, but `verification-trends-v1` itself grants no publish, deploy or production-corpus mutation authority.

## Regression coverage

`tests/test_verification_trends.py` freezes the key semantics with deterministic fixtures for:

- a genuine MAE shift on matched monthly samples;
- missing provider cycles and visible attrition;
- sparse periods that suppress material skill claims;
- model-version boundaries;
- common-window and meteorological-season clipping;
- eligible calibration change from genuine-member trend points;
- provider freshness deterioration independent from skill;
- pre-common IFS-only history;
- source/contract threshold alignment.
