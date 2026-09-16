from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence

CONTRACT = "release-artifact-identity-v1"
SCHEMA_VERSION = 1
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMAGE_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]{0,199}$")
_PRIVATE_KEYS = frozenset(
    {
        "home_lat",
        "home_lon",
        "credentials",
        "credential",
        "token",
        "secret",
        "raw_logs",
        "raw_log",
        "database_path",
        "host_path",
        "env",
        "environment",
    }
)
_PRIVATE_PATH_PREFIXES = ("/home/", "/opt/", "/root/", "/etc/")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} evidence missing or malformed")
    return value


def _exact_keys(value: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    observed = frozenset(str(key) for key in value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(f"{label} schema mismatch: missing={missing} extra={extra}")


def _scan_privacy(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _PRIVATE_KEYS or normalized.endswith("_path"):
                raise ValueError(f"release evidence contains forbidden private field: {key}")
            _scan_privacy(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _scan_privacy(child)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PATH_PREFIXES):
            raise ValueError("release evidence contains a private host path")


def _load_contract(repo_root: Path) -> dict[str, object]:
    path = repo_root / "deploy" / "release-artifact-identity.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("release artifact identity contract must be an object")
    return payload


def _blocked_payload(reason: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "state": "BLOCKED",
        "block_reasons": [reason],
        "warn_reasons": [],
        "release_identity": None,
        "release_manifest": None,
        "build_release_evidence_only": True,
        "deployed_runtime_state_proven": False,
        "authority": {
            "registry_push": False,
            "runtime_live": False,
            "production_image_deploy": False,
            "restart": False,
            "credentials_or_secrets": False,
        },
        "production_mutation_performed": False,
    }


def evaluate_release_artifact_identity(
    repo_root: Path,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    """Bind reviewed build evidence to an immutable image identity.

    The result is build/release evidence only. It never proves that the image is
    deployed and never grants registry, runtime, restart, or LIVE authority.
    """

    repo_root = repo_root.resolve()
    _scan_privacy(evidence)
    _exact_keys(
        evidence,
        frozenset(
            {
                "schema_version",
                "source_sha",
                "build_evidence",
                "image",
                "runtime_descriptor_sha256",
            }
        ),
        "release evidence",
    )
    if evidence.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must equal {SCHEMA_VERSION}")

    try:
        contract = _load_contract(repo_root)
    except (OSError, json.JSONDecodeError, ValueError):
        return _blocked_payload("RELEASE_CONTRACT_UNREADABLE")

    blockers: list[str] = []
    warnings: list[str] = []
    if contract.get("contract") != CONTRACT or contract.get("schema_version") != SCHEMA_VERSION:
        blockers.append("RELEASE_CONTRACT_SCHEMA_MISMATCH")

    source_sha = evidence.get("source_sha")
    if not isinstance(source_sha, str) or not _SHA40_RE.fullmatch(source_sha):
        blockers.append("INVALID_SOURCE_SHA")
        source_sha = str(source_sha or "")

    build_evidence = _mapping(evidence.get("build_evidence"), "build")
    if build_evidence.get("contract") != contract.get("build_contract"):
        blockers.append("BUILD_CONTRACT_MISMATCH")
    if build_evidence.get("state") != "PASS":
        blockers.append("BUILD_EVIDENCE_NOT_PASS")

    source_identity = _mapping(build_evidence.get("source_identity"), "build source identity")
    if (
        source_identity.get("expected_source_sha") != source_sha
        or source_identity.get("observed_source_sha") != source_sha
        or source_identity.get("match") is not True
    ):
        blockers.append("SOURCE_BUILD_IDENTITY_MISMATCH")

    build = _mapping(build_evidence.get("build"), "build identity")
    build_identity = build.get("build_identity_sha256")
    sbom_identity = build.get("sbom_sha256")
    dependency_lock_identity = build.get("dependency_lock_sha256")
    if not isinstance(build_identity, str) or not _SHA256_RE.fullmatch(build_identity):
        blockers.append("BUILD_IDENTITY_INVALID")
        build_identity = str(build_identity or "")
    if not isinstance(sbom_identity, str) or not _SHA256_RE.fullmatch(sbom_identity):
        blockers.append("SBOM_IDENTITY_INVALID")
        sbom_identity = str(sbom_identity or "")
    if not isinstance(dependency_lock_identity, str) or not _SHA256_RE.fullmatch(
        dependency_lock_identity
    ):
        blockers.append("DEPENDENCY_LOCK_IDENTITY_INVALID")
        dependency_lock_identity = str(dependency_lock_identity or "")

    sbom = _mapping(build_evidence.get("sbom"), "SBOM")
    actual_sbom_identity = _sha256_bytes(_canonical_json(sbom).encode("utf-8"))
    if actual_sbom_identity != sbom_identity:
        blockers.append("STALE_SBOM_IDENTITY")
    if sbom.get("source_sha") != source_sha:
        blockers.append("SOURCE_BUILD_IDENTITY_MISMATCH")

    descriptor_relative = str(contract.get("runtime_descriptor", "deploy/runtime-descriptor.json"))
    descriptor_path = repo_root / descriptor_relative
    try:
        descriptor_sha256 = _sha256_file(descriptor_path)
        runtime_descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        descriptor_sha256 = ""
        runtime_descriptor = {}
        blockers.append("RUNTIME_DESCRIPTOR_UNREADABLE")

    supplied_descriptor_identity = evidence.get("runtime_descriptor_sha256")
    if not isinstance(supplied_descriptor_identity, str) or not _SHA256_RE.fullmatch(
        supplied_descriptor_identity
    ):
        blockers.append("RUNTIME_DESCRIPTOR_IDENTITY_INVALID")
    elif supplied_descriptor_identity != descriptor_sha256:
        blockers.append("RUNTIME_DESCRIPTOR_MISMATCH")

    expected_runtime = contract.get("expected_runtime")
    if not isinstance(expected_runtime, Mapping):
        blockers.append("RELEASE_CONTRACT_SCHEMA_MISMATCH")
        expected_runtime = {}
    runtime_class = runtime_descriptor.get("runtime_class") if isinstance(runtime_descriptor, dict) else None
    target_alias = runtime_descriptor.get("target_alias") if isinstance(runtime_descriptor, dict) else None
    if (
        runtime_class != expected_runtime.get("runtime_class")
        or target_alias != expected_runtime.get("target_alias")
    ):
        blockers.append("RUNTIME_DESCRIPTOR_IDENTITY_MISMATCH")
    if build.get("runtime_class") != runtime_class or build.get("target_alias") != target_alias:
        blockers.append("BUILD_RUNTIME_DESCRIPTOR_MISMATCH")

    image = _mapping(evidence.get("image"), "image")
    _exact_keys(
        image,
        frozenset(
            {
                "repository",
                "reference",
                "digest",
                "built_source_sha",
                "build_identity_sha256",
                "sbom_sha256",
                "tag_reference",
                "tag_resolved_digest",
            }
        ),
        "image",
    )
    repository = image.get("repository")
    if not isinstance(repository, str) or not _IMAGE_REPOSITORY_RE.fullmatch(repository):
        blockers.append("IMAGE_REPOSITORY_INVALID")
        repository = str(repository or "")

    digest = image.get("digest")
    digest_valid = isinstance(digest, str) and bool(_DIGEST_RE.fullmatch(digest))
    if digest in (None, ""):
        blockers.append("IMAGE_DIGEST_MISSING")
    elif not digest_valid:
        blockers.append("IMAGE_DIGEST_INVALID")
    digest = str(digest or "")

    reference = image.get("reference")
    if not isinstance(reference, str) or "@" not in reference:
        blockers.append("MUTABLE_TAG_ONLY_REFERENCE")
    elif digest_valid and reference != f"{repository}@{digest}":
        blockers.append("IMAGE_REFERENCE_DIGEST_MISMATCH")

    if image.get("built_source_sha") != source_sha:
        blockers.append("IMAGE_SOURCE_SHA_MISMATCH")
    if image.get("build_identity_sha256") != build_identity:
        blockers.append("IMAGE_BUILD_IDENTITY_MISMATCH")
    if image.get("sbom_sha256") != sbom_identity:
        blockers.append("IMAGE_SBOM_IDENTITY_MISMATCH")

    tag_reference = image.get("tag_reference")
    tag_resolved_digest = image.get("tag_resolved_digest")
    if tag_reference is not None:
        if not isinstance(tag_reference, str) or not tag_reference or "@" in tag_reference:
            blockers.append("TAG_REFERENCE_INVALID")
        if not isinstance(tag_resolved_digest, str) or not _DIGEST_RE.fullmatch(
            tag_resolved_digest
        ):
            blockers.append("TAG_RESOLUTION_EVIDENCE_MISSING")
        elif digest_valid and tag_resolved_digest != digest:
            blockers.append("MUTABLE_TAG_REUSED_DIFFERENT_DIGEST")
    elif tag_resolved_digest is not None:
        blockers.append("TAG_RESOLUTION_WITHOUT_TAG_REFERENCE")

    blockers = list(dict.fromkeys(blockers))
    warnings = list(dict.fromkeys(warnings))
    state = "BLOCKED" if blockers else "WARN" if warnings else "PASS"

    release_manifest = {
        "contract": CONTRACT,
        "source_sha": source_sha,
        "build_identity_sha256": build_identity,
        "dependency_lock_sha256": dependency_lock_identity,
        "sbom_sha256": sbom_identity,
        "runtime_descriptor": {
            "path": descriptor_relative,
            "sha256": descriptor_sha256,
            "runtime_class": runtime_class,
            "target_alias": target_alias,
        },
        "image": {
            "repository": repository,
            "digest": digest,
            "reference": reference,
        },
    }
    release_identity = (
        f"sha256:{_sha256_bytes(_canonical_json(release_manifest).encode('utf-8'))}"
        if state == "PASS"
        else None
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "state": state,
        "block_reasons": blockers,
        "warn_reasons": warnings,
        "release_identity": release_identity,
        "release_manifest": release_manifest,
        "tag_evidence": {
            "tag_reference": tag_reference,
            "tag_resolved_digest": tag_resolved_digest,
            "tag_is_release_identity": False,
        },
        "build_release_evidence_only": True,
        "deployed_runtime_state_proven": False,
        "privacy": {
            "private_coordinates_included": False,
            "credentials_or_tokens_included": False,
            "private_runtime_paths_included": False,
            "raw_runtime_logs_included": False,
        },
        "authority": {
            "registry_push": False,
            "runtime_live": False,
            "production_image_deploy": False,
            "restart": False,
            "credentials_or_secrets": False,
        },
        "production_mutation_performed": False,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate immutable public-only release artifact identity"
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args(argv)

    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("release evidence must be a JSON object")
        payload = evaluate_release_artifact_identity(Path(args.repo_root), raw)
    except (ValueError, json.JSONDecodeError) as exc:
        payload = _blocked_payload("MALFORMED_RELEASE_EVIDENCE")
        payload["error"] = str(exc)

    if args.output:
        _write_json(Path(args.output), payload)
    print(json.dumps(payload, sort_keys=True))
    if payload["state"] == "BLOCKED":
        return 3
    if args.require_pass and payload["state"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
