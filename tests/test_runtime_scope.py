from pathlib import Path

import pytest

import companionguard_app.projects as projects
from companionguard_app.runtime_scope import RuntimeScope, resolve_project_root


def test_published_path_resolution(tmp_path):
    assert resolve_project_root(
        "published-project", scope=RuntimeScope.PUBLISHED, data_root=tmp_path
    ) == tmp_path / "projects" / "published-project"


def test_workspace_path_resolution(tmp_path):
    assert resolve_project_root(
        "sandbox-project",
        scope=RuntimeScope.WORKSPACE,
        session_id="session-1",
        sandbox_id="sandbox-1",
        data_root=tmp_path,
    ) == tmp_path / "runtime_sessions" / "session-1" / "projects" / "sandbox-1"


def test_published_and_workspace_paths_are_separate(tmp_path):
    published = resolve_project_root("project", scope="PUBLISHED", data_root=tmp_path)
    workspace = resolve_project_root(
        "project",
        scope="WORKSPACE",
        session_id="session",
        sandbox_id="sandbox",
        data_root=tmp_path,
    )
    assert published != workspace
    assert published == tmp_path / "projects" / "project"
    assert workspace.is_relative_to(tmp_path / "runtime_sessions")


@pytest.mark.parametrize(
    ("session_id", "sandbox_id", "message"),
    [
        (None, "sandbox", "session_id"),
        ("session", None, "sandbox_id"),
    ],
)
def test_workspace_requires_both_scope_ids(tmp_path, session_id, sandbox_id, message):
    with pytest.raises(ValueError, match=message):
        resolve_project_root(
            "project",
            scope=RuntimeScope.WORKSPACE,
            session_id=session_id,
            sandbox_id=sandbox_id,
            data_root=tmp_path,
        )


@pytest.mark.parametrize("value", ["", " ", ".", "..", "../escape", "a..b", "a/b", "a\\b", "/tmp/project"])
def test_scope_ids_reject_unsafe_path_values(tmp_path, value):
    with pytest.raises(ValueError):
        resolve_project_root(value, scope=RuntimeScope.PUBLISHED, data_root=tmp_path)


def test_workspace_scope_ids_are_validated(tmp_path):
    for field, kwargs in [("session_id", {"session_id": "../escape"}), ("sandbox_id", {"sandbox_id": "a/b"})]:
        with pytest.raises(ValueError, match=field):
            resolve_project_root(
                "project",
                scope=RuntimeScope.WORKSPACE,
                session_id=kwargs.get("session_id", "session"),
                sandbox_id=kwargs.get("sandbox_id", "sandbox"),
                data_root=tmp_path,
            )


def test_resolution_does_not_create_directories_or_files(tmp_path):
    root = resolve_project_root(
        "project",
        scope=RuntimeScope.WORKSPACE,
        session_id="session",
        sandbox_id="sandbox",
        data_root=tmp_path,
    )
    assert root == tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox"
    assert not (tmp_path / "runtime_sessions").exists()
    assert not root.exists()
    assert not list(tmp_path.rglob("*"))


def test_legacy_project_paths_remain_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    legacy = projects.project_paths("project-id")
    scoped = projects.scoped_project_paths(
        "project-id", scope=RuntimeScope.PUBLISHED, data_root=tmp_path
    )
    assert legacy.root == tmp_path / "projects" / "project-id"
    assert scoped.root == legacy.root
    assert legacy.raw_cases == scoped.raw_cases


def test_scoped_project_paths_workspace_is_explicit_and_nonexistent(tmp_path):
    paths = projects.scoped_project_paths(
        "project-id",
        scope=RuntimeScope.WORKSPACE,
        session_id="session-id",
        sandbox_id="sandbox-id",
        data_root=tmp_path,
    )
    assert paths.root == tmp_path / "runtime_sessions" / "session-id" / "projects" / "sandbox-id"
    assert not paths.root.exists()
    assert not Path(paths.manifest).exists()
