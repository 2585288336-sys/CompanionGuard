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


class _ExportClassification(str):
    ALLOW_PROJECT_ARTIFACT = "ALLOW_PROJECT_ARTIFACT"
    DENY_INFRASTRUCTURE = "DENY_INFRASTRUCTURE"
    UNKNOWN = "UNKNOWN"


_ALLOWED_ROOT_FILES = {
    "project.json",
    "raw_cases.jsonl",
    "collection_sessions.jsonl",
    "collection_queues.jsonl",
    "judge_results.jsonl",
    "human_adjudication.csv",
    "final_results.csv",
    "adjudication_sampling.json",
    "test_plans.json",
    "layer2_product_safeguards.jsonl",
    "layer3_public_evidence.jsonl",
    "llm_usage.jsonl",
}
_ALLOWED_ARTIFACT_DIRS = {"evidence", "reports"}
_INFRA_FILE_NAMES = {
    ".env",
    ".workspace_manifest.json",
    ".published_runtime_manifest.json",
    ".ds_store",
    "secrets.toml",
    "deployment_manifest.json",
    "export_manifest.json",
    "sha256sums.txt",
}
_INFRA_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".streamlit",
    "temporary",
    "tmp",
    "temp",
    "staging",
    "backup",
    "backups",
}
_SECRET_FILE_RE = re.compile(
    r"(?:credential|credentials|api[_-]?key|access[_-]?token|private[_-]?key|password)",
    re.IGNORECASE,
)
_TEXT_SUFFIXES = {".json", ".jsonl", ".csv", ".md", ".txt", ".yaml", ".yml"}
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----")
_BEARER_RE = re.compile(r"\bAuthorization\s*:\s*Bearer\s+([^\s,;]+)", re.IGNORECASE)
_ASSIGNMENT_RE = re.compile(
    r"\b(?:DEEPSEEK_API_KEY|OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|"
    r"API[_-]?KEY|ACCESS[_-]?TOKEN|SECRET(?:[_-]?KEY)?|PRIVATE[_-]?KEY|PASSWORD)"
    r"\s*[:=]\s*([^\s,;]+)",
    re.IGNORECASE,
)


def classify_export_path(relative: Path) -> str:
    """Classify a project-relative path without reading or touching it."""

    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        return _ExportClassification.UNKNOWN
    if any(part in _INFRA_DIR_NAMES for part in relative.parts):
        return _ExportClassification.DENY_INFRASTRUCTURE
    if relative.name.lower() in _INFRA_FILE_NAMES:
        return _ExportClassification.DENY_INFRASTRUCTURE
    if relative.name.lower().endswith(".env"):
        return _ExportClassification.DENY_INFRASTRUCTURE
    if relative.name.lower().endswith(".promotion.json"):
        return _ExportClassification.DENY_INFRASTRUCTURE
    if _SECRET_FILE_RE.search(relative.name):
        return _ExportClassification.DENY_INFRASTRUCTURE
    if relative.parts[0] in _ALLOWED_ARTIFACT_DIRS:
        return _ExportClassification.ALLOW_PROJECT_ARTIFACT
    if len(relative.parts) == 1 and relative.name in _ALLOWED_ROOT_FILES:
        return _ExportClassification.ALLOW_PROJECT_ARTIFACT
    return _ExportClassification.UNKNOWN


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    return normalized in {
        "your_api_key",
        "<api_key>",
        "***redacted***",
        "example",
        "dummy",
        "test-placeholder",
    } or "example" in normalized or "dummy" in normalized or "test-placeholder" in normalized


def _scan_text_credentials(relative: Path, path: Path) -> None:
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectExportError(f"Unable to inspect text artifact: {relative.as_posix()}") from exc
    if _PRIVATE_KEY_RE.search(text):
        raise ProjectExportError(
            f"Potential credential material detected in exportable project content: "
            f"{relative.as_posix()} (private_key_header)"
        )
    for match in _BEARER_RE.finditer(text):
        if not _is_placeholder(match.group(1)):
            raise ProjectExportError(
                f"Potential credential material detected in exportable project content: "
                f"{relative.as_posix()} (authorization_bearer)"
            )
    for match in _ASSIGNMENT_RE.finditer(text):
        if not _is_placeholder(match.group(1)):
            raise ProjectExportError(
                f"Potential credential material detected in exportable project content: "
                f"{relative.as_posix()} (credential_assignment)"
            )


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
            classification = classify_export_path(relative)
            if directory_path.is_symlink():
                raise ProjectExportError(f"Symlink is not allowed in export: {relative.as_posix()}")
            if classification == _ExportClassification.DENY_INFRASTRUCTURE:
                excluded.append(relative.as_posix())
            elif classification == _ExportClassification.UNKNOWN:
                raise ProjectExportError(f"Unclassified export artifact: {relative.as_posix()}")
            else:
                kept_directories.append(directory)
        directories[:] = kept_directories
        for filename in sorted(filenames):
            candidate = current_path / filename
            relative = _safe_relative(root, candidate)
            classification = classify_export_path(relative)
            if candidate.is_symlink():
                raise ProjectExportError(f"Symlink is not allowed in export: {relative.as_posix()}")
            if classification == _ExportClassification.DENY_INFRASTRUCTURE:
                excluded.append(relative.as_posix())
                continue
            if classification == _ExportClassification.UNKNOWN:
                raise ProjectExportError(f"Unclassified export artifact: {relative.as_posix()}")
            try:
                if not candidate.resolve().is_relative_to(resolved_root):
                    raise ProjectExportError(f"Project file escaped the active project root: {relative.as_posix()}")
                if not candidate.is_file():
                    raise ProjectExportError(f"Unsupported export artifact: {relative.as_posix()}")
                size, digest = _digest(candidate)
            except OSError as exc:
                raise ProjectExportError(f"Unable to inspect project file: {relative}") from exc
            _scan_text_credentials(relative, candidate)
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
    manifest["privacy_behavior"] = (
        "Project content is exported as-is; infrastructure files and detected credentials "
        "are excluded/blocked."
    )
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
