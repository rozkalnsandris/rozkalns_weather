# Runtime configuration validation v1

`runtime-config-v1` is the privacy-safe startup configuration contract for the public-only runtime and the later private-research runtime.

Canonical machine snapshot: `contracts/runtime-config-v1.json`.
Executable validator: `python -m rozkalns_weather.runtime_config`.

## States

The validator emits only `PASS`, `WARN`, or `BLOCKED` plus stable reason codes and boolean presence evidence. It never emits `HOME_LAT`, `HOME_LON`, Google project/dataset values, credential material, the database URL value, raw environment data, or private runtime paths.

`PASS` means the declared configuration is internally compatible with this source contract. It does **not** prove a deployed runtime, valid Google credentials, provider availability, production database readiness, or LIVE/data authority.

`WARN` is reserved for source/development configurations that are allowed but are not a reviewed deployment profile. `BLOCKED` is fail-closed and must prevent the reviewed application startup.

## Public-only deployment

The reviewed public package sets:

- `WEATHER_RUNTIME_MODE=public-only`
- `WEATHER_CONFIG_PROFILE=deployment`
- `WEATHER_CONFIG_SCHEMA_VERSION=1`
- `DATABASE_INIT_MODE=require-existing`
- `DATABASE_URL` present

Private-home coordinates and WeatherNext private-access inputs are unsupported in this mode. Deployment with `DATABASE_INIT_MODE=auto` is `BLOCKED` as `IMPLICIT_DATABASE_INITIALIZATION_UNSAFE`.

The Docker application command runs the validator before `uvicorn`, so a `BLOCKED` result exits before the application process starts. The validator itself performs no network request, database initialization, database write, credential read, Docker/systemd action, or host mutation.

## Private-research deployment

A later separately authorized private runtime must use `private-research` with the deployment profile and `require-existing`. It additionally requires:

- both `HOME_LAT` and `HOME_LON` present at runtime;
- both Google project and WeatherNext dataset configuration present at runtime;
- `GOOGLE_AUTH_PRESENT=true` as presence/readiness evidence only.

`GOOGLE_AUTH_PRESENT` is not a credential and must never contain credential material. Real values stay runtime-only. The validator does not test Google Cloud access; the existing WeatherNext first-access and private-runtime activation contracts remain authoritative for that later gate.

## Fail-closed examples

Stable blocking reasons include `CONFIG_SCHEMA_UNSUPPORTED`, `CONFIG_PROFILE_INVALID`, `RUNTIME_MODE_INVALID`, `DATABASE_INIT_MODE_INVALID`, `HOME_COORDINATE_PAIR_INCOMPLETE`, `HOME_COORDINATE_INVALID`, `IMPLICIT_DATABASE_INITIALIZATION_UNSAFE`, `PUBLIC_RUNTIME_PRIVATE_HOME_UNSUPPORTED`, `PUBLIC_RUNTIME_PRIVATE_ACCESS_UNSUPPORTED`, `PRIVATE_HOME_REQUIRED`, `PROJECT_DATASET_CONFIG_REQUIRED`, `GOOGLE_AUTH_PRESENCE_REQUIRED`, `GOOGLE_AUTH_PRESENCE_FLAG_INVALID`, `INGEST_TIMEOUT_INVALID`, `INGEST_RETRIES_INVALID`, and `PRECIP_THRESHOLD_INVALID`.

## Authority boundary

A validator `PASS` is configuration evidence only. It never grants RPi5 deploy/restart authority, Docker/systemd/timer authority, `.env`/secret/credential authority, Google Cloud/BigQuery read authority, Cloudflare/network authority, or production SQLite/corpus write/migration authority. Those remain separate exact owner gates under the weather and `RPi5_main` trust boundary.
