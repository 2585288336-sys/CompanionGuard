from __future__ import annotations

import hashlib
import json

import pytest

import companionguard_app.runtime_workspace as runtime_workspace
from companionguard_app.runtime_scope import PublishedWriteError, RuntimeScope
from companionguard_app.runtime_workspace import (
    WorkspaceCreationError,
    ensure_workspace,
    get_runtime_context,
    get_workspace_mapping,
)
from companionguard_app.storage import append_judge_result, load_judge_results


def _fixture_project(data_root, project_id: str, *, value: str = "A"):
    root = data_root / "projects" / project_id
    (root / "evidence" / "dialogue").mkdir(parents=True)
    (root / "project.json").write_text(
        json.dumps({"project_id": project_id, "project_name": f"Project {project_id}"}),
        encoding="utf-8",
    )
    (root / "raw_cases.jsonl").write_text(json.dumps({"case_id": "case-1", "value": value}) + "\n", encoding="utf-8")
    (root / "evidence" / "dialogue" / "screen.txt").write_text("official evidence", encoding="utf-8")
    return root


def _tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_published_read_does_not_create_runtime_workspace(tmp_path):
    _fixture_project(tmp_path, "published")
    state = {}
    context = get_runtime_context("published", state=state, data_root=tmp_path)
    assert context.scope is RuntimeScope.PUBLISHED
    assert context.paths.root == tmp_path / "projects" / "published"
    assert not (tmp_path / "runtime_sessions").exists()
    assert get_workspace_mapping(state) == {}


def test_first_write_creates_atomic_isolated_workspace_and_preserves_source(tmp_path):
    source = _fixture_project(tmp_path, "published")
    source_digest = _tree_digest(source)
    state = {}
    context = ensure_workspace("published", state=state, data_root=tmp_path)

    assert context.scope is RuntimeScope.WORKSPACE
    assert context.paths.root == tmp_path / "runtime_sessions" / context.session_id / "projects" / context.sandbox_id
    assert context.paths.root.is_dir()
    assert (context.paths.root / ".workspace_manifest.json").is_file()
    assert json.loads((context.paths.root / ".workspace_manifest.json").read_text(encoding="utf-8"))["source_scope"] == "PUBLISHED"
    assert _tree_digest(source) == source_digest

    (context.paths.raw_cases).write_text(json.dumps({"case_id": "case-1", "value": "B"}) + "\n", encoding="utf-8")
    assert json.loads((source / "raw_cases.jsonl").read_text(encoding="utf-8"))["value"] == "A"


def test_same_session_reuses_workspace_and_different_sessions_are_isolated(tmp_path):
    _fixture_project(tmp_path, "published")
    first_state = {}
    first = ensure_workspace("published", state=first_state, data_root=tmp_path)
    reused = ensure_workspace("published", state=first_state, data_root=tmp_path)
    second = ensure_workspace("published", state={}, data_root=tmp_path)

    assert reused.paths.root == first.paths.root
    assert reused.sandbox_id == first.sandbox_id
    assert second.session_id != first.session_id
    assert second.sandbox_id != first.sandbox_id
    assert second.paths.root != first.paths.root


def test_one_session_can_have_distinct_sandboxes_for_distinct_published_projects(tmp_path):
    _fixture_project(tmp_path, "project-a")
    _fixture_project(tmp_path, "project-b")
    state = {}
    first = ensure_workspace("project-a", state=state, data_root=tmp_path)
    second = ensure_workspace("project-b", state=state, data_root=tmp_path)
    assert first.sandbox_id != second.sandbox_id
    assert first.paths.root != second.paths.root
    assert set(get_workspace_mapping(state)) == {"project-a", "project-b"}


@pytest.mark.parametrize("project_id", ["", ".", "..", "../escape", "a/b", "/tmp/project"])
def test_workspace_ids_and_project_ids_are_rejected(tmp_path, project_id):
    with pytest.raises(ValueError):
        ensure_workspace(project_id, state={}, data_root=tmp_path)


def test_failed_copy_leaves_no_registered_or_valid_workspace(tmp_path, monkeypatch):
    _fixture_project(tmp_path, "published")
    state = {}

    def fail_copy(*args, **kwargs):
        raise WorkspaceCreationError("fixture copy failure")

    monkeypatch.setattr(runtime_workspace, "_verify_copy", fail_copy)
    with pytest.raises(WorkspaceCreationError):
        ensure_workspace("published", state=state, data_root=tmp_path)
    assert get_workspace_mapping(state) == {}
    assert not (tmp_path / "runtime_sessions").exists()


def test_read_after_write_is_session_local_and_published_guard_remains(tmp_path):
    source = _fixture_project(tmp_path, "published")
    first_state = {}
    published = get_runtime_context("published", state=first_state, data_root=tmp_path)
    assert published.scope is RuntimeScope.PUBLISHED
    workspace = ensure_workspace("published", state=first_state, data_root=tmp_path)
    append_judge_result(
        {"case_id": "workspace-case", "status": "ok"},
        workspace.paths.judge_results,
        scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace.paths.root,
        data_root=tmp_path,
    )
    assert load_judge_results(workspace.paths.judge_results)[0]["case_id"] == "workspace-case"
    assert load_judge_results(source / "judge_results.jsonl") == []

    same_session = get_runtime_context("published", state=first_state, data_root=tmp_path)
    other_session = get_runtime_context("published", state={}, data_root=tmp_path)
    assert same_session.scope is RuntimeScope.WORKSPACE
    assert load_judge_results(same_session.paths.judge_results)[0]["case_id"] == "workspace-case"
    assert other_session.scope is RuntimeScope.PUBLISHED
    with pytest.raises(PublishedWriteError):
        append_judge_result({"case_id": "must-not-write"}, other_session.paths.judge_results, scope=RuntimeScope.PUBLISHED)
    assert load_judge_results(source / "judge_results.jsonl") == []
