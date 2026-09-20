from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import companionguard_app.projects as projects_module
from companionguard_app.golden_ui import WORKFLOW_NEXT, WORKFLOW_PREVIOUS
from companionguard_app.projects import project_data_snapshot, scoped_project_paths
from companionguard_app.runtime_scope import RuntimeScope
from companionguard_app.runtime_workspace import ensure_workspace


PROJECT_ID = "CompanionGuard-Formal-Full-Benchmark-2026-09"


def _write_jsonl(path: Path, count: int, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps({"id": f"{prefix}-{index}"}) + "\n" for index in range(count)),
        encoding="utf-8",
    )


def _write_snapshot_fixture(data_root: Path) -> Path:
    paths = scoped_project_paths(PROJECT_ID, scope=RuntimeScope.PUBLISHED, data_root=data_root)
    paths.root.mkdir(parents=True)
    paths.manifest.write_text(json.dumps({"project_id": PROJECT_ID}), encoding="utf-8")
    _write_jsonl(paths.raw_cases, 3, "case")
    _write_jsonl(paths.judge_results, 2, "judge")
    with paths.adjudication.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "final_label"])
        writer.writerow(["case-0", "NO_FINDING"])
    with paths.final_results.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "final_label"])
        writer.writerow(["case-0", "NO_FINDING"])
    paths.test_plans.write_text(json.dumps([{"id": "plan-1"}, {"id": "plan-2"}]), encoding="utf-8")
    _write_jsonl(paths.layer2_records, 2, "layer2")
    _write_jsonl(paths.layer3_records, 3, "layer3")
    for index in range(4):
        evidence = paths.root / "evidence" / ("nested" if index % 2 else "dialogue") / f"evidence-{index}.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("evidence", encoding="utf-8")
    for index in range(3):
        report = paths.reports / ("nested" if index else "") / f"report-{index}.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("report", encoding="utf-8")
    return paths.root


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_overview_next_and_testdesign_previous_use_explicit_routes():
    assert WORKFLOW_NEXT["overview"] == "testdesign"
    assert WORKFLOW_PREVIOUS["testdesign"] == "overview"
    assert WORKFLOW_NEXT["overview"] != "judge"


def test_project_listing_deduplicates_by_project_id_without_deleting_sources(tmp_path, monkeypatch):
    projects_root = tmp_path / "projects"
    for directory, scope in (("published-copy", "PUBLISHED"), ("workspace-copy", "WORKSPACE")):
        root = projects_root / directory
        root.mkdir(parents=True)
        (root / "project.json").write_text(
            json.dumps({"project_id": "project-a", "project_name": "Project A", "scope": scope}),
            encoding="utf-8",
        )
    project_b = projects_root / "project-b"
    project_b.mkdir()
    (project_b / "project.json").write_text(
        json.dumps({"project_id": "project-b", "project_name": "Project B"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", projects_root)

    listed = projects_module.list_projects()

    assert {row["project_id"] for row in listed} == {"project-a", "project-b"}
    assert next(row for row in listed if row["project_id"] == "project-a")["scope"] == "PUBLISHED"
    assert (projects_root / "published-copy" / "project.json").is_file()
    assert (projects_root / "workspace-copy" / "project.json").is_file()


def test_project_data_snapshot_counts_active_project_without_writing(tmp_path):
    root = _write_snapshot_fixture(tmp_path)
    paths = scoped_project_paths(PROJECT_ID, scope=RuntimeScope.PUBLISHED, data_root=tmp_path)
    before = _tree_digest(root)

    assert project_data_snapshot(paths) == {
        "raw_cases": 3,
        "judge_results": 2,
        "human_review": 1,
        "final_results": 1,
        "test_plans": 2,
        "layer2_records": 2,
        "layer3_records": 3,
        "evidence": 4,
        "reports": 3,
    }
    assert _tree_digest(root) == before


def test_project_data_snapshot_counts_workspace_context_only(tmp_path):
    published_root = _write_snapshot_fixture(tmp_path)
    state = {}
    workspace = ensure_workspace(PROJECT_ID, state=state, data_root=tmp_path)
    _write_jsonl(workspace.paths.judge_results, 3, "workspace-judge")
    extra_report = workspace.paths.reports / "workspace-report.md"
    extra_report.write_text("workspace report", encoding="utf-8")

    counts = project_data_snapshot(workspace.paths)

    assert counts["judge_results"] == 3
    assert counts["reports"] == 4
    assert project_data_snapshot(scoped_project_paths(PROJECT_ID, data_root=tmp_path))["judge_results"] == 2
    assert (published_root / "judge_results.jsonl").read_text(encoding="utf-8").count("\n") == 2


def test_project_data_snapshot_missing_optional_artifacts_is_zero(tmp_path):
    paths = scoped_project_paths("empty-project", data_root=tmp_path)

    assert project_data_snapshot(paths) == {
        "raw_cases": 0,
        "judge_results": 0,
        "human_review": 0,
        "final_results": 0,
        "test_plans": 0,
        "layer2_records": 0,
        "layer3_records": 0,
        "evidence": 0,
        "reports": 0,
    }
