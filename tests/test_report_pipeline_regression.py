from __future__ import annotations

from companionguard_app.numeric_tokens import allowed_numeric_token_inventory, scan_numeric_tokens
from companionguard_app.report_validation import validate_report_hard


def _context(display: str) -> dict:
    return {
        "meta": {"context_schema_version": "1.0", "report_type": "dialogue"},
        "coverage": {}, "overall": {}, "products": {}, "modules": {}, "criteria": {},
        "conditions": {"C0": {"finding_rate_display": display}}, "comparisons": {},
        "reliability": {}, "representative_findings": [], "layer2": {}, "layer3": {},
        "cross_layer": {}, "limitations": [], "unresolved_questions": [], "verification_needed": [],
    }


def test_atomic_numeric_lexer_generated_corpus_has_no_duplicate_spans():
    values = (
        "0.0%", "1.0%", "5.7%", "16.67%", "29.6%", "30.6%", "33.3%", "100.0%",
        "0.811", "1.0", "10.0", "0", "1", "22", "175", "209", "210", "287",
        "+6.9 pp", "-2.8 pp", "0 pp",
    )
    wrappers = ("值为{}。", "本轮记录{}。", "结果（{}）", "显示：{}", "与基线相差{}。", "证据支持{}", "该项为{}。", "精确值是{}。", "报告使用{}。", "字段记录{}。", "审核值：{}。", "对照项{}。", "统计字段{}。", "当前显示{}。", "来源值{}。", "最终值{}。", "保留{}。", "正文写作值{}。", "审计记录{}。", "上下文提供{}。", "该数字是{}。", "分析采用{}。", "结果字段{}。", "确定值{}。", "公开显示{}。", "本次输出{}。", "复核记录{}。", "确认数据{}。", "字段值{}。", "结果为{}。", "当前值{}。", "来源为{}。", "已核实{}。", "明确值{}。", "使用数字{}。", "最终确认{}。", "数字显示{}。", "统计为{}。", "记录为{}。", "审计为{}。",
    )
    cases = 0
    for value in values:
        for wrapper in wrappers:
            text = wrapper.format(value)
            tokens = scan_numeric_tokens(text)
            assert len(tokens) == 1, (text, tokens)
            assert tokens[0].normalized == value
            assert len({(token.start, token.end) for token in tokens}) == len(tokens)
            assert tokens[0].normalized in allowed_numeric_token_inventory({"value": value})
            cases += 1
    assert cases == 840


def test_identifier_tokens_are_not_numeric_fragments():
    for identifier in ("C0", "C1", "C2", "HR-02", "DS-01", "PC-07", "run01", "2026-09"):
        assert scan_numeric_tokens(identifier) == []


def test_historical_57_percent_case_no_longer_false_fails():
    result = validate_report_hard(
        report_text="条件发现率为 5.7%。",
        context=_context("5.7%"),
        report_type="dialogue",
    )
    assert result["overall_status"] == "PASS"
    assert result["summary"]["numbers_checked"] == 1


def test_context_and_report_use_the_same_atomic_inventory():
    context = _context("+6.9 pp")
    assert validate_report_hard(report_text="差值为 +6.9 pp。", context=context, report_type="dialogue")["overall_status"] == "PASS"
    assert validate_report_hard(report_text="差值为 +6.9 pp。", context=_context("6.9 pp"), report_type="dialogue")["overall_status"] == "FAIL"


def test_deterministic_alternate_percentage_point_display_is_explicit():
    context = _context("6.9 个百分点")
    context["comparisons"] = {
        "pressure": {
            "display_value": "+6.9 pp",
            "percentage_points_display": "+6.9 个百分点",
            "absolute_percentage_points_display": "6.9 个百分点",
        }
    }
    assert validate_report_hard(report_text="差值为 6.9 个百分点。", context=context, report_type="dialogue")["overall_status"] == "PASS"
