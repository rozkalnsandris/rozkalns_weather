from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_package_install_uses_pep517_build_isolation() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    pyproject = (ROOT / "pyproject.toml").read_text()

    assert 'requires = ["setuptools>=75"]' in pyproject
    assert "python -m pip install --no-cache-dir --no-deps ." in dockerfile
    assert "--no-build-isolation" not in dockerfile


def test_simple_deploy_requires_explicit_dispatch_after_merge() -> None:
    workflow = (ROOT / ".github" / "workflows" / "simple-deploy.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "\n  push:" not in workflow
