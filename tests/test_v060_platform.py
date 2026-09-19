from __future__ import annotations

import json
from pathlib import Path

import companionguard_app.projects as projects
from companionguard_app.audits import load_jsonl, make_audit_row, upsert_jsonl
from companionguard_app.reliability import reliability_metrics
from companionguard_app.reporting import build_integrated_report
from companionguard_app.runtime_scope import RuntimeScope


def test_layer2_and_layer3_frozen_check_counts():
    root = Path(__file__).resolve().parents[1]
    layer2 = json.loads((root / "config" / "layer2_checks.json").read_text(encoding="utf-8"))
    layer3 = json.loads((root / "config" / "layer3_checks.json").read_text(encoding="utf-8"))
    assert len(layer2["checks"]) == 22
    assert layer2["statuses"] == ["OBSERVED", "NOT_OBSERVED", "NOT_TRIGGERED", "NOT_VERIFIABLE"]
    assert len(layer2["standard_path"]) == 9
    assert [c["code"] for c in layer3["checks"]] == [f"L3-0{i}" for i in range(1, 7)]
    assert layer3["statuses"] == ["DOCUMENTED", "PARTIALLY_DOCUMENTED", "NOT_FOUND", "NOT_PUBLICLY_VERIFIABLE"]


def test_project_scoped_paths_are_isolated(tmp_path, monkeypatch):
    workspace_a = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox-a"
    workspace_b = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox-b"
    p1 = projects.create_project(
        name="Batch A",
        project_id="batch-a",
        products=[{"id": "A", "label": "A", "slug": "A"}],
        scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace_a,
        data_root=tmp_path,
    )
    p2 = projects.create_project(
        name="Batch B",
        project_id="batch-b",
        products=[{"id": "B", "label": "B", "slug": "B"}],
        scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace_b,
        data_root=tmp_path,
    )
    paths1 = projects._project_paths_at_root(p1["project_id"], workspace_a)
    paths2 = projects._project_paths_at_root(p2["project_id"], workspace_b)
    assert paths1.root != paths2.root
    paths1.raw_cases.write_text('{"case_id":"a"}\n', encoding="utf-8")
    assert not paths2.raw_cases.exists()




def test_project_delete_removes_only_target_project(tmp_path, monkeypatch):
    root1 = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox-a"
    root2 = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox-b"
    p1 = projects.create_project(name="Delete Me", project_id="delete-me", products=[{"id":"A","label":"A","slug":"A"}], scope=RuntimeScope.WORKSPACE, workspace_root=root1, data_root=tmp_path)
    p2 = projects.create_project(name="Keep Me", project_id="keep-me", products=[{"id":"B","label":"B","slug":"B"}], scope=RuntimeScope.WORKSPACE, workspace_root=root2, data_root=tmp_path)
    (root1 / "raw_cases.jsonl").write_text("{}\n", encoding="utf-8")
    projects.delete_project(p1["project_id"], scope=RuntimeScope.WORKSPACE, workspace_root=root1, data_root=tmp_path)
    assert not root1.exists()
    assert root2.exists()

def test_audit_upsert_replaces_same_product_and_check(tmp_path):
    path = tmp_path / "layer2.jsonl"
    workspace_root = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox"
    workspace_root.mkdir(parents=True)
    first = make_audit_row(project_id="p", product="X", check_code="AID-01", status="NOT_OBSERVED", evidence_summary="none", notes="")
    second = make_audit_row(project_id="p", product="X", check_code="AID-01", status="OBSERVED", evidence_summary="found", notes="")
    path = workspace_root / "layer2.jsonl"
    upsert_jsonl(path, first, key_fields=("product", "check_code"), scope=RuntimeScope.WORKSPACE, workspace_root=workspace_root, data_root=tmp_path)
    upsert_jsonl(path, second, key_fields=("product", "check_code"), scope=RuntimeScope.WORKSPACE, workspace_root=workspace_root, data_root=tmp_path)
    rows = load_jsonl(path)
    assert len(rows) == 1
    assert rows[0]["status"] == "OBSERVED"


def test_reliability_metrics_three_class_kappa():
    rows = [
        {"auto_label": "FINDING", "human_label": "FINDING"},
        {"auto_label": "NO_FINDING", "human_label": "NO_FINDING"},
        {"auto_label": "REVIEW", "human_label": "REVIEW"},
        {"auto_label": "FINDING", "human_label": "NO_FINDING"},
    ]
    result = reliability_metrics(rows)
    assert result["n"] == 4
    assert result["exact_agreement"] == 0.75
    assert result["cohen_kappa"] is not None
    assert result["matrix"]["FINDING"]["NO_FINDING"] == 1


def test_integrated_report_keeps_layers_separate(tmp_path):
    workspace_root = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox"
    workspace_root.mkdir(parents=True)
    l2 = workspace_root / "l2.jsonl"
    l3 = workspace_root / "l3.jsonl"
    upsert_jsonl(l2, make_audit_row(project_id="p", product="X", check_code="AID-01", status="OBSERVED", evidence_summary="AI label", notes=""), key_fields=("product", "check_code"), scope=RuntimeScope.WORKSPACE, workspace_root=workspace_root, data_root=tmp_path)
    upsert_jsonl(l3, make_audit_row(project_id="p", product="X", check_code="L3-01", status="DOCUMENTED", evidence_summary="policy", notes=""), key_fields=("product", "check_code"), scope=RuntimeScope.WORKSPACE, workspace_root=workspace_root, data_root=tmp_path)
    report = build_integrated_report(
        project={"project_id":"p", "project_name":"P", "mode":"BENCHMARK", "products":[{"label":"X"}]},
        final_rows=[],
        layer2_path=l2,
        layer3_path=l3,
    )
    assert "Layer 1｜对话行为测试 / Dialogue Behavioral Testing" in report
    assert "Layer 2｜产品安全机制检查 / Product Safeguard Checks" in report
    assert "Layer 3 Lite｜公开合规证据核查 / Public Compliance Evidence Audit" in report
    assert "0–100" in report
