from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_image_imports_source_directly_without_local_wheel_build() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "ENV PYTHONPATH=/app/src" in dockerfile
    assert "COPY src ./src" in dockerfile
    assert "pip install --no-cache-dir --no-deps ." not in dockerfile
    assert "COPY pyproject.toml README.md ./" not in dockerfile


def test_public_ingest_uses_module_entrypoint_in_runtime_image() -> None:
    compose = (ROOT / "deploy" / "docker-compose.public.yml").read_text()

    assert 'command: ["python", "-m", "rozkalns_weather", "ingest-public"]' in compose
    assert 'command: ["rozkalns-weather", "ingest-public"]' not in compose


def test_simple_deploy_requires_explicit_dispatch_after_merge() -> None:
    workflow = (ROOT / ".github" / "workflows" / "simple-deploy.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "\n  push:" not in workflow
