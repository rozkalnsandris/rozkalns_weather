from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import tomllib
from typing import Sequence

CONTRACT = "container-build-reproducibility-v1"
SCHEMA_VERSION = 1
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_LOCK_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)$")
_DEP_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_NUMERIC_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _normalize_copy_source(value: str) -> str:
    normalized = value.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def _parse_lock(text: str) -> tuple[list[dict[str, str]], list[str]]:
    packages: list[dict[str, str]] = []
    reasons: list[str] = []
    seen: set[str] = set()
    previous: str | None = None
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LOCK_RE.fullmatch(line)
        if not match:
            reasons.append(f"UNPINNED_OR_AMBIGUOUS_LOCK_ENTRY:{line_number}")
            continue
        name, version = match.groups()
        normalized = _normalize_name(name)
        if normalized in seen:
            reasons.append(f"DUPLICATE_LOCK_PACKAGE:{normalized}")
            continue
        if previous is not None and normalized < previous:
            reasons.append("LOCK_ORDER_NOT_DETERMINISTIC")
        previous = normalized
        seen.add(normalized)
        packages.append({"name": normalized, "version": version})
    if not packages:
        reasons.append("EMPTY_DEPENDENCY_LOCK")
    return packages, reasons


def _dependency_name(spec: str) -> str | None:
    match = _DEP_NAME_RE.match(spec)
    return _normalize_name(match.group(1)) if match else None


def _numeric_version(value: str) -> tuple[int, ...] | None:
    if not _NUMERIC_VERSION_RE.fullmatch(value):
        return None
    return tuple(int(part) for part in value.split("."))


def _compare_versions(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    l_value = left + (0,) * (width - len(left))
    r_value = right + (0,) * (width - len(right))
    return (l_value > r_value) - (l_value < r_value)


def _locked_version_satisfies(spec: str, locked_version: str) -> bool:
    parsed = _numeric_version(locked_version)
    if parsed is None:
        return True
    name = _DEP_NAME_RE.match(spec)
    if not name:
        return False
    tail = spec[name.end():]
    for clause in tail.split(","):
        clause = clause.strip()
        if not clause:
            continue
        matched = re.fullmatch(r"(>=|<=|==|>|<)\s*(\d+(?:\.\d+)*)", clause)
        if not matched:
            continue
        operator, wanted = matched.groups()
        wanted_version = _numeric_version(wanted)
        if wanted_version is None:
            continue
        comparison = _compare_versions(parsed, wanted_version)
        if operator == ">=" and comparison < 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
        if operator == "==" and comparison != 0:
            return False
    return True


def _docker_copy_sources(text: str) -> tuple[list[str], list[str]]:
    sources: list[str] = []
    reasons: list[str] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or not stripped.upper().startswith("COPY "):
            continue
        try:
            parts = shlex.split(stripped)
        except ValueError:
            reasons.append(f"INVALID_DOCKER_COPY_SYNTAX:{line_number}")
            continue
        if len(parts) < 3 or parts[0].upper() != "COPY":
            reasons.append(f"INVALID_DOCKER_COPY_SYNTAX:{line_number}")
            continue
        if any(part.startswith("--from=") for part in parts[1:-1]):
            reasons.append(f"MULTISTAGE_COPY_NOT_ALLOWED:{line_number}")
            continue
        sources.extend(part for part in parts[1:-1] if not part.startswith("--"))
    return sources, reasons


def _docker_from(text: str) -> tuple[str | None, list[str]]:
    values: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            if len(parts) >= 2:
                values.append(parts[1])
    if len(values) != 1:
        return (values[0] if values else None), ["DOCKERFILE_MUST_HAVE_ONE_BASE_IMAGE"]
    return values[0], []


def _load_contract(repo_root: Path) -> dict[str, object]:
    path = repo_root / "deploy" / "container-build-reproducibility.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _blocked_payload(reason: str) -> dict[str, object]:
    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "state": "BLOCKED",
        "block_reasons": [reason],
        "warn_reasons": [],
        "source_only": True,
        "production_mutation_performed": False,
        "authority": {
            "registry_push": False,
            "runtime_live": False,
            "production_image_deploy": False,
            "credentials_or_secrets": False,
        },
    }


def build_evidence(
    repo_root: Path,
    *,
    source_sha: str,
    observed_source_sha: str | None,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    block_reasons: list[str] = []
    warn_reasons: list[str] = []

    if not _SHA40_RE.fullmatch(source_sha):
        block_reasons.append("INVALID_SOURCE_SHA")
    if observed_source_sha is None:
        warn_reasons.append("OBSERVED_SOURCE_SHA_UNAVAILABLE")
    elif not _SHA40_RE.fullmatch(observed_source_sha):
        block_reasons.append("INVALID_OBSERVED_SOURCE_SHA")
    elif observed_source_sha != source_sha:
        block_reasons.append("SOURCE_SHA_MISMATCH")

    try:
        contract = _load_contract(repo_root)
    except (OSError, json.JSONDecodeError):
        return _blocked_payload("BUILD_CONTRACT_UNREADABLE")

    if contract.get("contract") != CONTRACT or contract.get("schema_version") != SCHEMA_VERSION:
        block_reasons.append("BUILD_CONTRACT_SCHEMA_MISMATCH")

    required_files = tuple(str(item) for item in contract.get("required_inputs", []))
    input_hashes: dict[str, str] = {}
    for relative in required_files:
        path = repo_root / relative
        if not path.is_file():
            block_reasons.append(f"REQUIRED_BUILD_INPUT_MISSING:{relative}")
            continue
        input_hashes[relative] = _sha256_file(path)

    dockerfile_path = repo_root / str(contract.get("dockerfile", "Dockerfile"))
    lock_path = repo_root / str(contract.get("dependency_lock", "deploy/public-runtime.lock"))
    pyproject_path = repo_root / "pyproject.toml"
    runtime_descriptor_path = repo_root / str(contract.get("runtime_descriptor", "deploy/runtime-descriptor.json"))

    try:
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
    except OSError:
        dockerfile_text = ""
        block_reasons.append("DOCKERFILE_UNREADABLE")

    base_image, docker_reasons = _docker_from(dockerfile_text)
    block_reasons.extend(docker_reasons)
    if base_image != contract.get("base_image"):
        block_reasons.append("BASE_IMAGE_IDENTITY_MISMATCH")
    if base_image and "@sha256:" not in base_image:
        block_reasons.append("BASE_IMAGE_DIGEST_UNPINNED")

    copy_sources, copy_reasons = _docker_copy_sources(dockerfile_text)
    block_reasons.extend(copy_reasons)
    allowed_copy_sources = {_normalize_copy_source(str(item)) for item in contract.get("allowed_copy_sources", [])}
    normalized_copy_sources = {_normalize_copy_source(item) for item in copy_sources}
    for item in sorted(normalized_copy_sources - allowed_copy_sources):
        block_reasons.append(f"UNEXPECTED_RUNTIME_COPY_SOURCE:{item}")
    for item in sorted(allowed_copy_sources - normalized_copy_sources):
        block_reasons.append(f"REQUIRED_RUNTIME_COPY_SOURCE_MISSING:{item}")
    if ".[weathernext]" in dockerfile_text or "[weathernext]" in dockerfile_text:
        block_reasons.append("PUBLIC_RUNTIME_WEATHERNEXT_EXTRA_FORBIDDEN")
    if "--no-deps" not in dockerfile_text or "--no-build-isolation" not in dockerfile_text:
        block_reasons.append("PROJECT_INSTALL_NOT_LOCK_ISOLATED")

    try:
        lock_text = lock_path.read_text(encoding="utf-8")
    except OSError:
        lock_text = ""
        block_reasons.append("DEPENDENCY_LOCK_UNREADABLE")
    packages, lock_reasons = _parse_lock(lock_text)
    block_reasons.extend(lock_reasons)
    lock_sha256 = _sha256_bytes(lock_text.encode("utf-8"))
    expected_lock_sha = str(contract.get("dependency_lock_sha256", ""))
    if expected_lock_sha and lock_sha256 != expected_lock_sha:
        block_reasons.append("DEPENDENCY_LOCK_CHECKSUM_MISMATCH")

    package_versions = {item["name"]: item["version"] for item in packages}

    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        pyproject = {}
        block_reasons.append("PYPROJECT_UNREADABLE")

    project = pyproject.get("project", {}) if isinstance(pyproject, dict) else {}
    dependencies = project.get("dependencies", []) if isinstance(project, dict) else []
    direct_specs = [str(item) for item in dependencies]
    direct_names = [name for spec in direct_specs if (name := _dependency_name(spec))]
    expected_direct = [_normalize_name(str(item)) for item in contract.get("public_runtime_direct_dependencies", [])]
    if sorted(direct_names) != sorted(expected_direct):
        block_reasons.append("DIRECT_DEPENDENCY_SET_MISMATCH")
    for spec in direct_specs:
        name = _dependency_name(spec)
        if not name:
            block_reasons.append("AMBIGUOUS_DIRECT_DEPENDENCY")
            continue
        locked = package_versions.get(name)
        if locked is None:
            block_reasons.append(f"DIRECT_DEPENDENCY_NOT_LOCKED:{name}")
        elif not _locked_version_satisfies(spec, locked):
            block_reasons.append(f"LOCKED_VERSION_OUTSIDE_DECLARED_RANGE:{name}")

    build_system = pyproject.get("build-system", {}) if isinstance(pyproject, dict) else {}
    for spec in build_system.get("requires", []) if isinstance(build_system, dict) else []:
        name = _dependency_name(str(spec))
        if not name:
            continue
        locked = package_versions.get(name)
        if locked is None:
            block_reasons.append(f"BUILD_DEPENDENCY_NOT_LOCKED:{name}")
        elif not _locked_version_satisfies(str(spec), locked):
            block_reasons.append(f"BUILD_LOCK_OUTSIDE_DECLARED_RANGE:{name}")

    forbidden_packages = {_normalize_name(str(item)) for item in contract.get("forbidden_public_runtime_packages", [])}
    for item in sorted(forbidden_packages & set(package_versions)):
        block_reasons.append(f"FORBIDDEN_PUBLIC_RUNTIME_PACKAGE:{item}")

    try:
        runtime_descriptor = json.loads(runtime_descriptor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        runtime_descriptor = {}
        block_reasons.append("RUNTIME_DESCRIPTOR_UNREADABLE")
    expected_runtime = contract.get("expected_runtime", {})
    if isinstance(expected_runtime, dict):
        if runtime_descriptor.get("runtime_class") != expected_runtime.get("runtime_class"):
            block_reasons.append("RUNTIME_CLASS_MISMATCH")
        if runtime_descriptor.get("target_alias") != expected_runtime.get("target_alias"):
            block_reasons.append("TARGET_ALIAS_MISMATCH")
        runtime_contract = runtime_descriptor.get("runtime_contract", {})
        if not isinstance(runtime_contract, dict) or runtime_contract.get("runtime_mode") != expected_runtime.get("runtime_mode"):
            block_reasons.append("RUNTIME_MODE_MISMATCH")
        if not isinstance(runtime_contract, dict) or runtime_contract.get("weathernext_required") is not False:
            block_reasons.append("PUBLIC_RUNTIME_WEATHERNEXT_REQUIREMENT_MISMATCH")

    package_entries: list[dict[str, str]] = []
    direct_set = set(expected_direct)
    build_tools = {_normalize_name(str(item)) for item in contract.get("build_tool_packages", [])}
    for item in packages:
        name = item["name"]
        scope = "runtime-direct" if name in direct_set else "build-tool" if name in build_tools else "runtime-transitive"
        package_entries.append(
            {
                "name": name,
                "version": item["version"],
                "purl": f"pkg:pypi/{name}@{item['version']}",
                "scope": scope,
            }
        )

    sbom = {
        "schema": "rozkalns.python-runtime-sbom.v1",
        "runtime_class": str(contract.get("runtime_class", "")),
        "source_sha": source_sha,
        "dependency_lock": str(contract.get("dependency_lock", "")),
        "dependency_lock_sha256": lock_sha256,
        "packages": package_entries,
        "expected_console_scripts": sorted(str(item) for item in contract.get("expected_console_scripts", [])),
        "runtime_copy_sources": sorted(normalized_copy_sources),
    }
    sbom_sha256 = _sha256_bytes(_canonical_json(sbom).encode("utf-8"))

    build_identity_payload = {
        "contract": CONTRACT,
        "source_sha": source_sha,
        "base_image": base_image,
        "inputs": input_hashes,
        "sbom_sha256": sbom_sha256,
        "runtime_class": str(contract.get("runtime_class", "")),
        "target_alias": runtime_descriptor.get("target_alias"),
    }
    build_identity_sha256 = _sha256_bytes(_canonical_json(build_identity_payload).encode("utf-8"))

    block_reasons = list(dict.fromkeys(block_reasons))
    warn_reasons = list(dict.fromkeys(warn_reasons))
    state = "BLOCKED" if block_reasons else "WARN" if warn_reasons else "PASS"

    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "block_reasons": block_reasons,
        "warn_reasons": warn_reasons,
        "source_only": True,
        "source_identity": {
            "expected_source_sha": source_sha,
            "observed_source_sha": observed_source_sha,
            "match": observed_source_sha == source_sha if observed_source_sha is not None else None,
        },
        "build": {
            "runtime_class": str(contract.get("runtime_class", "")),
            "target_alias": runtime_descriptor.get("target_alias"),
            "base_image": base_image,
            "input_sha256": input_hashes,
            "dependency_lock_sha256": lock_sha256,
            "sbom_sha256": sbom_sha256,
            "build_identity_sha256": build_identity_sha256,
        },
        "sbom": sbom,
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
            "credentials_or_secrets": False,
            "release_activation": False,
        },
        "production_mutation_performed": False,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate public-only reproducible container build evidence")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--observed-source-sha")
    parser.add_argument("--output")
    parser.add_argument("--sbom-output")
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args(argv)

    try:
        payload = build_evidence(
            Path(args.repo_root),
            source_sha=args.source_sha.lower(),
            observed_source_sha=args.observed_source_sha.lower() if args.observed_source_sha else None,
        )
    except Exception:
        payload = _blocked_payload("BUILD_EVIDENCE_EXECUTION_ERROR")

    if args.output:
        _write_json(Path(args.output), payload)
    if args.sbom_output and "sbom" in payload:
        _write_json(Path(args.sbom_output), payload["sbom"])

    print(json.dumps(payload, sort_keys=True))
    if payload["state"] == "BLOCKED":
        return 3
    if args.require_pass and payload["state"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
