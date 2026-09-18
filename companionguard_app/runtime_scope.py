"""Runtime data scopes, safe project-root resolution, and write permissions.

Path resolution remains side-effect free.  Write APIs use the guard in this
module so that Published data is fail-closed until a future Workspace scope is
explicitly selected.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from .config import DATA_DIR


class RuntimeScope(str, Enum):
    """The two project-data scopes understood by the runtime."""

    PUBLISHED = "PUBLISHED"
    WORKSPACE = "WORKSPACE"


# Short alias for callers that prefer the simpler name.
Scope = RuntimeScope


class PublishedWriteError(PermissionError):
    """Raised when a published project or an unscoped write is mutated."""


def assert_writable_scope(scope: RuntimeScope | str | None) -> None:
    """Allow only an explicit WORKSPACE scope to perform a write.

    Missing scope is intentionally fail-closed.  Legacy read APIs may continue
    without scope, but a write API must never infer that an old project path is
    writable or silently default to WORKSPACE.
    """

    if scope is None:
        raise PublishedWriteError(
            "Published benchmark is read-only. An explicit writable scope is required."
        )
    try:
        selected_scope = RuntimeScope(scope)
    except ValueError as exc:
        raise ValueError(f"Unsupported runtime scope: {scope!r}") from exc
    if selected_scope is RuntimeScope.PUBLISHED:
        raise PublishedWriteError("Published benchmark is read-only.")
    if selected_scope is not RuntimeScope.WORKSPACE:
        raise ValueError(f"Unsupported writable scope: {scope!r}")


def validate_scope_id(value: str, *, name: str = "id") -> str:
    """Validate one path component used by a scoped project path.

    Scope IDs are intentionally stricter than the legacy ``safe_slug`` helper:
    they must already be safe path components.  No normalization is performed,
    so a caller cannot accidentally resolve one identifier while storing data
    under another.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{name} contains a null byte")
    if value in {".", ".."} or ".." in value:
        raise ValueError(f"{name} contains a path traversal component")
    if "/" in value or "\\" in value:
        raise ValueError(f"{name} must be a single path component")
    if Path(value).is_absolute():
        raise ValueError(f"{name} must not be an absolute path")
    return value


def resolve_project_root(
    project_id: str,
    *,
    scope: RuntimeScope | str = RuntimeScope.PUBLISHED,
    session_id: str | None = None,
    sandbox_id: str | None = None,
    data_root: Path | None = None,
) -> Path:
    """Resolve a project root without touching the filesystem.

    Published projects remain under ``data/projects``.  Workspace projects are
    explicitly separated under ``data/runtime_sessions/<session>/projects``.
    The optional ``data_root`` exists for isolated tests and does not change the
    production default.
    """

    try:
        selected_scope = RuntimeScope(scope)
    except ValueError as exc:
        raise ValueError(f"Unsupported runtime scope: {scope!r}") from exc

    root = Path(data_root) if data_root is not None else DATA_DIR
    validated_project_id = validate_scope_id(project_id, name="project_id")

    if selected_scope is RuntimeScope.PUBLISHED:
        if session_id is not None or sandbox_id is not None:
            raise ValueError("PUBLISHED scope does not accept session_id or sandbox_id")
        return root / "projects" / validated_project_id

    if session_id is None:
        raise ValueError("WORKSPACE scope requires session_id")
    if sandbox_id is None:
        raise ValueError("WORKSPACE scope requires sandbox_id")
    validated_session_id = validate_scope_id(session_id, name="session_id")
    validated_sandbox_id = validate_scope_id(sandbox_id, name="sandbox_id")
    return root / "runtime_sessions" / validated_session_id / "projects" / validated_sandbox_id
