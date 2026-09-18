"""Read-only export of the currently active project context."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .runtime_scope import RuntimeScope, validate_scope_id
from .runtime_workspace import RuntimeContext


EXPORT_FORMAT_VERSION = "1"
MANIFEST_NAME = "EXPORT_MANIFEST.json"
CHECKSUMS_NAME = "SHA256SUMS.txt"


class ProjectExportError(RuntimeError):
    """Raised when a project package cannot be built safely."""


@dataclass(frozen=True)
class ProjectPackage:
    """The in-memory download artifact and its safe client-side filename."""

    data: bytes
    filename: str
    manifest: dict[str, object]


@dataclass(frozen=True)
class _ProjectFile:
    source: Path
    relative: Path
    size: int
    digest: str


@dataclass(frozen=True)
class _Discovery:
    files: list[_ProjectFile]
    excluded: list[str]


_INFRA_FILE_NAMES = {
    ".env",
    ".workspace_manifest.json",
    ".ds_store",
    "secrets.toml",
}
_INFRA_DIR_NAMES = {".git", "__pycache__"}
_SECRET_FILE_RE = re.compile(
    r"(?:credential|credentials|api[_-]?key|access[_-]?token|private[_-]?key|password)",
    re.IGNORECASE,
)


def _is_excluded(relative: Path) -> bool:
    parts = relative.parts
    if any(part in _INFRA_DIR_NAMES for part in parts):
        return True
    name = relative.name.lower()
    if name in _INFRA_FILE_NAMES or name.endswith(".env"):
        return True
    # Keep normal evidence files, including images.  Only explicitly
    # credential-like filenames are excluded from the project package.
    return bool(_SECRET_FILE_RE.search(name))


def _safe_relative(source_root: Path, candidate: Path) -> Path:
    try:
        relative = candidate.relative_to(source_root)
    except ValueError as exc:
        raise ProjectExportError("Project file escaped the active project root") from exc
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ProjectExportError(f"Unsafe project-relative path: {relative}")
    return relative


def _digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _discover_files(root: Path) -> _Discovery:
    if not root.is_dir() or root.is_symlink():
        raise ProjectExportError("Active project root does not exist or is a symlink")
    resolved_root = root.resolve()
    discovered: list[_ProjectFile] = []
    excluded: list[str] = []
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for directory in sorted(directories):
            directory_path = current_path / directory
            relative = _safe_relative(root, directory_path)
            if directory_path.is_symlink() or _is_excluded(relative):
                excluded.append(relative.as_posix())
            else:
                kept_directories.append(directory)
        directories[:] = kept_directories
        for filename in sorted(filenames):
            candidate = current_path / filename
            relative = _safe_relative(root, candidate)
            if candidate.is_symlink() or _is_excluded(relative):
                excluded.append(relative.as_posix())
                continue
            try:
                if not candidate.resolve().is_relative_to(resolved_root):
                    excluded.append(relative.as_posix())
                    continue
                if not candidate.is_file():
                    excluded.append(relative.as_posix())
                    continue
                size, digest = _digest(candidate)
            except OSError as exc:
                raise ProjectExportError(f"Unable to inspect project file: {relative}") from exc
            discovered.append(_ProjectFile(candidate, relative, size, digest))
    return _Discovery(
        files=sorted(discovered, key=lambda item: item.relative.as_posix()),
        excluded=sorted(set(excluded)),
    )


def _project_metadata(paths_root: Path) -> dict[str, object]:
    manifest_path = paths_root / "project.json"
    if not manifest_path.is_file():
        return {}
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def build_project_package(context: RuntimeContext) -> ProjectPackage:
    """Build a ZIP from the active context without mutating or creating it.

    Only files already present beneath ``context.paths.root`` are exported.
    The two generated package-control files exist only inside the ZIP.
    """

    project_id = validate_scope_id(context.published_project_id, name="project_id")
    if not isinstance(context.scope, RuntimeScope):
        raise ProjectExportError("Invalid runtime scope")
    discovery = _discover_files(context.paths.root)
    files = discovery.files
    archive_root = f"CompanionGuard-Project-{project_id}"
    source_type = "evaluator_workspace" if context.scope is RuntimeScope.WORKSPACE else "official_published"
    manifest_data = _project_metadata(context.paths.root)
    manifest: dict[str, object] = {
        "export_format_version": EXPORT_FORMAT_VERSION,
        "project_id": project_id,
        "export_scope": context.scope.value,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "ephemeral_workspace": context.scope is RuntimeScope.WORKSPACE,
        "source_type": source_type,
        "file_count": len(files),
        "total_uncompressed_bytes": sum(item.size for item in files),
        "integrity_algorithm": "SHA-256",
    }
    for key in ("schema_version", "data_schema_version"):
        if key in manifest_data and isinstance(manifest_data[key], (str, int, float, bool)):
            manifest[key] = manifest_data[key]
    manifest["source_project_id"] = project_id
    if discovery.excluded:
        manifest["excluded_files"] = discovery.excluded

    checksums = "".join(
        f"{item.digest}  {archive_root}/{item.relative.as_posix()}\n"
        for item in files
    )
    output = io.BytesIO()
    try:
        with zipfile.ZipFile(
            output,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            strict_timestamps=False,
        ) as archive:
            for item in files:
                archive.write(item.source, f"{archive_root}/{item.relative.as_posix()}")
            archive.writestr(
                f"{archive_root}/{MANIFEST_NAME}",
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
            archive.writestr(f"{archive_root}/{CHECKSUMS_NAME}", checksums)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ProjectExportError("Unable to build project package") from exc

    suffix = "workspace" if context.scope is RuntimeScope.WORKSPACE else "published"
    return ProjectPackage(
        data=output.getvalue(),
        filename=f"CompanionGuard-{project_id}-{suffix}.zip",
        manifest=manifest,
    )
