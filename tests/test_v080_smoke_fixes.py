from __future__ import annotations

from pathlib import Path

from companionguard_app.collector import build_queue_items_from_selections
from companionguard_app.collector_storage import resolve_evidence_path
from companionguard_app.metrics import finding_rate, valid_case_rows
from companionguard_app.reporting import build_integrated_report
from companionguard_app.service import criteria_index


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
    assert "Adjudicated FORMAL cases: 1" in report
    assert "FORMAL cases excluded by Case Validity: 1" in report
