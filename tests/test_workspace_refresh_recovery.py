from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

import companionguard_app.golden_ui as golden_ui
import companionguard_app.platform_ui as platform_ui
from companionguard_app.audits import make_audit_row, upsert_jsonl
from companionguard_app.project_export import build_project_package
from companionguard_app.projects import project_data_snapshot, scoped_project_paths
from companionguard_app.runtime_scope import RuntimeScope
from companionguard_app.runtime_workspace import (
    ACTIVE_PROJECT_ID_KEY,
    RECOVERY_FAILED_KEY,
    RESUME_QUERY_PARAM,
    SESSION_ID_KEY,
    WORKSPACE_MAPPING_KEY,
    clear_workspace_recovery,
    ensure_workspace,
    get_runtime_context,
    resume_workspace_from_query,
    workspace_recovery_failed,
)


PROJECT_ID = "refresh-fixture"


def _fixture_project(data_root: Path) -> Path:
    root = data_root / "projects" / PROJECT_ID
    (root / "evidence" / "dialogue").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "project.json").write_text(
        json.dumps(
            {
                "project_id": PROJECT_ID,
                "project_name": "Refresh Fixture",
                "mode": "BENCHMARK",
                "products": [{"id": "Product A", "label": "Product A", "role": "Primary anthropomorphic AI product"}],
            }
        ),
        encoding="utf-8",
    )
    (root / "raw_cases.jsonl").write_text('{"case_id":"case-1"}\n', encoding="utf-8")
    return root


def _write_layer3(context, product: str = "Product A", check_code: str = "L3-01") -> None:
    row = make_audit_row(
        project_id=PROJECT_ID,
        product=product,
        check_code=check_code,
        status="DOCUMENTED",
        evidence_summary="fixture evidence",
        notes="",
    )
    upsert_jsonl(
        context.paths.layer3_records,
        row,
        key_fields=("product", "check_code"),
        scope=RuntimeScope.WORKSPACE,
        workspace_root=context.paths.root,
        data_root=context.paths.root.parents[3],
    )


def test_refresh_resumes_same_physical_workspace_and_layer3_rows(tmp_path):
    _fixture_project(tmp_path)
    query = {}
    state_a = {}
    first = ensure_workspace(PROJECT_ID, state=state_a, data_root=tmp_path, query_params=query)
    original_root = first.paths.root
    token = query[RESUME_QUERY_PARAM]
    _write_layer3(first)

    state_b = {}
    recovered = resume_workspace_from_query(state=state_b, data_root=tmp_path, query_params=query)

    assert recovered is not None
    assert recovered.scope is RuntimeScope.WORKSPACE
    assert recovered.paths.root == original_root
    assert state_b[SESSION_ID_KEY] == first.session_id
    assert state_b[WORKSPACE_MAPPING_KEY] == {PROJECT_ID: first.sandbox_id}
    assert state_b[ACTIVE_PROJECT_ID_KEY] == PROJECT_ID
    assert query[RESUME_QUERY_PARAM] == token
    assert len([line for line in recovered.paths.layer3_records.read_text().splitlines() if line.strip()]) == 1


def test_multiple_refreshes_keep_one_workspace_and_row_count(tmp_path):
    _fixture_project(tmp_path)
    query = {}
    state = {}
    first = ensure_workspace(PROJECT_ID, state=state, data_root=tmp_path, query_params=query)
    _write_layer3(first)
    original_root = first.paths.root

    for _ in range(3):
        state = {}
        recovered = resume_workspace_from_query(state=state, data_root=tmp_path, query_params=query)
        assert recovered is not None
        assert recovered.paths.root == original_root
        assert project_data_snapshot(recovered.paths)["layer3_records"] == 1


def test_invalid_or_deleted_token_fails_closed_without_published_fallback(tmp_path):
    _fixture_project(tmp_path)
    invalid_state: dict[str, object] = {}
    invalid_query = {RESUME_QUERY_PARAM: "invalid-token"}

    assert resume_workspace_from_query(state=invalid_state, data_root=tmp_path, query_params=invalid_query) is None
    assert invalid_state[RECOVERY_FAILED_KEY] is True
    assert workspace_recovery_failed(invalid_state)
    assert not (tmp_path / "runtime_sessions").exists()

    source_state: dict[str, object] = {}
    query: dict[str, object] = {}
    workspace = ensure_workspace(PROJECT_ID, state=source_state, data_root=tmp_path, query_params=query)
    original_root = workspace.paths.root
    import shutil

    shutil.rmtree(original_root)
    deleted_state: dict[str, object] = {}
    assert resume_workspace_from_query(state=deleted_state, data_root=tmp_path, query_params=query) is None
    assert deleted_state[RECOVERY_FAILED_KEY] is True
    assert get_runtime_context(PROJECT_ID, state=deleted_state, data_root=tmp_path).scope is RuntimeScope.PUBLISHED
    assert not (tmp_path / "runtime_sessions" / workspace.session_id / "projects" / workspace.sandbox_id).exists()


def test_multiple_matching_manifests_fail_closed(tmp_path):
    _fixture_project(tmp_path)
    query: dict[str, object] = {}
    workspace = ensure_workspace(PROJECT_ID, state={}, data_root=tmp_path, query_params=query)
    duplicate_root = tmp_path / "runtime_sessions" / "duplicate-session" / "projects" / "duplicate-sandbox"
    duplicate_root.parent.mkdir(parents=True)
    import shutil

    shutil.copytree(workspace.paths.root, duplicate_root)
    duplicate_manifest = json.loads((duplicate_root / ".workspace_manifest.json").read_text(encoding="utf-8"))
    duplicate_manifest["session_id"] = "duplicate-session"
    duplicate_manifest["sandbox_id"] = "duplicate-sandbox"
    (duplicate_root / ".workspace_manifest.json").write_text(
        json.dumps(duplicate_manifest),
        encoding="utf-8",
    )

    failed_state: dict[str, object] = {}
    assert resume_workspace_from_query(state=failed_state, data_root=tmp_path, query_params=query) is None
    assert failed_state[RECOVERY_FAILED_KEY] is True
    assert WORKSPACE_MAPPING_KEY not in failed_state


def test_cross_workspace_tokens_restore_only_their_exact_workspace(tmp_path):
    _fixture_project(tmp_path)
    query_a: dict[str, object] = {}
    query_b: dict[str, object] = {}
    workspace_a = ensure_workspace(PROJECT_ID, state={}, data_root=tmp_path, query_params=query_a)
    workspace_b = ensure_workspace(PROJECT_ID, state={}, data_root=tmp_path, query_params=query_b)
    assert workspace_a.paths.root != workspace_b.paths.root
    assert query_a[RESUME_QUERY_PARAM] != query_b[RESUME_QUERY_PARAM]

    recovered_a = resume_workspace_from_query(state={}, data_root=tmp_path, query_params=query_a)
    recovered_b = resume_workspace_from_query(state={}, data_root=tmp_path, query_params=query_b)
    assert recovered_a is not None and recovered_a.paths.root == workspace_a.paths.root
    assert recovered_b is not None and recovered_b.paths.root == workspace_b.paths.root


def test_return_to_published_clears_failed_recovery_state_and_token():
    state = {RECOVERY_FAILED_KEY: True, WORKSPACE_MAPPING_KEY: {PROJECT_ID: "sandbox"}}
    query = {RESUME_QUERY_PARAM: "opaque-token-value"}

    clear_workspace_recovery(state=state, query_params=query)

    assert not workspace_recovery_failed(state)
    assert WORKSPACE_MAPPING_KEY not in state
    assert RESUME_QUERY_PARAM not in query


def test_raw_token_is_not_in_manifest_or_export(tmp_path):
    _fixture_project(tmp_path)
    query: dict[str, object] = {}
    context = ensure_workspace(PROJECT_ID, state={}, data_root=tmp_path, query_params=query)
    token = str(query[RESUME_QUERY_PARAM])
    manifest_text = (context.paths.root / ".workspace_manifest.json").read_text(encoding="utf-8")
    assert token not in manifest_text
    assert "resume_token_sha256" in manifest_text

    recovered = resume_workspace_from_query(state={}, data_root=tmp_path, query_params=query)
    assert recovered is not None
    package = build_project_package(recovered)
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        contents = b"".join(archive.read(name) for name in archive.namelist())
        assert token.encode() not in contents
        assert ".workspace_manifest.json" not in archive.namelist()


def test_navigation_preserves_workspace_query_parameter(monkeypatch):
    query = {RESUME_QUERY_PARAM: "opaque-token-value", "page": "layer3", "view": "compact"}
    state = {}

    class FakeStreamlit:
        query_params = query
        session_state = state

    monkeypatch.setattr(golden_ui, "st", FakeStreamlit())
    golden_ui._set_page("layer3")

    assert query == {RESUME_QUERY_PARAM: "opaque-token-value", "page": "layer3", "view": "compact"}


def test_failed_recovery_blocks_new_workspace_write(monkeypatch):
    monkeypatch.setattr(platform_ui, "workspace_recovery_failed", lambda: True)
    with pytest.raises(RuntimeError, match="无法恢复"):
        platform_ui.ensure_active_workspace_for_write()
