from __future__ import annotations

import json
from pathlib import Path
import shutil

from rozkalns_weather.build_evidence import CONTRACT, build_evidence, main

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "deploy").mkdir(parents=True)
    (root / "src").mkdir()
    for relative in (
        "Dockerfile",
        "pyproject.toml",
        "README.md",
        ".dockerignore",
        "deploy/public-runtime.lock",
        "deploy/container-build-reproducibility.json",
        "deploy/runtime-descriptor.json",
        "deploy/docker-compose.public.yml",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return root


def test_repository_build_evidence_is_pass_and_deterministic() -> None:
    first = build_evidence(ROOT, source_sha=SHA, observed_source_sha=SHA)
    second = build_evidence(ROOT, source_sha=SHA, observed_source_sha=SHA)

    assert first["contract"] == CONTRACT
    assert first["state"] == "PASS"
    assert first["block_reasons"] == []
    assert first["warn_reasons"] == []
    assert first["build"]["build_identity_sha256"] == second["build"]["build_identity_sha256"]
    assert first["build"]["sbom_sha256"] == second["build"]["sbom_sha256"]
    assert first["sbom"]["dependency_lock_sha256"] == first["build"]["dependency_lock_sha256"]
    assert len(first["sbom"]["packages"]) == 18
    assert {item["scope"] for item in first["sbom"]["packages"]} >= {
        "runtime-direct",
        "runtime-transitive",
        "build-tool",
    }
    assert first["authority"]["runtime_live"] is False
    assert first["authority"]["registry_push"] is False
    assert first["production_mutation_performed"] is False


def test_source_identity_mismatch_blocks() -> None:
    payload = build_evidence(ROOT, source_sha=SHA, observed_source_sha="b" * 40)
    assert payload["state"] == "BLOCKED"
    assert "SOURCE_SHA_MISMATCH" in payload["block_reasons"]


def test_unpinned_dependency_entry_blocks_without_echoing_value(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    lock_path = root / "deploy" / "public-runtime.lock"
    lock_path.write_text(lock_path.read_text(encoding="utf-8") + "unsafe-package>=1\n", encoding="utf-8")

    payload = build_evidence(root, source_sha=SHA, observed_source_sha=SHA)

    assert payload["state"] == "BLOCKED"
    assert any(reason.startswith("UNPINNED_OR_AMBIGUOUS_LOCK_ENTRY:") for reason in payload["block_reasons"])
    assert "unsafe-package>=1" not in json.dumps(payload)


def test_unexpected_runtime_copy_source_blocks(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    dockerfile = root / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            "COPY src ./src",
            "COPY src ./src\nCOPY .env.example ./.env.example",
        ),
        encoding="utf-8",
    )

    payload = build_evidence(root, source_sha=SHA, observed_source_sha=SHA)

    assert payload["state"] == "BLOCKED"
    assert "UNEXPECTED_RUNTIME_COPY_SOURCE:.env.example" in payload["block_reasons"]


def test_public_runtime_rejects_weathernext_extra(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    dockerfile = root / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            "--no-deps --no-build-isolation .",
            "--no-deps --no-build-isolation '.[weathernext]'",
        ),
        encoding="utf-8",
    )

    payload = build_evidence(root, source_sha=SHA, observed_source_sha=SHA)

    assert payload["state"] == "BLOCKED"
    assert "PUBLIC_RUNTIME_WEATHERNEXT_EXTRA_FORBIDDEN" in payload["block_reasons"]


def test_cli_writes_machine_evidence_and_sbom(tmp_path: Path, capsys) -> None:
    evidence = tmp_path / "evidence.json"
    sbom = tmp_path / "sbom.json"

    rc = main(
        [
            "--repo-root",
            str(ROOT),
            "--source-sha",
            SHA,
            "--observed-source-sha",
            SHA,
            "--require-pass",
            "--output",
            str(evidence),
            "--sbom-output",
            str(sbom),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert stdout["state"] == "PASS"
    assert json.loads(evidence.read_text(encoding="utf-8"))["state"] == "PASS"
    assert json.loads(sbom.read_text(encoding="utf-8"))["schema"] == "rozkalns.python-runtime-sbom.v1"


def test_cli_warns_when_observed_sha_is_unavailable(capsys) -> None:
    rc = main(["--repo-root", str(ROOT), "--source-sha", SHA])
    output = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output["state"] == "WARN"
    assert output["warn_reasons"] == ["OBSERVED_SOURCE_SHA_UNAVAILABLE"]
