# Release artifact identity

Contract: `release-artifact-identity-v1`.

This contract binds a reviewed public-only build to an immutable container image identity before a later rollout. It is **build/release evidence only**: a PASS result does not prove that any image is deployed and does not grant registry, Docker, systemd, restart, RPi5, or other LIVE authority.

## Evidence chain

The validator consumes the deterministic `container-build-reproducibility-v1` output from Issue #60 and binds these identities together:

1. exact 40-character source commit SHA;
2. deterministic `build_identity_sha256`;
3. dependency-lock SHA-256;
4. deterministic runtime SBOM SHA-256, recomputed from the supplied SBOM payload;
5. the reviewed `deploy/runtime-descriptor.json` SHA-256 plus its `runtime_class` and `target_alias`;
6. an immutable OCI-style image digest `sha256:<64 hex>` and digest-qualified image reference.

The resulting `release_manifest` contains only immutable, privacy-safe release identity fields. `release_identity` is `sha256:` plus the SHA-256 of canonical JSON for that manifest.

A mutable image tag may be included only as auxiliary resolution evidence. The tag is never the release identity. If a supplied tag resolves to a digest different from the immutable image digest, validation is BLOCKED.

## Input

`python -m rozkalns_weather.release_artifact_identity` reads one JSON object from stdin:

```json
{
  "schema_version": 1,
  "source_sha": "<exact-reviewed-source-sha>",
  "runtime_descriptor_sha256": "<sha256-of-reviewed-runtime-descriptor>",
  "build_evidence": {
    "...": "container-build-reproducibility-v1 PASS payload"
  },
  "image": {
    "repository": "ghcr.io/example/weather",
    "reference": "ghcr.io/example/weather@sha256:<digest>",
    "digest": "sha256:<digest>",
    "built_source_sha": "<exact-reviewed-source-sha>",
    "build_identity_sha256": "<build-identity>",
    "sbom_sha256": "<sbom-identity>",
    "tag_reference": null,
    "tag_resolved_digest": null
  }
}
```

`--output <path>` may write the sanitized report. `--require-pass` returns a non-zero exit code unless the result is PASS.

## Stable blocking reasons

Important deterministic reasons include:

- `BUILD_CONTRACT_MISMATCH` or `BUILD_EVIDENCE_NOT_PASS`;
- `SOURCE_BUILD_IDENTITY_MISMATCH`;
- `BUILD_IDENTITY_INVALID`, `SBOM_IDENTITY_INVALID`, or `DEPENDENCY_LOCK_IDENTITY_INVALID`;
- `STALE_SBOM_IDENTITY`;
- `RUNTIME_DESCRIPTOR_MISMATCH`, `RUNTIME_DESCRIPTOR_IDENTITY_MISMATCH`, or `BUILD_RUNTIME_DESCRIPTOR_MISMATCH`;
- `IMAGE_DIGEST_MISSING` or `IMAGE_DIGEST_INVALID`;
- `MUTABLE_TAG_ONLY_REFERENCE` or `IMAGE_REFERENCE_DIGEST_MISMATCH`;
- `IMAGE_SOURCE_SHA_MISMATCH`, `IMAGE_BUILD_IDENTITY_MISMATCH`, or `IMAGE_SBOM_IDENTITY_MISMATCH`;
- `TAG_RESOLUTION_EVIDENCE_MISSING` or `MUTABLE_TAG_REUSED_DIFFERENT_DIGEST`.

The validator fails closed instead of treating a mutable tag as immutable evidence or inferring a missing digest.

## Post-rollout acceptance integration

`post-rollout-acceptance-v1` already requires an expected release identity. A later, separately authorized rollout can carry the PASS `release_identity` into runtime evidence, and post-rollout acceptance can require the runtime-reported release identity to match it together with the exact source SHA.

That later comparison is what links reviewed release evidence to observed deployed state. This source validator deliberately reports:

- `build_release_evidence_only: true`;
- `deployed_runtime_state_proven: false`;
- all registry/deploy/restart/LIVE authority flags as `false`.

Therefore a PASS result is not evidence that a registry push happened, that an image exists on the RPi5, that Docker or systemd changed, or that the Web UI is live.

## Privacy and authority boundary

Evidence must not contain exact home coordinates, credentials/tokens/secrets, private host paths, raw runtime logs, or runtime `.env` content. The validator performs no network calls and no runtime mutation.

Registry push, image build/push, RPi5 deploy/redeploy/restart, Docker/systemd mutation, credentials, Cloudflare/network changes, and production SQLite/corpus mutation remain separately authorized operations outside this contract.
