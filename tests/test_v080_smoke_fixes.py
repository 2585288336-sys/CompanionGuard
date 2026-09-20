from __future__ import annotations

import json
from pathlib import Path

from companionguard_app.adjudication import build_sampling_plan, review_case_ids
from companionguard_app.collector import build_queue_items_from_selections
from companionguard_app.collector_storage import resolve_evidence_path
from companionguard_app.metrics import finding_rate, valid_case_rows
from companionguard_app.reporting import build_integrated_report
from companionguard_app.service import criteria_index
from companionguard_app.storage import build_final_results
from companionguard_app.runtime_scope import RuntimeScope
from companionguard_app.validity import screen_case_validity
from companionguard_app.reliability import reliability_metrics
from companionguard_judge.pipeline import judge_case


def test_granular_test_plan_can_select_mr02_and_mc01a_only():
    criteria = criteria_index()
    items = build_queue_items_from_selections(
        criteria=criteria,
        selections={
            "MR": {"scenarios": ["MR-02"], "conditions": []},
            "MC": {"scenarios": ["MC-01-A"], "conditions": []},
        },
        product_slug="P",
        phase="SMOKE",
        run_numbers=[1],
    )
    assert [(x["criterion_id"], x["scenario_id"], x["condition"]) for x in items] == [
        ("MR", "MR-02", None),
        ("MC", "MC-01-A", None),
    ]


def test_each_core_criterion_can_have_independent_conditions():
    criteria = criteria_index()
    items = build_queue_items_from_selections(
        criteria=criteria,
        selections={
            "DS-01": {"scenarios": ["DS-01"], "conditions": ["C0", "C1", "C2"]},
            "FD-01": {"scenarios": ["FD-01"], "conditions": ["C0"]},
        },
        product_slug="P",
        phase="SMOKE",
        run_numbers=[1],
    )
    ds = [x for x in items if x["criterion_id"] == "DS-01"]
    fd = [x for x in items if x["criterion_id"] == "FD-01"]
    assert {x["condition"] for x in ds} == {"C0", "C1", "C2"}
    assert {x["condition"] for x in fd} == {"C0"}


def test_integrated_report_reliability_excludes_smoke(tmp_path: Path):
    rows = [
        {
            "phase": "SMOKE",
            "auto_label": "NO_FINDING",
            "human_label": "NO_FINDING",
            "final_label": "NO_FINDING",
            "product": "X",
            "module": "relationship_safety",
            "criterion_id": "DS-01",
            "condition": "C0",
        }
    ]
    report = build_integrated_report(
        project={"project_id": "p", "project_name": "P", "mode": "BENCHMARK", "products": [{"label": "X"}]},
        final_rows=rows,
        layer2_path=tmp_path / "l2.jsonl",
        layer3_path=tmp_path / "l3.jsonl",
    )
    assert "Adjudicated FORMAL cases: 0" in report
    assert "Cases compared: 0" in report


def test_c0_c1_c2_are_separate_case_ids():
    criteria = criteria_index()
    items = build_queue_items_from_selections(
        criteria=criteria,
        selections={"DS-01": {"scenarios": ["DS-01"], "conditions": ["C0", "C1", "C2"]}},
        product_slug="P",
        phase="FORMAL",
        run_numbers=[1],
    )
    assert len({x["case_id"] for x in items}) == 3
    assert {x["condition"] for x in items} == {"C0", "C1", "C2"}


def test_evidence_path_resolves_inside_project(tmp_path: Path):
    evidence = tmp_path / "evidence" / "dialogue" / "case-1" / "A1_01.png"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"not-a-real-image")
    assert resolve_evidence_path("evidence/dialogue/case-1/A1_01.png", tmp_path) == evidence.resolve()
    assert resolve_evidence_path("../outside.png", tmp_path) is None


def test_invalid_and_review_cases_are_excluded_from_risk_metrics():
    rows = [
        {"case_id": "valid", "case_validity": "VALID", "final_label": "FINDING"},
        {"case_id": "invalid", "case_validity": "INVALID", "final_label": "NO_FINDING"},
        {"case_id": "review", "case_validity": "REVIEW", "final_label": "FINDING"},
    ]
    assert [r["case_id"] for r in valid_case_rows(rows)] == ["valid"]
    assert finding_rate(rows) == 1.0


def test_integrated_report_preserves_validity_exclusion_counts(tmp_path: Path):
    rows = [
        {
            "phase": "FORMAL", "case_validity": "VALID", "auto_label": "FINDING",
            "human_label": "FINDING", "final_label": "FINDING", "product": "X",
            "module": "relationship_safety", "criterion_id": "DS-01", "condition": "C0",
        },
        {
            "phase": "FORMAL", "case_validity": "INVALID", "auto_label": "NO_FINDING",
            "human_label": "NO_FINDING", "final_label": "NO_FINDING", "product": "X",
            "module": "relationship_safety", "criterion_id": "DS-01", "condition": "C0",
        },
    ]
    report = build_integrated_report(
        project={"project_id": "p", "project_name": "P", "mode": "BENCHMARK", "products": [{"label": "X"}]},
        final_rows=rows,
        layer2_path=tmp_path / "l2.jsonl",
        layer3_path=tmp_path / "l3.jsonl",
    )
    assert "Collected FORMAL cases: 2" in report
    assert "Adjudicated FORMAL cases: 2" in report
    assert "FORMAL cases excluded by Case Validity: 1" in report


def test_normal_case_validity_is_valid_and_obvious_anomaly_is_review():
    normal = {"conversation": [{"role": "assistant", "content": "我会基于你的问题说明相关信息。"}]}
    empty = {"conversation": [{"role": "assistant", "content": ""}]}
    unrelated = {
        "conversation": [{"role": "assistant", "content": "北京今天最高气温26度。"}],
    }
    assert screen_case_validity(normal) == ("VALID", "")
    assert screen_case_validity(empty)[0] == "REVIEW"
    assert screen_case_validity(unrelated, {"review_note": "response is unrelated to the prompt"}) == ("REVIEW", "OFF_TOPIC_RESPONSE")


def test_judge_pipeline_persists_validity_screen_without_changing_risk_label():
    class FakeJudgeClient:
        model = "test-model"
        provider_name = "test-provider"

        def judge(self, **kwargs):
            return {
                "test_id": "c1",
                "category": "DS-01",
                "label": "NO_FINDING",
                "matched_target_behaviors": [],
                "evidence": [],
                "rationale": "The response is relevant to the prompt.",
                "review_note": None,
            }, {}

    criterion = {"criterion_id": "DS-01", "judge_template": "single_turn_regulatory_content"}
    case = {
        "case_id": "c1",
        "criterion_id": "DS-01",
        "conversation": [{"role": "user", "turn": "P1", "content": "question"}, {"role": "assistant", "turn": "A1", "content": "Relevant answer."}],
    }
    row = judge_case(FakeJudgeClient(), criterion, case)
    assert row["auto_label"] == "NO_FINDING"
    assert row["auto_case_validity"] == "VALID"


def test_reliability_uses_only_reviewed_valid_cases():
    rows = [
        {"auto_label": "FINDING", "human_label": "FINDING", "final_case_validity": "VALID", "adjudication_status": "REVIEWED"},
        {"auto_label": "FINDING", "human_label": "NO_FINDING", "final_case_validity": "VALID", "adjudication_status": "UNREVIEWED"},
        {"auto_label": "FINDING", "human_label": "NO_FINDING", "final_case_validity": "INVALID", "adjudication_status": "REVIEWED"},
    ]
    assert reliability_metrics(rows)["n"] == 1


def test_sample_plan_is_deterministic_and_forces_review_cases():
    rows = [
        {"case_id": "a", "status": "ok", "phase": "FORMAL", "product": "P1", "criterion_id": "DS-01", "condition": "C0", "auto_label": "NO_FINDING"},
        {"case_id": "b", "status": "ok", "phase": "FORMAL", "product": "P2", "criterion_id": "DS-01", "condition": "C0", "auto_label": "REVIEW"},
        {"case_id": "c", "status": "ok", "phase": "FORMAL", "product": "P1", "criterion_id": "DS-01", "condition": "C1", "auto_label": "NO_FINDING", "auto_case_validity": "REVIEW"},
        {"case_id": "d", "status": "ok", "phase": "SMOKE", "product": "P1", "criterion_id": "DS-01", "condition": "C0", "auto_label": "NO_FINDING"},
    ]
    project = {
        "project_id": "p", "human_adjudication_policy": "SAMPLED_ADJUDICATION",
        "human_adjudication_sampling_method": "STRATIFIED_SAMPLE",
        "human_adjudication_sample_rate": 0.25, "human_adjudication_random_seed": 7,
        "human_adjudication_strata": ["product", "criterion_id", "condition"],
    }
    plan_a = build_sampling_plan(judge_rows=rows, project=project, created_at="fixed")
    plan_b = build_sampling_plan(judge_rows=rows, project=project, created_at="fixed")
    assert plan_a["selected_case_ids"] == plan_b["selected_case_ids"]
    assert {"b", "c"}.issubset(plan_a["selected_case_ids"])
    assert review_case_ids(judge_rows=rows, project=project, sampling_plan=plan_a) == set(plan_a["selected_case_ids"]) | {"d"}


def test_sampled_final_results_do_not_fabricate_human_labels(tmp_path: Path):
    workspace_root = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox"
    workspace_root.mkdir(parents=True)
    judge_path = workspace_root / "judge.jsonl"
    rows = [
        {"case_id": "c1", "criterion_id": "DS-01", "status": "ok", "product": "P", "auto_label": "NO_FINDING", "auto_case_validity": "VALID", "condition": "C0", "metadata": {"phase": "FORMAL"}, "result": {}},
    ]
    judge_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    final = build_final_results({}, judge_path=judge_path, adjudication_path=workspace_root / "missing.csv", output_path=workspace_root / "final.csv", policy="SAMPLED_ADJUDICATION", scope=RuntimeScope.WORKSPACE, workspace_root=workspace_root, data_root=tmp_path)
    assert final[0]["adjudication_status"] == "UNREVIEWED"
    assert final[0]["analysis_label"] == "NO_FINDING"
    assert final[0]["human_label"] == ""
    assert final[0]["final_label"] == ""
