from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_SHA = "e05ed760791a127c7c9628696806ef39c9fe329c"
RPI5_SHA = "ff20fcf64ba62c95e5f15eeb481c3c66bb5c9708"
IMAGE = "ghcr.io/rozkalnsandris/rozkalns_weather"
TARGET = "rozkalns-weather-public-rpi5"


def _manifest() -> dict[str, object]:
    return json.loads((ROOT / ".simple-deploy.json").read_text())


def test_manifest_is_fixed_weather_consumer_contract() -> None:
    manifest = _manifest()
    assert manifest == {
        "schema": "rozkalns.simple-deploy.consumer.v1",
        "repository": "rozkalnsandris/rozkalns_weather",
        "image": IMAGE,
        "build": {"context": ".", "dockerfile": "Dockerfile", "architecture": "linux/arm64"},
        "target": {"alias": TARGET, "runtime_class": "rpi5-compose"},
        "compose": {"project": "rozkalns-weather-public", "file": "deploy/docker-compose.public.yml", "service": "weather"},
        "health": {"liveness_path": "/health", "readiness": {"state": "required", "path": "/ready"}},
        "persistence": {"volumes": ["weather_data"]},
        "registry": {"pull_profile": "public-anonymous-pull"},
        "forbidden_operations": [
            "database-schema-data-mutation",
            "destructive-recovery",
            "secrets-credentials-permissions",
            "cloudflare-dns-network",
            "private-provider-activation",
            "unrelated-host-control",
        ],
    }


def test_caller_is_tiny_immutable_and_least_privilege() -> None:
    caller = (ROOT / ".github/workflows/simple-deploy.yml").read_text()
    assert f"uses: rozkalnsandris/ops-workflows/.github/workflows/simple-deploy.yml@{SHARED_SHA} # v1.0.0" in caller
    assert "branches: [main]" in caller
    assert "source_sha: ${{ github.sha }}" in caller
    assert "contents: read" in caller
    assert "packages: write" in caller
    assert "@main" not in caller
    assert "self-hosted" not in caller
    for forbidden in ("ssh ", "sudo ", "docker compose", "HOME_LAT", "HOME_LON", "secrets."):
        assert forbidden not in caller


def test_production_compose_is_image_based_and_keeps_data_boundary() -> None:
    compose = (ROOT / "deploy/docker-compose.public.yml").read_text()
    assert "build:" not in compose
    assert compose.count(f"image: {IMAGE}:production") == 5
    assert "weather_data:/app/data" in compose
    assert "DATABASE_INIT_MODE: require-existing" in compose
    assert "WEATHER_RUNTIME_MODE: public-only" in compose
    assert "depends_on:" not in compose
    assert "env_file:" not in compose
    assert "HOME_LAT" not in compose
    assert "HOME_LON" not in compose
    assert "/ready" in compose


def test_machine_contracts_mark_simple_deploy_current_and_old_control_plane_legacy() -> None:
    runtime = json.loads((ROOT / "deploy/runtime-descriptor.json").read_text())
    current = runtime["deployment_architecture"]
    assert current["current"] == "SIMPLE_DEPLOY_V1_CANARY_SOURCE"
    assert current["shared_workflow_sha"] == SHARED_SHA
    assert current["generic_runtime_source_sha"] == RPI5_SHA
    assert current["deployment_identity"] == "immutable_registry_digest"
    assert current["source_merge_authorizes_live"] is False

    binding = json.loads((ROOT / "deploy/rpi5-source-binding.json").read_text())
    assert binding["lifecycle"]["current_ordinary_release_role"] == "LEGACY_SUPERSEDED"
    assert binding["lifecycle"]["generic_rpi5_deployer_source_sha"] == RPI5_SHA

    preflight = json.loads((ROOT / "deploy/first-public-rollout-preflight.json").read_text())
    assert preflight["lifecycle"]["required_by_current_ordinary_release"] is False
    readiness = json.loads((ROOT / "deploy/rollout-readiness.json").read_text())
    assert readiness["lifecycle"]["old_queue_operator_jit_required_for_current_ordinary_release"] is False


def test_current_docs_name_simple_deploy_and_legacy_boundary() -> None:
    required = [
        "README.md", "docs/ROADMAP.md", "docs/IMPLEMENTATION_STATUS.md", "docs/OPERATIONS.md",
        "docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md", "docs/ARCHITECTURE.md", "docs/RELEASE_READINESS_MATRIX.md",
        "docs/SIMPLE_DEPLOY_CANARY.md", ".agents/skills/rozkalns-weather/SKILL.md", "AGENTS.md",
    ]
    for relative in required:
        text = (ROOT / relative).read_text()
        assert "SIMPLE-DEPLOY" in text, relative
    for relative in (
        "README.md", "docs/ROADMAP.md", "docs/IMPLEMENTATION_STATUS.md",
        "docs/OPERATIONS.md", "docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md",
    ):
        text = (ROOT / relative).read_text().lower()
        assert "legacy" in text or "superseded" in text, relative


def test_public_anonymous_pull_requires_verified_package_visibility() -> None:
    text = (ROOT / "docs/SIMPLE_DEPLOY_CANARY.md").read_text()
    assert "actually anonymous-pullable" in text
    assert "package visibility remains a GitHub Packages setting" in text
    assert "separate exact owner authorization" in text
    assert "private-read-only" in text
