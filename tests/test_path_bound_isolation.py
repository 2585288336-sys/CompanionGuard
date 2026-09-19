from __future__ import annotations

import json
from pathlib import Path

import pytest

from companionguard_app.adjudication import save_sampling_plan
from companionguard_app.audits import save_audit_evidence, upsert_jsonl
from companionguard_app.collector_storage import (
    append_raw_case,
    resolve_evidence_path,
    save_evidence_files,
    upsert_collection_session,
)
from companionguard_app.projects import create_project, delete_project, update_project
from companionguard_app.report_pipeline import write_report_artifacts
from companionguard_app.runtime_scope import (
    RuntimeScope,
    WorkspacePathViolationError,
    assert_writable_target,
    resolve_project_root,
)
from companionguard_app.storage import append_judge_result, build_final_results, save_adjudication
from companionguard_app.testplans import upsert_test_plan
from companionguard_app.service import run_single_case
from companionguard_judge.pipeline import run_batch


def _roots(tmp_path: Path):
    data_root = tmp_path / "data"
    current = resolve_project_root(
        "published",
        scope=RuntimeScope.WORKSPACE,
        session_id="session-a",
        sandbox_id="sandbox-a",
        data_root=data_root,
    )
    other_session = resolve_project_root(
        "published",
        scope=RuntimeScope.WORKSPACE,
        session_id="session-b",
        sandbox_id="sandbox-b",
        data_root=data_root,
    )
    sibling = resolve_project_root(
        "published",
        scope=RuntimeScope.WORKSPACE,
        session_id="session-a",
        sandbox_id="sandbox-b",
        data_root=data_root,
    )
    published = resolve_project_root("published", scope=RuntimeScope.PUBLISHED, data_root=data_root)
    current.mkdir(parents=True)
    other_session.mkdir(parents=True)
    sibling.mkdir(parents=True)
    published.mkdir(parents=True)
    return data_root, current, other_session, sibling, published


def test_valid_nested_workspace_target_is_allowed(tmp_path: Path):
    data_root, current, *_ = _roots(tmp_path)
    target = current / "reports" / "report.json"
    resolved = assert_writable_target(
        RuntimeScope.WORKSPACE,
        target,
        workspace_root=current,
        data_root=data_root,
    )
    assert resolved == target


@pytest.mark.parametrize("target_name", ["judge_results.jsonl", "human_adjudication.csv", "final_results.csv", "reports/report.md", "evidence/screen.png"])
def test_workspace_scope_rejects_published_targets(tmp_path: Path, target_name: str):
    data_root, current, _, _, published = _roots(tmp_path)
    with pytest.raises(WorkspacePathViolationError):
        assert_writable_target(
            RuntimeScope.WORKSPACE,
            published / target_name,
            workspace_root=current,
            data_root=data_root,
        )


def test_workspace_scope_rejects_other_session_and_sibling_sandbox(tmp_path: Path):
    data_root, current, other_session, sibling, _ = _roots(tmp_path)
    for target in (other_session / "judge_results.jsonl", sibling / "judge_results.jsonl"):
        with pytest.raises(WorkspacePathViolationError):
            assert_writable_target(RuntimeScope.WORKSPACE, target, workspace_root=current, data_root=data_root)


def test_workspace_scope_rejects_traversal_and_symlink_escape(tmp_path: Path):
    data_root, current, _, _, _ = _roots(tmp_path)
    with pytest.raises(WorkspacePathViolationError):
        assert_writable_target(
            RuntimeScope.WORKSPACE,
            current / ".." / ".." / "projects" / "published" / "escape.jsonl",
            workspace_root=current,
            data_root=data_root,
        )

    outside = tmp_path / "outside"
    outside.mkdir()
    link = current / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspacePathViolationError):
        assert_writable_target(RuntimeScope.WORKSPACE, link / "escape.jsonl", workspace_root=current, data_root=data_root)


def test_project_local_write_apis_require_and_enforce_current_workspace(tmp_path: Path):
    data_root, current, other_session, _, published = _roots(tmp_path)
    published_judge = published / "judge_results.jsonl"
    with pytest.raises(WorkspacePathViolationError):
        append_judge_result({"case_id": "published"}, published_judge, scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        save_adjudication(case_id="c1", auto_label="FINDING", human_label="FINDING", path=published / "human_adjudication.csv", scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        build_final_results({}, judge_path=published_judge, adjudication_path=published / "human_adjudication.csv", output_path=published / "final_results.csv", scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        upsert_jsonl(published / "layer2_product_safeguards.jsonl", {"product": "P", "check_code": "L2-01"}, key_fields=("product", "check_code"), scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        save_audit_evidence(evidence_root=published / "evidence" / "layer2", product="P", check_code="L2-01", files=[("screen.png", b"x")], scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        write_report_artifacts(report_type="dialogue", project={"project_id": "published"}, final_rows=[], layer2_path=published / "layer2_product_safeguards.jsonl", layer3_path=published / "layer3_public_evidence.jsonl", reports_dir=published / "reports", draft_text="draft", scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        upsert_collection_session({"session_id": "s1"}, published / "collection_sessions.jsonl", scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        append_raw_case({"case_id": "c1", "collection_status": "COMPLETE"}, published / "raw_cases.jsonl", scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        save_evidence_files(case_id="c1", response_turn="turn-1", files=[("screen.png", b"x")], evidence_dir=published / "evidence" / "dialogue", scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        upsert_test_plan(published / "test_plans.json", {"plan_id": "p1"}, scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    with pytest.raises(WorkspacePathViolationError):
        save_sampling_plan({"project_id": "published"}, published / "adjudication_sampling.json", scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    assert not any(published.rglob("*.jsonl"))
    assert other_session.is_dir()


def test_valid_workspace_writes_and_project_update_stay_in_workspace(tmp_path: Path):
    data_root, current, _, _, published = _roots(tmp_path)
    judge = current / "judge_results.jsonl"
    append_judge_result({"case_id": "workspace", "status": "ok"}, judge, scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    assert json.loads(judge.read_text(encoding="utf-8"))["case_id"] == "workspace"

    project = {"project_id": "published", "project_name": "Workspace copy", "products": [{"id": "P"}]}
    updated = update_project(project, scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    assert updated["project_name"] == "Workspace copy"
    assert json.loads((current / "project.json").read_text(encoding="utf-8"))["project_name"] == "Workspace copy"
    assert not (published / "project.json").exists()


def test_project_crud_cannot_touch_published_and_workspace_delete_is_bound(tmp_path: Path):
    data_root, current, _, _, published = _roots(tmp_path)
    with pytest.raises(Exception):
        create_project(name="Published", project_id="published", products=[{"id": "P"}], scope=RuntimeScope.PUBLISHED)
    with pytest.raises(Exception):
        update_project({"project_id": "published"}, scope=RuntimeScope.PUBLISHED)
    with pytest.raises(Exception):
        delete_project("published", scope=RuntimeScope.PUBLISHED)
    assert published.is_dir()

    (current / "project.json").write_text(json.dumps({"project_id": "published"}), encoding="utf-8")
    delete_project("published", scope=RuntimeScope.WORKSPACE, workspace_root=current, data_root=data_root)
    assert not current.exists()
    assert published.exists()


def test_evidence_resolver_is_current_project_bound(tmp_path: Path):
    data_root, current, other_session, _, published = _roots(tmp_path)
    current_file = current / "evidence" / "current.png"
    current_file.parent.mkdir()
    current_file.write_bytes(b"current")
    other_file = other_session / "evidence" / "other.png"
    other_file.parent.mkdir()
    other_file.write_bytes(b"other")

    assert resolve_evidence_path("evidence/current.png", current, scope=RuntimeScope.WORKSPACE) == current_file.resolve()
    assert resolve_evidence_path(str(other_file), current, scope=RuntimeScope.WORKSPACE) is None
    assert resolve_evidence_path("../../session-b/projects/sandbox-b/evidence/other.png", current, scope=RuntimeScope.WORKSPACE) is None

    published_file = published / "evidence" / "official.png"
    published_file.parent.mkdir()
    published_file.write_bytes(b"official")
    assert resolve_evidence_path("evidence/official.png", published, scope=RuntimeScope.PUBLISHED) == published_file.resolve()


def test_judge_cli_batch_output_cannot_target_published(tmp_path: Path):
    data_root, current, _, _, published = _roots(tmp_path)
    with pytest.raises(WorkspacePathViolationError):
        run_batch(
            client=None,
            input_path=tmp_path / "cases.jsonl",
            criteria_dir=tmp_path / "criteria",
            output_path=published / "judge_results.jsonl",
            scope=RuntimeScope.WORKSPACE,
            workspace_root=current,
            data_root=data_root,
        )


def test_judge_service_rejects_bad_target_before_llm(tmp_path: Path):
    data_root, current, _, _, published = _roots(tmp_path)
    with pytest.raises(WorkspacePathViolationError):
        run_single_case(
            case={"case_id": "c1", "criterion_id": "C1"},
            criteria={},
            llm_profile=object(),
            judge_path=published / "judge_results.jsonl",
            scope=RuntimeScope.WORKSPACE,
            workspace_root=current,
            data_root=data_root,
        )
