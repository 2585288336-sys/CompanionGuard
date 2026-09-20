from __future__ import annotations

from pathlib import Path

from companionguard_app.report_validation import validate_report_hard
from companionguard_app.reporting import build_dialogue_report_context, build_writer_facing_context


ROOT = Path(__file__).resolve().parents[1]


def _rows_for_criteria(count: int) -> list[dict]:
    return [
        {
            "phase": "FORMAL",
            "case_validity": "VALID",
            "final_case_validity": "VALID",
            "adjudication_status": "REVIEWED",
            "auto_label": "NO_FINDING",
            "human_label": "NO_FINDING",
            "final_label": "NO_FINDING",
            "product": "P",
            "criterion_id": f"C-{chr(64 + index)}",
            "criterion_name": "Criterion",
            "module": "relationship_safety",
            "condition": "C0",
        }
        for index in range(1, count + 1)
    ]


def test_dialogue_context_and_writer_context_expose_deterministic_criterion_count():
    context = build_dialogue_report_context(
        project={"project_id": "p", "products": [{"label": "P"}]},
        final_rows=_rows_for_criteria(22),
    )
    assert len(context["criteria"]) == 22
    assert context["criterion_count"] == 22

    writer = build_writer_facing_context(context)
    assert writer["criterion_count"] == 22


def test_dialogue_numeric_validation_accepts_22_and_rejects_21():
    context = build_dialogue_report_context(
        project={"project_id": "p", "products": [{"label": "P"}]},
        final_rows=_rows_for_criteria(22),
    )

    accepted = validate_report_hard(
        report_text="本轮覆盖 22 个 criterion。",
        context=context,
        report_type="dialogue",
    )
    assert accepted["overall_status"] == "PASS"

    rejected = validate_report_hard(
        report_text="本轮覆盖 21 个 criterion。",
        context=context,
        report_type="dialogue",
    )
    assert rejected["overall_status"] == "FAIL"
    assert any(issue["issue_type"] == "NUMBER_MISMATCH" and issue["value"] == "21" for issue in rejected["issues"])


def test_dialogue_prompt_preserves_layer_boundaries_and_count_contract():
    prompt = (ROOT / "prompts" / "reporting" / "dialogue_report_v1.1.md").read_text(encoding="utf-8")
    assert "criterion_count" in prompt
    assert "不得自行数 `criteria` 列表" in prompt
    assert "本报告聚焦 Layer 1" in prompt
    assert "不表示项目没有 Layer 2 或 Layer 3 数据" in prompt
    assert "综合分析见 Integrated Report" in prompt
    assert "不要把 Layer 2 / Layer 3 逐条 records 注入本报告" in prompt
