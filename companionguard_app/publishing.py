"""Versioned AUTHORITATIVE -> PUBLISHED snapshot infrastructure.

This module is deliberately separate from evaluator workflows.  Its default
operation is validation and dry-run planning; publishing requires an explicit
``confirm_publish=True`` from an owner-controlled caller.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .runtime_scope import RuntimeScope, validate_scope_id


DEPLOYMENT_MANIFEST = "deployment_manifest.json"
RUNTIME_MANIFEST = ".published_runtime_manifest.json"
PROMOTION_MARKER_VERSION = "1"
PROMOTION_PHASES = frozenset({"PREPARED", "OLD_MOVED", "NEW_INSTALLED"})
MANIFEST_VERSION = "1.0"
CONTENT_HASH_ALGORITHM = "SHA-256"

REQUIRED_BENCHMARK_FILES = (
    "project.json",
    "raw_cases.jsonl",
    "collection_sessions.jsonl",
    "collection_queues.jsonl",
    "judge_results.jsonl",
    "human_adjudication.csv",
    "final_results.csv",
    "test_plans.json",
)

_SECRET_FILE_RE = re.compile(
    r"(?:credential|credentials|api[_-]?key|access[_-]?token|private[_-]?key|password)",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_INFRA_FILE_NAMES = {
    ".ds_store",
    ".env",
    ".workspace_manifest.json",
    "deployment_manifest.json",
    "export_manifest.json",
    "sha256sums.txt",
    RUNTIME_MANIFEST,
}
_INFRA_DIR_NAMES = {".git", "__pycache__"}


class PublishingError(ValueError):
    """Raised when a source, manifest, or publish operation is unsafe."""


class DuplicatePublishedVersionError(PublishingError):
    """Raised when a version would silently overwrite the same version."""


@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class SourceValidation:
    source_path: Path
    project_id: str
    project: dict[str, Any]
    files: dict[str, FileRecord]
    record_summary: dict[str, int]

    @property
    def total_bytes(self) -> int:
        return sum(record.bytes for record in self.files.values())

    @property
    def source_snapshot_hash(self) -> str:
        return _snapshot_hash(self.files)


@dataclass(frozen=True)
class PublishDiff:
    added: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]
    old_file_count: int
    new_file_count: int
    old_total_bytes: int
    new_total_bytes: int

    @property
    def added_count(self) -> int:
        return len(self.added)

    @property
    def modified_count(self) -> int:
        return len(self.modified)

    @property
    def removed_count(self) -> int:
        return len(self.removed)

    @property
    def unchanged_count(self) -> int:
        return len(self.unchanged)

    def as_dict(self) -> dict[str, Any]:
        return {
            "added": list(self.added),
            "modified": list(self.modified),
            "removed": list(self.removed),
            "unchanged": list(self.unchanged),
            "old_file_count": self.old_file_count,
            "new_file_count": self.new_file_count,
            "old_total_bytes": self.old_total_bytes,
            "new_total_bytes": self.new_total_bytes,
            "added_count": self.added_count,
            "modified_count": self.modified_count,
            "removed_count": self.removed_count,
            "unchanged_count": self.unchanged_count,
        }


@dataclass(frozen=True)
class PublishPlan:
    project_id: str
    published_version: str
    source_validation: SourceValidation
    manifest: dict[str, Any]
    diff: PublishDiff
    published: bool = False
    destination: Path | None = None


def validate_published_version(version: str) -> str:
    if not isinstance(version, str) or not version.strip():
        raise PublishingError("published_version must be explicitly provided")
    if not _VERSION_RE.fullmatch(version) or ".." in version:
        raise PublishingError("published_version contains unsafe path characters")
    return version


def _is_forbidden(relative: Path) -> bool:
    if any(part in _INFRA_DIR_NAMES for part in relative.parts):
        return True
    name = relative.name.lower()
    return (
        name in _INFRA_FILE_NAMES
        or name.endswith(".env")
        or name.endswith((".tmp", ".temp", ".lock"))
        or name.startswith("~$")
        or bool(_SECRET_FILE_RE.search(name))
    )


def _safe_relative(root: Path, path: Path) -> Path:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise PublishingError("Project file escaped its source root") from exc
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or "\\" in str(relative):
        raise PublishingError(f"Unsafe project-relative path: {relative}")
    return relative


def _file_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _inventory(root: Path, *, reject_forbidden: bool) -> dict[str, FileRecord]:
    if not root.is_dir() or root.is_symlink():
        raise PublishingError(f"Project root is not a safe directory: {root}")
    resolved_root = root.resolve()
    records: dict[str, FileRecord] = {}
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for directory in sorted(directories):
            candidate = current_path / directory
            relative = _safe_relative(root, candidate)
            if candidate.is_symlink():
                if reject_forbidden:
                    raise PublishingError(f"Symlink is not allowed: {relative}")
                continue
            if _is_forbidden(relative):
                if reject_forbidden:
                    raise PublishingError(f"Infrastructure file is not allowed: {relative}")
                continue
            kept_directories.append(directory)
        directories[:] = kept_directories
        for filename in sorted(filenames):
            candidate = current_path / filename
            relative = _safe_relative(root, candidate)
            if candidate.is_symlink():
                raise PublishingError(f"Symlink is not allowed: {relative}")
            if _is_forbidden(relative):
                if reject_forbidden:
                    raise PublishingError(f"Infrastructure or secret-like file is not allowed: {relative}")
                continue
            if not candidate.resolve().is_relative_to(resolved_root):
                raise PublishingError(f"File escaped its source root: {relative}")
            if not candidate.is_file():
                raise PublishingError(f"Unsupported project entry: {relative}")
            size, digest = _file_digest(candidate)
            records[relative.as_posix()] = FileRecord(relative.as_posix(), digest, size)
    return dict(sorted(records.items()))


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishingError(f"Invalid {label}: {path.name}") from exc


def _validate_jsonl(path: Path) -> int:
    count = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise PublishingError(f"JSONL record is not an object: {path.name}:{line_number}")
                count += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishingError(f"Invalid JSONL: {path.name}") from exc
    return count


def _validate_csv(path: Path) -> int:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle, strict=True))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise PublishingError(f"Invalid CSV: {path.name}") from exc
    return max(0, len(rows) - 1) if rows else 0


def _validate_test_plans(path: Path) -> int:
    value = _read_json(path, "test_plans.json")
    if not isinstance(value, list):
        raise PublishingError("test_plans.json must contain a list of plan records")
    if any(not isinstance(plan, dict) for plan in value):
        raise PublishingError("test_plans.json plan records must be objects")
    return len(value)


def _validate_source_location(source: Path) -> None:
    if any(part == "runtime_sessions" for part in source.resolve().parts):
        raise PublishingError("A runtime Workspace cannot be an AUTHORITATIVE source")
    if any(path.name == ".workspace_manifest.json" for path in source.rglob(".workspace_manifest.json")):
        raise PublishingError("A source containing .workspace_manifest.json is a Workspace")


def validate_authoritative_source(
    source_path: str | Path,
    *,
    expected_project_id: str,
    source_scope: RuntimeScope | str | None = None,
) -> SourceValidation:
    """Validate an explicit local AUTHORITATIVE project without changing it."""

    if source_scope is not None and RuntimeScope(source_scope) is RuntimeScope.WORKSPACE:
        raise PublishingError("WORKSPACE scope cannot be published")
    project_id = validate_scope_id(expected_project_id, name="project_id")
    source = Path(source_path)
    _validate_source_location(source)
    files = _inventory(source, reject_forbidden=True)
    missing = [relative for relative in REQUIRED_BENCHMARK_FILES if relative not in files]
    if missing:
        raise PublishingError(f"Authoritative source is missing required files: {', '.join(missing)}")

    project = _read_json(source / "project.json", "project.json")
    if not isinstance(project, dict):
        raise PublishingError("project.json must contain an object")
    if project.get("project_id") != project_id:
        raise PublishingError("project.json project_id does not match expected project_id")
    if not project.get("schema_version") or not project.get("data_schema_version"):
        raise PublishingError("project.json must identify schema_version and data_schema_version")

    record_summary = {
        "raw_cases": _validate_jsonl(source / "raw_cases.jsonl"),
        "judge_results": _validate_jsonl(source / "judge_results.jsonl"),
        "collection_sessions": _validate_jsonl(source / "collection_sessions.jsonl"),
        "collection_queues": _validate_jsonl(source / "collection_queues.jsonl"),
        "human_adjudication": _validate_csv(source / "human_adjudication.csv"),
        "final_results": _validate_csv(source / "final_results.csv"),
        "test_plans": _validate_test_plans(source / "test_plans.json"),
        "evidence": sum(1 for relative in files if relative.startswith("evidence/")),
        "reports": sum(1 for relative in files if relative.startswith("reports/")),
        "layer2": _validate_jsonl(source / "layer2_product_safeguards.jsonl") if "layer2_product_safeguards.jsonl" in files else 0,
        "layer3": _validate_jsonl(source / "layer3_public_evidence.jsonl") if "layer3_public_evidence.jsonl" in files else 0,
    }
    return SourceValidation(source, project_id, project, files, record_summary)


def _snapshot_hash(files: Mapping[str, FileRecord]) -> str:
    digest = hashlib.sha256()
    for relative, record in sorted(files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.sha256.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(record.bytes).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_deployment_manifest(
    validation: SourceValidation,
    *,
    published_version: str,
    published_at: str | None = None,
) -> dict[str, Any]:
    version = validate_published_version(published_version)
    timestamp = published_at or datetime.now(timezone.utc).isoformat()
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise PublishingError("published_at must be a non-empty string")
    return {
        "manifest_version": MANIFEST_VERSION,
        "project_id": validation.project_id,
        "published_version": version,
        "published_at": timestamp,
        "source_type": "AUTHORITATIVE",
        "source_snapshot_hash": validation.source_snapshot_hash,
        "content_hash_algorithm": CONTENT_HASH_ALGORITHM,
        "file_count": len(validation.files),
        "total_bytes": validation.total_bytes,
        "schema_version": validation.project["schema_version"],
        "data_schema_version": validation.project["data_schema_version"],
        "files": {
            relative: {"sha256": record.sha256, "bytes": record.bytes}
            for relative, record in validation.files.items()
        },
        "record_summary": dict(validation.record_summary),
    }


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    required = {"manifest_version", "project_id", "published_version", "source_type", "source_snapshot_hash", "files"}
    missing = required - set(manifest)
    if missing:
        raise PublishingError(f"Deployment manifest is missing fields: {', '.join(sorted(missing))}")
    if manifest["source_type"] != "AUTHORITATIVE":
        raise PublishingError("Deployment manifest source_type must be AUTHORITATIVE")
    project_id = validate_scope_id(str(manifest["project_id"]), name="project_id")
    validate_published_version(str(manifest["published_version"]))
    files = manifest["files"]
    if not isinstance(files, dict):
        raise PublishingError("Deployment manifest files must be an object")
    for relative, details in files.items():
        relative_path = Path(str(relative))
        if relative_path.is_absolute() or ".." in relative_path.parts or not relative_path.parts:
            raise PublishingError(f"Unsafe path in deployment manifest: {relative}")
        if not isinstance(details, dict) or not isinstance(details.get("sha256"), str) or not isinstance(details.get("bytes"), int):
            raise PublishingError(f"Invalid file record in deployment manifest: {relative}")
    copy = dict(manifest)
    copy["project_id"] = project_id
    return copy


def load_deployment_manifest(project_root: str | Path) -> dict[str, Any] | None:
    path = Path(project_root) / DEPLOYMENT_MANIFEST
    if not path.is_file():
        return None
    value = _read_json(path, DEPLOYMENT_MANIFEST)
    if not isinstance(value, dict):
        raise PublishingError("deployment_manifest.json must contain an object")
    return _validate_manifest(value)


def build_publish_diff(
    current_published_root: str | Path,
    authoritative: SourceValidation | str | Path,
    *,
    project_id: str | None = None,
) -> PublishDiff:
    if isinstance(authoritative, SourceValidation):
        new_files = authoritative.files
    else:
        source = Path(authoritative)
        inferred_project_id = project_id
        if inferred_project_id is None:
            project = _read_json(source / "project.json", "project.json")
            inferred_project_id = str(project.get("project_id")) if isinstance(project, dict) else ""
        new_files = validate_authoritative_source(source, expected_project_id=inferred_project_id).files
    old_root = Path(current_published_root)
    old_files = _inventory(old_root, reject_forbidden=False) if old_root.is_dir() else {}
    added = sorted(set(new_files) - set(old_files))
    removed = sorted(set(old_files) - set(new_files))
    modified = sorted(path for path in set(new_files) & set(old_files) if new_files[path].sha256 != old_files[path].sha256)
    unchanged = sorted(path for path in set(new_files) & set(old_files) if new_files[path].sha256 == old_files[path].sha256)
    return PublishDiff(
        tuple(added),
        tuple(modified),
        tuple(removed),
        tuple(unchanged),
        len(old_files),
        len(new_files),
        sum(record.bytes for record in old_files.values()),
        sum(record.bytes for record in new_files.values()),
    )


def _copy_file_stream(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, destination.open("wb") as destination_handle:
        shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)


def verify_manifest_content(root: str | Path, manifest: Mapping[str, Any]) -> None:
    validated = _validate_manifest(manifest)
    actual = _inventory(Path(root), reject_forbidden=False)
    expected = {
        str(relative): FileRecord(str(relative), str(details["sha256"]), int(details["bytes"]))
        for relative, details in validated["files"].items()
    }
    if set(actual) != set(expected):
        raise PublishingError("Published snapshot file inventory does not match its manifest")
    for relative, record in expected.items():
        actual_record = actual[relative]
        if actual_record.sha256 != record.sha256 or actual_record.bytes != record.bytes:
            raise PublishingError(f"Published snapshot hash mismatch: {relative}")
    if len(expected) != int(validated.get("file_count", len(expected))):
        raise PublishingError("Published snapshot file_count does not match its manifest")
    if _snapshot_hash(expected) != validated["source_snapshot_hash"]:
        raise PublishingError("Published snapshot source_snapshot_hash does not match its files")


def stage_snapshot(
    validation: SourceValidation,
    manifest: Mapping[str, Any],
    *,
    staging_root: str | Path,
) -> Path:
    staging_parent = Path(staging_root)
    staging_parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{validation.project_id}-", dir=staging_parent))
    try:
        for relative in validation.files:
            _copy_file_stream(validation.source_path / relative, temp_root / relative)
        (temp_root / DEPLOYMENT_MANIFEST).write_text(
            json.dumps(dict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verify_manifest_content(temp_root, manifest)
        return temp_root
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def promotion_marker_path(destination_root: str | Path) -> Path:
    """Return the sibling transaction marker for a controlled destination."""

    destination = Path(destination_root)
    if not destination.name or destination.name in {".", ".."} or "/" in destination.name or "\\" in destination.name:
        raise PublishingError("Destination name is not safe for promotion")
    return destination.parent / f".{destination.name}.promotion.json"


def _transaction_relative(parent: Path, path: Path, *, label: str) -> str:
    try:
        relative = path.relative_to(parent)
    except ValueError as exc:
        raise PublishingError(f"Promotion {label} escaped its destination parent") from exc
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or "\\" in str(relative):
        raise PublishingError(f"Promotion {label} is unsafe")
    return relative.as_posix()


def _transaction_path(parent: Path, value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PublishingError(f"Promotion {label} is missing")
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or "\\" in value:
        raise PublishingError(f"Promotion {label} is unsafe")
    candidate = parent / relative
    if candidate.relative_to(parent) != relative:
        raise PublishingError(f"Promotion {label} is unsafe")
    return candidate


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Persist a small transaction marker with durable replace semantics."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.tmp-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(dict(value), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _promotion_marker(
    destination: Path,
    staged: Path,
    backup: Path | None,
    *,
    destination_existed: bool,
    intended_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    marker: dict[str, Any] = {
        "transaction_format_version": PROMOTION_MARKER_VERSION,
        "destination_name": destination.name,
        "staged_name": _transaction_relative(destination.parent, staged, label="staged path"),
        "backup_name": None if backup is None else _transaction_relative(destination.parent, backup, label="backup path"),
        "destination_existed": destination_existed,
        "phase": "PREPARED",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if intended_manifest is not None:
        marker["intended_published_version"] = intended_manifest.get("published_version")
        marker["intended_source_snapshot_hash"] = intended_manifest.get("source_snapshot_hash")
    return marker


def _read_promotion_marker(destination: Path) -> tuple[Path, dict[str, Any]]:
    marker_path = promotion_marker_path(destination)
    if marker_path.is_symlink() or not marker_path.is_file():
        raise PublishingError("Promotion marker is not a regular file")
    value = _read_json(marker_path, "promotion marker")
    if not isinstance(value, dict):
        raise PublishingError("Promotion marker must contain an object")
    if value.get("transaction_format_version") != PROMOTION_MARKER_VERSION:
        raise PublishingError("Unsupported promotion marker format")
    if value.get("destination_name") != destination.name:
        raise PublishingError("Promotion marker destination does not match")
    if value.get("phase") not in PROMOTION_PHASES:
        raise PublishingError("Promotion marker phase is invalid")
    if not isinstance(value.get("destination_existed"), bool):
        raise PublishingError("Promotion marker destination_existed is invalid")
    _transaction_path(destination.parent, value.get("staged_name"), label="staged path")
    backup_name = value.get("backup_name")
    if backup_name is not None:
        _transaction_path(destination.parent, backup_name, label="backup path")
    return marker_path, value


def _remove_promotion_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _valid_intended_snapshot(path: Path, manifest: Mapping[str, Any] | None) -> bool:
    if manifest is None or not path.is_dir() or path.is_symlink():
        return False
    try:
        verify_manifest_content(path, manifest)
    except (OSError, PublishingError):
        return False
    return True


def _valid_backup_snapshot(path: Path, destination_name: str) -> bool:
    """Validate the identity of an old snapshot without assuming its version."""

    if not path.is_dir() or path.is_symlink():
        return False
    deployment_manifest = path / DEPLOYMENT_MANIFEST
    if deployment_manifest.is_file():
        try:
            old_manifest = load_deployment_manifest(path)
            return old_manifest is not None and verify_manifest_content(path, old_manifest) is None
        except (OSError, PublishingError):
            return False
    runtime_metadata = path / RUNTIME_MANIFEST
    project_file = path / "project.json"
    if not runtime_metadata.is_file() or not project_file.is_file():
        return False
    try:
        metadata = _read_json(runtime_metadata, RUNTIME_MANIFEST)
        project = _read_json(project_file, "project.json")
    except PublishingError:
        return False
    if not isinstance(metadata, dict) or not isinstance(project, dict):
        return False
    if metadata.get("project_id") != destination_name or project.get("project_id") != destination_name:
        return False
    if not isinstance(metadata.get("published_version"), str) or not isinstance(metadata.get("source_snapshot_hash"), str):
        return False
    try:
        _inventory(path, reject_forbidden=False)
    except (OSError, PublishingError):
        return False
    return True


def _finish_recovered_promotion(marker_path: Path, staged: Path, backup: Path | None) -> None:
    if staged.exists():
        _remove_promotion_path(staged)
    if backup is not None and backup.exists():
        _remove_promotion_path(backup)
    marker_path.unlink(missing_ok=True)


def recover_interrupted_promotion(
    destination_root: str | Path,
    *,
    intended_manifest: Mapping[str, Any] | None = None,
) -> bool:
    """Resolve one interrupted sibling transaction, or fail closed.

    The marker phase is only a hint.  The actual destination, staged copy, and
    backup are validated before any artifact is removed.
    """

    destination = Path(destination_root)
    marker_path = promotion_marker_path(destination)
    if not marker_path.exists():
        return False
    marker_path, marker = _read_promotion_marker(destination)
    staged = _transaction_path(destination.parent, marker["staged_name"], label="staged path")
    backup_name = marker.get("backup_name")
    backup = None if backup_name is None else _transaction_path(destination.parent, backup_name, label="backup path")
    destination_valid = _valid_intended_snapshot(destination, intended_manifest)
    backup_valid = backup is not None and backup.exists() and _valid_backup_snapshot(backup, destination.name)

    if destination.exists() and backup is not None and backup.exists():
        if destination_valid:
            _finish_recovered_promotion(marker_path, staged, backup)
            return True
        if backup_valid:
            _remove_promotion_path(destination)
            backup.replace(destination)
            _finish_recovered_promotion(marker_path, staged, None)
            return True
        raise PublishingError("Promotion transaction is ambiguous: destination and backup are not both healthy")

    if not destination.exists() and backup is not None and backup.exists():
        if not backup_valid:
            raise PublishingError("Promotion transaction is ambiguous: backup snapshot is not healthy")
        backup.replace(destination)
        _finish_recovered_promotion(marker_path, staged, None)
        return True

    if destination.exists():
        if destination_valid:
            _finish_recovered_promotion(marker_path, staged, None)
            return True
        raise PublishingError("Promotion transaction is ambiguous: destination is not healthy and backup is missing")

    if not marker["destination_existed"] and _valid_intended_snapshot(staged, intended_manifest):
        staged.replace(destination)
        if not _valid_intended_snapshot(destination, intended_manifest):
            raise PublishingError("Recovered staged snapshot failed validation")
        _finish_recovered_promotion(marker_path, staged, None)
        return True

    raise PublishingError("Promotion transaction is unresolved; preserving all artifacts")


def atomic_promote(
    staged_root: str | Path,
    destination_root: str | Path,
    *,
    intended_manifest: Mapping[str, Any] | None = None,
) -> None:
    """Promote a validated directory with a recoverable sibling transaction."""

    staged = Path(staged_root)
    destination = Path(destination_root)
    if not staged.is_dir():
        raise PublishingError("Staged snapshot does not exist")
    if staged.is_symlink() or destination.is_symlink():
        raise PublishingError("Promotion does not allow symlink roots")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _transaction_relative(destination.parent, staged, label="staged path")
    if staged == destination:
        raise PublishingError("Staged snapshot and destination must be different")
    recover_interrupted_promotion(destination, intended_manifest=intended_manifest)
    if intended_manifest is not None:
        verify_manifest_content(staged, intended_manifest)

    destination_existed = destination.exists()
    backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}" if destination_existed else None
    marker = _promotion_marker(
        destination,
        staged,
        backup,
        destination_existed=destination_existed,
        intended_manifest=intended_manifest,
    )
    marker_path = promotion_marker_path(destination)
    _atomic_write_json(marker_path, marker)
    if destination_existed:
        destination.replace(backup)
        marker["phase"] = "OLD_MOVED"
        _atomic_write_json(marker_path, marker)
    staged.replace(destination)
    marker["phase"] = "NEW_INSTALLED"
    _atomic_write_json(marker_path, marker)
    if intended_manifest is not None:
        verify_manifest_content(destination, intended_manifest)
    _finish_recovered_promotion(marker_path, staged, backup)


def publish_snapshot(
    source_path: str | Path,
    *,
    project_id: str,
    published_version: str,
    destination_root: str | Path,
    confirm_publish: bool = False,
    published_at: str | None = None,
) -> PublishPlan:
    """Validate and plan a snapshot; write only when ``confirm_publish`` is true."""

    validation = validate_authoritative_source(source_path, expected_project_id=project_id)
    manifest = build_deployment_manifest(validation, published_version=published_version, published_at=published_at)
    destination = Path(destination_root) / validation.project_id
    diff = build_publish_diff(destination, validation)
    existing_manifest = load_deployment_manifest(destination) if destination.is_dir() else None
    if existing_manifest and existing_manifest.get("published_version") == published_version:
        raise DuplicatePublishedVersionError(f"Published version already exists: {published_version}")
    if not confirm_publish:
        return PublishPlan(validation.project_id, published_version, validation, manifest, diff, False, destination)

    staging_parent = Path(destination_root) / ".staging"
    try:
        staged = stage_snapshot(validation, manifest, staging_root=staging_parent)
    except Exception:
        try:
            staging_parent.rmdir()
        except OSError:
            pass
        raise
    try:
        atomic_promote(staged, destination, intended_manifest=manifest)
    except Exception:
        raise
    try:
        staging_parent.rmdir()
    except OSError:
        pass
    return PublishPlan(validation.project_id, published_version, validation, manifest, diff, True, destination)
