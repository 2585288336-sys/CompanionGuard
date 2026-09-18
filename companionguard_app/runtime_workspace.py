"""Ephemeral evaluator workspaces for the Published benchmark.

This module owns session-local routing and lazy, copy-on-write workspace
creation.  It deliberately does not add persistence, authentication, cleanup,
or benchmark-schema fields.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, MutableMapping

import streamlit as st

from .config import DATA_DIR
from .projects import ProjectPaths, project_paths, scoped_project_paths
from .runtime_scope import RuntimeScope, validate_scope_id


SESSION_ID_KEY = "companionguard_session_id"
WORKSPACE_MAPPING_KEY = "companionguard_workspace_mapping"
WORKSPACE_MANIFEST = ".workspace_manifest.json"
WORKSPACE_VERSION = "1"


class WorkspaceCreationError(RuntimeError):
    """Raised when an isolated evaluator workspace cannot be created safely."""


@dataclass(frozen=True)
class RuntimeContext:
    published_project_id: str
    scope: RuntimeScope
    session_id: str
    sandbox_id: str | None
    paths: ProjectPaths

    @property
    def is_workspace(self) -> bool:
        return self.scope is RuntimeScope.WORKSPACE


def _state(state: MutableMapping[str, Any] | None = None) -> MutableMapping[str, Any]:
    return st.session_state if state is None else state


def get_session_id(state: MutableMapping[str, Any] | None = None) -> str:
    """Return a stable, non-PII identifier for the live Streamlit session."""

    store = _state(state)
    value = store.get(SESSION_ID_KEY)
    if isinstance(value, str):
        try:
            return validate_scope_id(value, name="session_id")
        except ValueError:
            pass
    value = uuid.uuid4().hex
    store[SESSION_ID_KEY] = value
    return value


def get_workspace_mapping(state: MutableMapping[str, Any] | None = None) -> dict[str, str]:
    """Return the session-local Published-project to sandbox mapping."""

    value = _state(state).get(WORKSPACE_MAPPING_KEY)
    if not isinstance(value, dict):
        return {}
    return {str(project_id): str(sandbox_id) for project_id, sandbox_id in value.items()}


def _set_workspace_mapping(
    published_project_id: str,
    sandbox_id: str,
    *,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    store = _state(state)
    mapping = get_workspace_mapping(store)
    mapping[published_project_id] = sandbox_id
    store[WORKSPACE_MAPPING_KEY] = mapping


def _data_root(data_root: Path | None) -> Path:
    return Path(data_root) if data_root is not None else DATA_DIR


def _workspace_paths(
    published_project_id: str,
    session_id: str,
    sandbox_id: str,
    *,
    data_root: Path | None = None,
) -> ProjectPaths:
    return scoped_project_paths(
        published_project_id,
        scope=RuntimeScope.WORKSPACE,
        session_id=session_id,
        sandbox_id=sandbox_id,
        data_root=_data_root(data_root),
    )


def _published_paths(published_project_id: str, *, data_root: Path | None = None) -> ProjectPaths:
    if data_root is None:
        return project_paths(published_project_id)
    return scoped_project_paths(
        published_project_id,
        scope=RuntimeScope.PUBLISHED,
        data_root=_data_root(data_root),
    )


def _manifest_path(paths: ProjectPaths) -> Path:
    return paths.root / WORKSPACE_MANIFEST


def _is_valid_workspace(paths: ProjectPaths) -> bool:
    return paths.root.is_dir() and paths.manifest.is_file() and _manifest_path(paths).is_file()


def _load_project(paths: ProjectPaths) -> dict[str, Any] | None:
    try:
        value = json.loads(paths.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def get_workspace_for_project(
    published_project_id: str,
    *,
    state: MutableMapping[str, Any] | None = None,
    data_root: Path | None = None,
) -> RuntimeContext | None:
    """Return an existing workspace without creating anything."""

    published_project_id = validate_scope_id(published_project_id, name="project_id")
    mapping = get_workspace_mapping(state)
    sandbox_id = mapping.get(published_project_id)
    if not sandbox_id:
        return None
    session_id = get_session_id(state)
    paths = _workspace_paths(
        published_project_id,
        session_id,
        validate_scope_id(sandbox_id, name="sandbox_id"),
        data_root=data_root,
    )
    if not _is_valid_workspace(paths):
        return None
    return RuntimeContext(
        published_project_id=published_project_id,
        scope=RuntimeScope.WORKSPACE,
        session_id=session_id,
        sandbox_id=sandbox_id,
        paths=paths,
    )


def get_runtime_context(
    published_project_id: str,
    *,
    state: MutableMapping[str, Any] | None = None,
    data_root: Path | None = None,
) -> RuntimeContext:
    """Resolve the current read context without creating a workspace."""

    published_project_id = validate_scope_id(published_project_id, name="project_id")
    existing = get_workspace_for_project(published_project_id, state=state, data_root=data_root)
    if existing is not None:
        return existing
    return RuntimeContext(
        published_project_id=published_project_id,
        scope=RuntimeScope.PUBLISHED,
        session_id=get_session_id(state),
        sandbox_id=None,
        paths=_published_paths(published_project_id, data_root=data_root),
    )


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_copy(source: Path, destination: Path) -> None:
    source_files = sorted(path.relative_to(source) for path in source.rglob("*") if path.is_file())
    destination_files = sorted(path.relative_to(destination) for path in destination.rglob("*") if path.is_file())
    if source_files != destination_files:
        raise WorkspaceCreationError("Workspace copy verification failed: file inventory differs.")
    for relative in source_files:
        source_file = source / relative
        destination_file = destination / relative
        if source_file.stat().st_size != destination_file.stat().st_size or _digest(source_file) != _digest(destination_file):
            raise WorkspaceCreationError(f"Workspace copy verification failed: {relative}")


def _remove_empty_runtime_parents(parent: Path, data_root: Path) -> None:
    runtime_root = data_root / "runtime_sessions"
    current = parent
    while current != runtime_root.parent and current.is_relative_to(runtime_root):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def ensure_workspace(
    published_project_id: str,
    *,
    state: MutableMapping[str, Any] | None = None,
    data_root: Path | None = None,
) -> RuntimeContext:
    """Atomically create or reuse this session's isolated workspace."""

    published_project_id = validate_scope_id(published_project_id, name="project_id")
    root = _data_root(data_root)
    store = _state(state)
    session_id = get_session_id(store)
    mapping = get_workspace_mapping(store)
    sandbox_id = mapping.get(published_project_id)
    if sandbox_id is None:
        sandbox_id = uuid.uuid4().hex
    sandbox_id = validate_scope_id(sandbox_id, name="sandbox_id")
    paths = _workspace_paths(published_project_id, session_id, sandbox_id, data_root=root)
    if _is_valid_workspace(paths):
        return RuntimeContext(published_project_id, RuntimeScope.WORKSPACE, session_id, sandbox_id, paths)
    if paths.root.exists():
        raise WorkspaceCreationError("A non-validated workspace already exists; refusing to overwrite it.")

    source = _published_paths(published_project_id, data_root=root)
    if not source.root.is_dir():
        raise WorkspaceCreationError(f"Published project does not exist: {published_project_id}")
    if any(path.is_symlink() for path in source.root.rglob("*")):
        raise WorkspaceCreationError("Published project contains symlinks; refusing to create a shared workspace copy.")

    parent = paths.root.parent
    temp_root = parent / f".{sandbox_id}.tmp-{uuid.uuid4().hex}"
    try:
        parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source.root, temp_root, symlinks=False)
        _verify_copy(source.root, temp_root)
        manifest = {
            "workspace_version": WORKSPACE_VERSION,
            "session_id": session_id,
            "sandbox_id": sandbox_id,
            "source_project_id": published_project_id,
            "source_scope": RuntimeScope.PUBLISHED.value,
            "source_path": f"data/projects/{published_project_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ephemeral": True,
        }
        _manifest_path(ProjectPaths(
            project_id=published_project_id,
            root=temp_root,
            manifest=temp_root / "project.json",
            raw_cases=temp_root / "raw_cases.jsonl",
            collection_sessions=temp_root / "collection_sessions.jsonl",
            collection_queues=temp_root / "collection_queues.jsonl",
            dialogue_evidence=temp_root / "evidence" / "dialogue",
            judge_results=temp_root / "judge_results.jsonl",
            adjudication=temp_root / "human_adjudication.csv",
            final_results=temp_root / "final_results.csv",
            adjudication_sampling=temp_root / "adjudication_sampling.json",
            layer2_records=temp_root / "layer2_product_safeguards.jsonl",
            layer2_evidence=temp_root / "evidence" / "layer2",
            layer3_records=temp_root / "layer3_public_evidence.jsonl",
            layer3_evidence=temp_root / "evidence" / "layer3",
            reports=temp_root / "reports",
            test_plans=temp_root / "test_plans.json",
        )).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_root.replace(paths.root)
    except Exception as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        _remove_empty_runtime_parents(parent, root)
        if isinstance(exc, WorkspaceCreationError):
            raise
        raise WorkspaceCreationError(f"Unable to create evaluator workspace: {exc}") from exc

    _set_workspace_mapping(published_project_id, sandbox_id, state=store)
    return RuntimeContext(published_project_id, RuntimeScope.WORKSPACE, session_id, sandbox_id, paths)


def ensure_active_workspace(
    published_project_id: str,
    *,
    state: MutableMapping[str, Any] | None = None,
    data_root: Path | None = None,
) -> RuntimeContext:
    """Create the workspace for the selected Published project on first write."""

    return ensure_workspace(published_project_id, state=state, data_root=data_root)

