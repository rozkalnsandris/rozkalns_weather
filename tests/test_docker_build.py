from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_package_install_uses_pep517_build_isolation() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    pyproject = (ROOT / "pyproject.toml").read_text()

    assert 'requires = ["setuptools>=75"]' in pyproject
    assert "python -m pip install --no-cache-dir --no-deps ." in dockerfile
    assert "--no-build-isolation" not in dockerfile
