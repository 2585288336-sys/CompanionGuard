from __future__ import annotations

import json
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from .config import PROJECT_ROOT
from .publishing import (
    DEPLOYMENT_MANIFEST,
    RUNTIME_MANIFEST,
    PublishingError,
    atomic_promote,
    load_deployment_manifest,
    verify_manifest_content,
    _copy_file_stream,
)


DEPLOYMENT_PROJECT_ID = "CompanionGuard-Formal-Full-Benchmark-2026-09"
_VERIFIED_RUNTIME_KEYS: set[tuple[str, str, str]] = set()


def _runtime_metadata(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "metadata_version": "1.0",
        "project_id": manifest["project_id"],
        "published_version": manifest["published_version"],
        "source_snapshot_hash": manifest["source_snapshot_hash"],
        "content_hash_algorithm": manifest.get("content_hash_algorithm", "SHA-256"),
    }


def _read_runtime_metadata(runtime_root: Path) -> dict[str, object] | None:
    path = runtime_root / RUNTIME_MANIFEST
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _manifest_files(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise PublishingError("Deployment manifest files must be an object")
    validated: dict[str, dict[str, object]] = {}
    for relative, details in files.items():
        relative_path = Path(str(relative))
        if (
            relative_path.is_absolute()
            or not relative_path.parts
            or ".." in relative_path.parts
            or "\\" in str(relative)
        ):
            raise PublishingError(f"Unsafe path in deployment manifest: {relative}")
        if not isinstance(details, dict) or not isinstance(details.get("sha256"), str) or not isinstance(details.get("bytes"), int):
            raise PublishingError(f"Invalid file record in deployment manifest: {relative}")
        validated[relative_path.as_posix()] = details
    return validated


def _streaming_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def verify_published_runtime_integrity(
    runtime_project_root: str | Path,
    deployment_manifest: dict[str, object],
) -> dict[str, object]:
    """Verify versioned Published project files against the seed manifest."""

    expected = _manifest_files(deployment_manifest)
    runtime_root = Path(runtime_project_root)
    missing: list[str] = []
    modified: list[str] = []
    checked = 0

    if runtime_root.is_dir() and not runtime_root.is_symlink():
        resolved_root = runtime_root.resolve()
        for relative, details in expected.items():
            candidate = runtime_root / relative
            try:
                resolved_candidate = candidate.resolve()
                inside_root = resolved_candidate.is_relative_to(resolved_root)
            except OSError:
                inside_root = False
            if candidate.is_symlink() or not inside_root or not candidate.is_file():
                missing.append(relative)
                continue
            checked += 1
            size, digest = _streaming_digest(candidate)
            if size != int(details["bytes"]) or digest != str(details["sha256"]):
                modified.append(relative)

    else:
        missing.extend(sorted(expected))

    unexpected: list[str] = []
    expected_paths = set(expected)
    if runtime_root.is_dir() and not runtime_root.is_symlink():
        for current, directories, filenames in os.walk(runtime_root, topdown=True, followlinks=False):
            current_path = Path(current)
            for directory in sorted(directories):
                candidate = current_path / directory
                if candidate.is_symlink():
                    unexpected.append(candidate.relative_to(runtime_root).as_posix())
            for filename in sorted(filenames):
                candidate = current_path / filename
                relative = candidate.relative_to(runtime_root).as_posix()
                if relative == RUNTIME_MANIFEST:
                    continue
                if relative not in expected_paths:
                    unexpected.append(relative)

    return {
        "valid": not missing and not modified and not unexpected,
        "missing_files": sorted(set(missing)),
        "modified_files": sorted(set(modified)),
        "unexpected_files": sorted(set(unexpected)),
        "expected_file_count": len(expected),
        "actual_checked_count": checked,
    }


def _materialize_versioned_runtime(seed_root: Path, runtime_root: Path, manifest: dict[str, object]) -> None:
    runtime_parent = runtime_root.parent
    runtime_parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{runtime_root.name}-", dir=runtime_parent))
    try:
        for relative in manifest["files"]:
            _copy_file_stream(seed_root / relative, temp_root / relative)
        (temp_root / RUNTIME_MANIFEST).write_text(
            json.dumps(_runtime_metadata(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verify_manifest_content(temp_root, manifest)
        atomic_promote(temp_root, runtime_root)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def ensure_deployment_project(
    *,
    project_id: str = DEPLOYMENT_PROJECT_ID,
    project_root: Path = PROJECT_ROOT,
) -> bool:
    """Materialize or safely refresh the immutable Published runtime.

    A seed without ``deployment_manifest.json`` keeps the legacy copy-once
    behavior.  A versioned seed is refreshed atomically only when its version
    or content hash differs.  Workspace directories are never inspected.
    """
    seed_root = project_root / "data" / "deployment_seed" / project_id
    runtime_root = project_root / "data" / "projects" / project_id
    if not seed_root.is_dir():
        return False

    try:
        manifest = load_deployment_manifest(seed_root)
    except (OSError, PublishingError) as exc:
        raise RuntimeError(f"Unable to validate Published deployment seed: {exc}") from exc
    if manifest is not None:
        current = _read_runtime_metadata(runtime_root) if runtime_root.is_dir() else None
        expected = _runtime_metadata(manifest)
        cache_key = (
            str(runtime_root.resolve()),
            str(expected["published_version"]),
            str(expected["source_snapshot_hash"]),
        )
        cacheable_root = Path(project_root).resolve() == PROJECT_ROOT.resolve()
        if current == expected and runtime_root.is_dir() and cacheable_root and cache_key in _VERIFIED_RUNTIME_KEYS:
            return False
        try:
            _manifest_files(manifest)
            verify_manifest_content(seed_root, manifest)
        except (OSError, PublishingError) as exc:
            raise RuntimeError(f"Unable to validate Published deployment seed: {exc}") from exc
        if current == expected and runtime_root.is_dir() and verify_published_runtime_integrity(runtime_root, manifest)["valid"]:
            if cacheable_root:
                _VERIFIED_RUNTIME_KEYS.add(cache_key)
            return False
        try:
            _materialize_versioned_runtime(seed_root, runtime_root, manifest)
        except (OSError, PublishingError) as exc:
            raise RuntimeError(f"Unable to refresh Published runtime: {exc}") from exc
        if cacheable_root:
            _VERIFIED_RUNTIME_KEYS.add(cache_key)
        return True

    if runtime_root.exists():
        return False

    runtime_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(seed_root, runtime_root, dirs_exist_ok=False)
    except FileExistsError:
        return False
    return True
