from __future__ import annotations

import pytest

from companionguard_app.report_validation import validate_report_hard
from companionguard_app.reporting import (
    _validate_report_context_invariants,
    build_dialogue_report_context,
    build_numeric_fact_registry,
    build_writer_facing_context,
)


def _numeric_context() -> dict:
    return {
        "meta": {"context_schema_version": "1.0", "report_type": "dialogue"},
        "coverage": {}, "overall": {}, "products": {}, "modules": {}, "criteria": {},
        "conditions": {"C0": {"finding_rate_display": "22.2%"}}, "comparisons": {},
        "reliability": {}, "representative_findings": [], "layer2": {}, "layer3": {},
        "cross_layer": {}, "limitations": [], "unresolved_questions": [], "verification_needed": [],
    }


def _case_rows() -> list[dict]:
    specs = (
        ("relationship_safety", 7, 62),
        ("extreme_behavior_and_crisis_response", 3, 27),
        ("information_and_rights_protection", 3, 21),
        ("minor_protection", 2, 36),
        ("prohibited_content_special_test", 7, 63),
    )
    rows = []
    criterion_index = 0
    for module, criterion_total, formal_case_total in specs:
        case_counts = [1] * criterion_total
        case_counts[0] += formal_case_total - criterion_total
        for case_total in case_counts:
            criterion_index += 1
            for case_index in range(case_total):
                rows.append({
                    "case_id": f"case-{criterion_index}-{case_index}",
                    "phase": "FORMAL", "case_validity": "VALID", "final_case_validity": "VALID",
                    "adjudication_status": "REVIEWED", "product": "P", "criterion_id": f"C-{criterion_index}",
                    "criterion_name": "Criterion", "module": module, "condition": "C0",
                    "final_label": "NO_FINDING", "analysis_label": "NO_FINDING",
                    "auto_label": "NO_FINDING", "human_label": "NO_FINDING",
                })
    return rows


def test_structural_prefix_is_masked_but_body_numbers_remain_strict():
    accepted = validate_report_hard(
        report_text="### 4.5 HR-01：本项发现率为 22.2%。\n**7. 建议复测。**",
        context=_numeric_context(), report_type="dialogue",
    )
    assert accepted["overall_status"] == "PASS"

    rejected = validate_report_hard(
        report_text="### 4.5 HR-01：本项发现率为 21.0%。\n**7. 建议复测。**",
        context=_numeric_context(), report_type="dialogue",
    )
    mismatches = [issue for issue in rejected["issues"] if issue["issue_type"] == "NUMBER_MISMATCH"]
    assert [issue["value"] for issue in mismatches] == ["21.0%"]
    assert "21.0%" in mismatches[0]["sentence_excerpt"]


def test_module_counts_separate_criteria_from_formal_cases_and_registry():
    context = build_dialogue_report_context(
        project={"project_id": "p", "products": [{"label": "P"}]},
        final_rows=_case_rows(),
    )
    assert context["criterion_count"] == 22
    assert context["module_criterion_counts"] == {
        "relationship_safety": 7,
        "extreme_behavior_and_crisis_response": 3,
        "information_and_rights_protection": 3,
        "minor_protection": 2,
        "prohibited_content_special_test": 7,
    }
    assert context["module_formal_case_counts"] == {
        "relationship_safety": 62,
        "extreme_behavior_and_crisis_response": 27,
        "information_and_rights_protection": 21,
        "minor_protection": 36,
        "prohibited_content_special_test": 63,
    }
    writer = build_writer_facing_context(context)
    modules = {row["module_key"]: row for row in writer["dialogue_analysis"]["modules"]}
    assert modules["relationship_safety"]["criterion_count"] == 7
    assert modules["relationship_safety"]["formal_case_count"] == 62
    assert any(item["fact_id"] == "modules.relationship_safety.formal_case_count" for item in build_numeric_fact_registry(context))


def test_invalid_report_context_blocks_writer_with_invariant_error():
    context = build_dialogue_report_context(
        project={"project_id": "p", "products": [{"label": "P"}]},
        final_rows=_case_rows(),
    )
    context["module_criterion_counts"]["relationship_safety"] += 1
    with pytest.raises(ValueError, match="REPORT_CONTEXT_INVARIANT_FAILED"):
        _validate_report_context_invariants(context)
    with pytest.raises(ValueError, match="REPORT_CONTEXT_INVARIANT_FAILED"):
        build_writer_facing_context(context)
