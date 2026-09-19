from __future__ import annotations

import json

import pytest

import companionguard_app.projects as projects
import companionguard_app.service as service
from companionguard_app.audits import save_audit_evidence, upsert_jsonl
from companionguard_app.projects import delete_project
from companionguard_app.report_pipeline import write_report_artifacts
from companionguard_app.runtime_scope import PublishedWriteError, RuntimeScope, assert_writable_scope
from companionguard_app.service import run_report_writer
from companionguard_app.storage import (
    append_judge_result,
    build_final_results,
    load_adjudications,
    load_final_results,
    load_judge_results,
    save_adjudication,
)


def test_scope_guard_is_explicit_and_fail_closed() -> None:
    assert_writable_scope(RuntimeScope.WORKSPACE) is None
    with pytest.raises(PublishedWriteError, match="read-only"):
        assert_writable_scope(RuntimeScope.PUBLISHED)
    with pytest.raises(PublishedWriteError, match="explicit writable scope"):
        assert_writable_scope(None)


def test_judge_write_is_rejected_before_file_mutation(tmp_path) -> None:
    workspace_root = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox"
    workspace_root.mkdir(parents=True)
    path = workspace_root / "judge_results.jsonl"
    with pytest.raises(PublishedWriteError):
        append_judge_result({"case_id": "case-1"}, path, scope=RuntimeScope.PUBLISHED)
    assert not path.exists()

    append_judge_result({"case_id": "case-1"}, path, scope=RuntimeScope.WORKSPACE, workspace_root=workspace_root, data_root=tmp_path)
    before = path.read_text(encoding="utf-8")
    with pytest.raises(PublishedWriteError):
        append_judge_result({"case_id": "case-2"}, path, scope=RuntimeScope.PUBLISHED)
    assert path.read_text(encoding="utf-8") == before


def test_human_review_and_final_results_are_rejected_without_side_effects(tmp_path) -> None:
    adjudication = tmp_path / "human_adjudication.csv"
    final_results = tmp_path / "final_results.csv"
    with pytest.raises(PublishedWriteError):
        save_adjudication(
            case_id="case-1",
            auto_label="FINDING",
            human_label="FINDING",
            path=adjudication,
            scope=RuntimeScope.PUBLISHED,
        )
    with pytest.raises(PublishedWriteError):
        build_final_results(
            {},
            judge_path=tmp_path / "judge.jsonl",
            adjudication_path=adjudication,
            output_path=final_results,
            scope=RuntimeScope.PUBLISHED,
        )
    assert not adjudication.exists()
    assert not final_results.exists()


def test_layer2_layer3_and_report_writes_are_rejected_before_directories(tmp_path) -> None:
    layer2 = tmp_path / "layer2.jsonl"
    layer3 = tmp_path / "layer3.jsonl"
    with pytest.raises(PublishedWriteError):
        upsert_jsonl(layer2, {"product": "P", "check_code": "L2-01"}, key_fields=("product", "check_code"), scope=RuntimeScope.PUBLISHED)
    with pytest.raises(PublishedWriteError):
        upsert_jsonl(layer3, {"product": "P", "check_code": "L3-01"}, key_fields=("product", "check_code"), scope=RuntimeScope.PUBLISHED)
    with pytest.raises(PublishedWriteError):
        save_audit_evidence(
            evidence_root=tmp_path / "evidence",
            product="P",
            check_code="L2-01",
            files=[("screen.png", b"bytes")],
            scope=RuntimeScope.PUBLISHED,
        )
    with pytest.raises(PublishedWriteError):
        write_report_artifacts(
            report_type="dialogue",
            project={"project_id": "published"},
            final_rows=[],
            layer2_path=layer2,
            layer3_path=layer3,
            reports_dir=tmp_path / "reports",
            draft_text="draft",
            scope=RuntimeScope.PUBLISHED,
        )
    assert not layer2.exists()
    assert not layer3.exists()
    assert not (tmp_path / "evidence").exists()
    assert not (tmp_path / "reports").exists()


def test_project_create_and_delete_are_guarded_before_mutation(tmp_path, monkeypatch) -> None:
    projects_root = tmp_path / "projects"
    monkeypatch.setattr(projects, "PROJECTS_DIR", projects_root)
    with pytest.raises(PublishedWriteError):
        projects.create_project(
            name="Published",
            project_id="published",
            products=[{"id": "P", "label": "P"}],
            scope=RuntimeScope.PUBLISHED,
        )
    assert not projects_root.exists()

    published_root = projects_root / "published"
    published_root.mkdir(parents=True)
    (published_root / "project.json").write_text(json.dumps({"project_id": "published"}), encoding="utf-8")
    with pytest.raises(PublishedWriteError):
        delete_project("published", scope=RuntimeScope.PUBLISHED)
    assert published_root.exists()
    assert (published_root / "project.json").exists()


def test_published_reads_remain_available(tmp_path) -> None:
    workspace_root = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox"
    workspace_root.mkdir(parents=True)
    judge = workspace_root / "judge.jsonl"
    adjudication = workspace_root / "human_adjudication.csv"
    final = workspace_root / "final_results.csv"
    judge.write_text(json.dumps({"case_id": "case-1", "status": "ok"}) + "\n", encoding="utf-8")
    save_adjudication(
        case_id="case-1",
        auto_label="NO_FINDING",
        human_label="NO_FINDING",
        path=adjudication,
        scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace_root,
        data_root=tmp_path,
    )
    build_final_results(
        {},
        judge_path=judge,
        adjudication_path=adjudication,
        output_path=final,
        scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace_root,
        data_root=tmp_path,
    )
    assert load_judge_results(judge)[0]["case_id"] == "case-1"
    assert load_adjudications(adjudication)[0]["case_id"] == "case-1"
    assert load_final_results(final)[0]["case_id"] == "case-1"


def test_llm_is_not_called_before_published_guard(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM client must not be constructed for a rejected Published write")

    monkeypatch.setattr(service, "make_client", fail_if_called)
    profile = object()
    with pytest.raises(PublishedWriteError):
        run_report_writer(
            role="dialogue_report",
            report_context={},
            llm_profile=profile,
            scope=RuntimeScope.PUBLISHED,
        )
