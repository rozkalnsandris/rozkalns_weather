# Source-to-runtime descriptor parity

`source-runtime-descriptor-parity-v1` is a **source-only** consistency gate. It compares the reviewed Weather deployment contracts with each other before any later LIVE rollout decision.

It does **not** inspect the Raspberry Pi, Docker, systemd, a running container, the production database, private host paths or credentials. A PASS therefore means only that the reviewed repository contracts agree with each other.

## Compared source identities

The validator binds these source surfaces:

- `deploy/runtime-descriptor.json`
- `deploy/docker-compose.public.yml`
- `deploy/public-ingest-schedule.json`
- `.simple-deploy.json`
- `deploy/production-public-corpus-bootstrap.json`
- `deploy/release-artifact-identity.json`
- `deploy/rpi5-source-binding.json`
- `deploy/rozkalns-weather-public-ingest.service.example`
- `deploy/rozkalns-weather-public-ingest.timer.example`

It checks service names, Compose file/project/application identity, public-ingest job and systemd timer identity, `/health` and `/ready`, `public-only` runtime mode, explicit `require-existing` database initialization, target alias, runtime class, image repository and pinned shared SIMPLE-DEPLOY workflow identity.

## Stale source binding semantics

`deploy/rpi5-source-binding.json` intentionally retains historical recovery/control-plane evidence. Its current `LEGACY_SUPERSEDED` / `pre_issue_140_main_anchor_only` source SHA is not a current release candidate and is not runtime proof.

The parity validator therefore does not treat that historical SHA as a mismatch against current `main`. A source binding that declares itself current/active while naming a different Weather source SHA is blocked with `STALE_SOURCE_BINDING`.

This distinction prevents two unsafe conclusions:

1. old GitHub continuity evidence must not be mistaken for the currently deployed runtime;
2. a stale historical SHA must not by itself be interpreted as proof that the live host is wrong or unhealthy.

## Stable fail-closed reasons

Machine-readable evidence uses stable reason codes including:

- `MISSING_COMPOSE_SERVICE`
- `COMPOSE_SERVICE_IDENTITY_MISMATCH`
- `COMPOSE_FILE_IDENTITY_MISMATCH`
- `COMPOSE_PROJECT_MISMATCH`
- `INGEST_SERVICE_MISMATCH`
- `TIMER_JOB_IDENTITY_MISMATCH`
- `LIVENESS_ENDPOINT_MISMATCH`
- `READINESS_ENDPOINT_MISMATCH`
- `RUNTIME_MODE_MISMATCH`
- `DATABASE_INIT_MODE_MISMATCH`
- `IMPLICIT_SCHEMA_INIT_UNSUPPORTED`
- `TARGET_ALIAS_MISMATCH`
- `RELEASE_RUNTIME_IDENTITY_MISMATCH`
- `RELEASE_IMAGE_IDENTITY_MISMATCH`
- `SHARED_WORKFLOW_IDENTITY_MISMATCH`
- `STALE_SOURCE_BINDING`

Any detected mismatch produces `BLOCKED`. Exact internal source parity produces `PASS`.

## Privacy-safe evidence

The output intentionally carries logical identities only. It does not expose:

- private host paths or broad host inventory;
- credentials, secrets or `.env` values;
- `HOME_LAT` / `HOME_LON` or a private home point;
- production SQLite contents.

The evidence also always states:

- `runtime_deployed_proven: false`
- `runtime_healthy_proven: false`
- `host_state_observed: false`
- `live_authority_granted: false`

## Future LIVE boundary

A source-parity PASS is a prerequisite, not deployment acceptance. When a future work item actually requires LIVE proof, the trusted `rozkalnsandris/RPi5_main` boundary must freshly and read-only bind, at minimum:

1. the reviewed exact Weather release/source identity;
2. the exact deployed immutable image digest;
3. the deployed Compose/service identity;
4. the installed public-ingest timer/service identity and schedule;
5. the live `/health` and `/ready` results;
6. the production database/schema mode without exposing private paths or data.

Any subsequent Docker/systemd/restart/deploy, configuration, filesystem, database/corpus or other runtime mutation remains a separate explicit owner gate. Repository source parity never grants that authority.
