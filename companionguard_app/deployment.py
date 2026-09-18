from __future__ import annotations

import json
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

    manifest = load_deployment_manifest(seed_root)
    if manifest is not None:
        current = _read_runtime_metadata(runtime_root) if runtime_root.is_dir() else None
        expected = _runtime_metadata(manifest)
        if current == expected and runtime_root.is_dir():
            return False
        try:
            _materialize_versioned_runtime(seed_root, runtime_root, manifest)
        except (OSError, PublishingError) as exc:
            raise RuntimeError(f"Unable to refresh Published runtime: {exc}") from exc
        return True

    if runtime_root.exists():
        return False

    runtime_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(seed_root, runtime_root, dirs_exist_ok=False)
    except FileExistsError:
        return False
    return True
