from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

from rozkalns_weather.build_evidence import build_evidence
from rozkalns_weather.release_artifact_identity import (
    CONTRACT,
    evaluate_release_artifact_identity,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
IMAGE_REPOSITORY = "ghcr.io/rozkalnsandris/rozkalns_weather"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence() -> dict[str, object]:
    build = build_evidence(
        ROOT,
        source_sha=SOURCE_SHA,
        observed_source_sha=SOURCE_SHA,
    )
    assert build["state"] == "PASS"
    build_identity = build["build"]["build_identity_sha256"]
    sbom_identity = build["build"]["sbom_sha256"]
    return {
        "schema_version": 1,
        "source_sha": SOURCE_SHA,
        "build_evidence": build,
        "runtime_descriptor_sha256": _sha256_file(
            ROOT / "deploy" / "runtime-descriptor.json"
        ),
        "image": {
            "repository": IMAGE_REPOSITORY,
            "reference": f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}",
            "digest": IMAGE_DIGEST,
            "built_source_sha": SOURCE_SHA,
            "build_identity_sha256": build_identity,
            "sbom_sha256": sbom_identity,
            "tag_reference": None,
            "tag_resolved_digest": None,
        },
    }


def test_exact_release_identity_is_pass_and_deterministic() -> None:
    first = evaluate_release_artifact_identity(ROOT, _evidence())
    second = evaluate_release_artifact_identity(ROOT, _evidence())

    assert first == second
    assert first["contract"] == CONTRACT
    assert first["state"] == "PASS"
    assert first["block_reasons"] == []
    assert first["release_identity"].startswith("sha256:")
    assert len(first["release_identity"]) == 71
    assert first["release_manifest"]["image"]["digest"] == IMAGE_DIGEST
    assert first["tag_evidence"]["tag_is_release_identity"] is False
    assert first["build_release_evidence_only"] is True
    assert first["deployed_runtime_state_proven"] is False
    assert first["authority"]["runtime_live"] is False
    assert first["authority"]["registry_push"] is False
    assert first["production_mutation_performed"] is False


def test_rebuilt_image_from_changed_source_is_blocked() -> None:
    evidence = _evidence()
    evidence["image"]["built_source_sha"] = "c" * 40

    result = evaluate_release_artifact_identity(ROOT, evidence)

    assert result["state"] == "BLOCKED"
    assert "IMAGE_SOURCE_SHA_MISMATCH" in result["block_reasons"]
    assert result["release_identity"] is None


def test_reused_mutable_tag_with_different_digest_is_blocked() -> None:
    evidence = _evidence()
    evidence["image"]["tag_reference"] = f"{IMAGE_REPOSITORY}:public"
    evidence["image"]["tag_resolved_digest"] = "sha256:" + "c" * 64

    result = evaluate_release_artifact_identity(ROOT, evidence)

    assert result["state"] == "BLOCKED"
    assert "MUTABLE_TAG_REUSED_DIFFERENT_DIGEST" in result["block_reasons"]
    assert result["tag_evidence"]["tag_is_release_identity"] is False


def test_missing_digest_and_tag_only_reference_are_blocked() -> None:
    evidence = _evidence()
    evidence["image"]["digest"] = ""
    evidence["image"]["reference"] = f"{IMAGE_REPOSITORY}:latest"

    result = evaluate_release_artifact_identity(ROOT, evidence)

    assert result["state"] == "BLOCKED"
    assert "IMAGE_DIGEST_MISSING" in result["block_reasons"]
    assert "MUTABLE_TAG_ONLY_REFERENCE" in result["block_reasons"]


def test_stale_runtime_descriptor_identity_is_blocked() -> None:
    evidence = _evidence()
    evidence["runtime_descriptor_sha256"] = "d" * 64

    result = evaluate_release_artifact_identity(ROOT, evidence)

    assert result["state"] == "BLOCKED"
    assert "RUNTIME_DESCRIPTOR_MISMATCH" in result["block_reasons"]


def test_stale_sbom_identity_is_blocked() -> None:
    evidence = deepcopy(_evidence())
    evidence["build_evidence"]["sbom"]["packages"].append(
        {
            "name": "unexpected-package",
            "version": "1.0.0",
            "purl": "pkg:pypi/unexpected-package@1.0.0",
            "scope": "runtime-transitive",
        }
    )

    result = evaluate_release_artifact_identity(ROOT, evidence)

    assert result["state"] == "BLOCKED"
    assert "STALE_SBOM_IDENTITY" in result["block_reasons"]


def test_source_build_identity_mismatch_is_blocked() -> None:
    evidence = _evidence()
    evidence["source_sha"] = "c" * 40
    evidence["image"]["built_source_sha"] = "c" * 40

    result = evaluate_release_artifact_identity(ROOT, evidence)

    assert result["state"] == "BLOCKED"
    assert "SOURCE_BUILD_IDENTITY_MISMATCH" in result["block_reasons"]


def test_matching_tag_resolution_is_allowed_but_not_identity() -> None:
    evidence = _evidence()
    evidence["image"]["tag_reference"] = f"{IMAGE_REPOSITORY}:public"
    evidence["image"]["tag_resolved_digest"] = IMAGE_DIGEST

    result = evaluate_release_artifact_identity(ROOT, evidence)

    assert result["state"] == "PASS"
    assert result["tag_evidence"] == {
        "tag_reference": f"{IMAGE_REPOSITORY}:public",
        "tag_resolved_digest": IMAGE_DIGEST,
        "tag_is_release_identity": False,
    }
