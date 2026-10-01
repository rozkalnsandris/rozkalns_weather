# Reproducible public-default container build and SBOM

Issue #60 defines a source-only reproducibility gate for the RPi5 application image. It does not build, push, deploy or activate a production image.

## Frozen build inputs

The runtime image uses:

- CPython `3.12.14-slim-bookworm` pinned by Docker Official Image multi-platform index digest;
- `deploy/public-runtime.lock` with exact Python package versions;
- `pip install -r` followed by project install with `--no-deps --no-build-isolation`;
- only `deploy/public-runtime.lock`, `pyproject.toml`, `README.md` and `src/` copied into the runtime build context.

The standard `google-cloud-bigquery` client is packaged in the same reproducible image so the SIMPLE WeatherNext path does not need a second host runtime. It remains dormant while `WEATHER_RUNTIME_MODE=public-only` / `weathernext_required=false`; no Google credential, project ID, dataset ID or private configuration is baked into the image. Private WeatherNext authentication and activation remain separate owner-gated runtime configuration.

Machine contract: `deploy/container-build-reproducibility.json`.

## Evidence and SBOM

Run from an exact source checkout:

```bash
python -m rozkalns_weather.build_evidence \
  --source-sha <40-char-reviewed-sha> \
  --observed-source-sha <40-char-checkout-sha> \
  --require-pass \
  --output /tmp/container-build-evidence.json \
  --sbom-output /tmp/container-runtime-sbom.json
```

The validator is network-free and reads only repository files. It produces `PASS`, `WARN` or `BLOCKED` with stable reason codes.

The evidence binds:

- exact expected and observed source SHA;
- base-image digest;
- SHA-256 of Dockerfile, dependency lock, runtime descriptor, Compose file and other reviewed build inputs;
- dependency-lock checksum;
- deterministic runtime SBOM checksum;
- runtime class and target alias;
- one `build_identity_sha256` suitable for later release acceptance.

The SBOM is `rozkalns.python-runtime-sbom.v1`. Every locked package has exact version, PyPI purl and scope (`runtime-direct`, `runtime-transitive` or `build-tool`). It also records expected console scripts and Docker `COPY` source roots.

## Fail-closed checks

`BLOCKED` includes, among others:

- invalid or mismatched source SHA;
- base image not matching the reviewed digest;
- missing/unreadable required build inputs;
- unpinned/ambiguous/duplicate dependency lock entries;
- dependency lock checksum drift;
- direct/build dependency not present in the lock or outside declared range;
- `.[weathernext]` installed by the public-default Dockerfile instead of the reviewed lock;
- unexpected Docker `COPY` sources;
- project install without `--no-deps --no-build-isolation`;
- runtime class/target/mode/WeatherNext-requirement mismatch.

If the checkout SHA is unavailable the result is `WARN`; CI uses `--require-pass` with `GITHUB_SHA` bound as both expected and observed identity.

## CI package validation

Backend CI keeps ordinary fixture tests and adds a build-evidence job on exact CPython `3.12.14`:

1. install `deploy/public-runtime.lock`;
2. install the project with `--no-deps --no-build-isolation`;
3. run `pip check`;
4. generate build evidence and SBOM with exact `GITHUB_SHA`;
5. import the application module and the packaged BigQuery client without constructing a client or reading credentials.

This validates that the committed lock is actually installable and internally consistent without invoking Google APIs, a Docker daemon or registry.

## LIVE boundary

A source `PASS` is not credential or private-provider activation authority. Ordinary SIMPLE-DEPLOY may publish/deploy the reviewed application image under its standing application-release contract, while a later separately authorized WeatherNext runtime activation must freshly bind the approved runtime identity/configuration.

Credentials/secrets, private home coordinates, Google IAM changes, BigQuery queries, private-provider activation and production SQLite/corpus writes remain outside this source gate.
