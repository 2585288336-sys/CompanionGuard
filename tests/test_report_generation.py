from __future__ import annotations

import unittest
from unittest.mock import patch

from companionguard_app.grounding_validator import validate_grounding
from companionguard_app.report_validation import validate_report_hard
from companionguard_app.report_pipeline import build_report_context
from companionguard_app.service import run_report_writer
from companionguard_llm.profiles import LLMProfile
from companionguard_llm.client import _parse_json_object
from reporting_integrated_fixture import make_integrated_fixture


def context():
    return {
        "meta": {"context_schema_version": "1.0", "report_type": "integrated"},
        "coverage": {}, "overall": {}, "products": {"豆包": {"formal_cases": 1}},
        "modules": {}, "criteria": {}, "conditions": {"C0": {"finding_rate": 0.214, "finding_rate_display": "21.4%"}, "C1": {"finding_rate": 0.301, "finding_rate_display": "30.1%"}},
        "comparisons": {}, "reliability": {}, "representative_findings": [], "layer2": {}, "layer3": {"records": [{"product": "豆包", "check_code": "L3-04", "status": "NOT_FOUND"}]},
        "cross_layer": {}, "limitations": [], "unresolved_questions": [], "verification_needed": [],
    }


class ReportGenerationValidationTests(unittest.TestCase):
    def check_fail(self, text, issue_type):
        result = validate_report_hard(report_text=text, context=context(), report_type="integrated")
        self.assertEqual(result["overall_status"], "FAIL")
        self.assertIn(issue_type, {item["issue_type"] for item in result["issues"]})

    def test_number_changed(self):
        self.check_fail("压力差值为9.1个百分点。", "NUMBER_MISMATCH")

    def test_unauthorized_calculation(self):
        self.check_fail("C1比C0增加8.7个百分点。", "UNAUTHORIZED_CALCULATION")

    def test_finding_is_not_legal_conclusion(self):
        self.check_fail("该产品被认定为不合规。", "LEGAL_OVERCLAIM")

    def test_layer3_status_semantics(self):
        self.check_fail("L3-04为NOT_FOUND，企业没有建立危机处置制度。", "L3_STATUS_SEMANTIC_ERROR")

    def test_layer3_status_semantics_do_not_cross_contaminate_sections(self):
        result = validate_report_hard(
            report_text="NOT_FOUND 仅表示没有找到公开材料。\nNOT_TRIGGERED 不等于未实施。",
            context=context(),
            report_type="dialogue",
        )
        self.assertEqual(result["overall_status"], "PASS")

    def test_unified_score_is_rejected(self):
        self.check_fail("综合安全分为80分。", "UNAUTHORIZED_SCORE")

    def test_integrated_report_requires_analysis_sections(self):
        result = validate_report_hard(
            report_text="# CompanionGuard 综合报告\n仅有范围说明。",
            context=context(),
            report_type="integrated",
        )
        self.assertEqual(result["overall_status"], "FAIL")
        self.assertIn("MISSING_REQUIRED_SECTION", {item["issue_type"] for item in result["issues"]})

    def test_integrated_report_allows_boundary_disclaimers_and_ids(self):
        text = """## Layer 1｜对话行为测试
## 摘要
## 评测范围
        ## Layer 2｜产品安全机制检查
        ## Layer 3｜公开合规证据核查
        ## 跨层一致与不一致
        ## 监管建议
        ## 局限性
案例 HR-02 和 L3-04 不代表未经支持的数字结论。
NOT_FOUND 不等于未实施；NOT_PUBLICLY_VERIFIABLE 不等于不合规；DOCUMENTED 不等于实际执行到位；FINDING 不等于违法或不合规。
        NOT_FOUND 仅表示在已查材料中未找到，不等于未实施或不合规。
FINDING 不等于违法或不合规。
"""
        result = validate_report_hard(report_text=text, context=context(), report_type="integrated")
        self.assertEqual(result["overall_status"], "PASS")

    def test_representative_case_overreach(self):
        result = validate_grounding(draft_report="该代表案例说明该产品普遍强化用户依赖。", context=context())
        self.assertEqual(result["overall_status"], "FAIL")
        self.assertIn("REPRESENTATIVE_CASE_OVERREACH", result["issues"][0]["issue_types"])

    def test_grounding_accepts_cross_layer_limited_statement(self):
        result = validate_grounding(draft_report="公开材料和产品机制均有相关记录，但部分行为测试仍出现 Finding。", context=context())
        self.assertEqual(result["overall_status"], "PASS")

    def test_integrated_fixture_exposes_cross_layer_patterns_and_small_sample(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as td:
            project, rows, layer2, layer3 = make_integrated_fixture(Path(td))
            report_context = build_report_context(report_type="integrated", project=project, final_rows=rows, layer2_path=layer2, layer3_path=layer3)
        cross_layer = report_context["cross_layer"]
        self.assertEqual(len(cross_layer["aligned_patterns"]), 1)
        self.assertEqual(len(cross_layer["inconsistent_patterns"]), 1)
        self.assertEqual(len(cross_layer["unresolved_patterns"]), 1)
        self.assertTrue(any(item["small_sample"] for item in report_context["conditions"].values()))
        self.assertEqual(report_context["products"]["MoMood"]["formal_cases"], 8)
        self.assertNotEqual(report_context["products"]["MoMood"]["finding_rate"], report_context["products"]["星野"]["finding_rate"])

    def test_integrated_writer_loads_style_guide_and_role_prompt(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        captured = {}

        class FakeClient:
            def generate_text(self, *, system_prompt, payload, max_output_tokens):
                captured["prompt"] = system_prompt
                return "draft", None

        profile = LLMProfile(role="integrated_report", provider_type="openai_chat_compatible", provider_name="test", model="test", api_key="test")
        with TemporaryDirectory() as td:
            with patch("companionguard_app.service.make_client", return_value=FakeClient()), patch("companionguard_app.service.LLM_USAGE_PATH", Path(td) / "usage.jsonl"):
                self.assertEqual(run_report_writer(role="integrated_report", report_context={}, llm_profile=profile), "draft\n")
        self.assertIn("CompanionGuard Chinese Regulatory Research Writing Skill v1.1", captured["prompt"])
        self.assertIn("Integrated Report Writer System Prompt v1.1", captured["prompt"])

    def test_chat_json_adapter_accepts_surrounded_object(self):
        self.assertEqual(_parse_json_object("说明文字\n```json\n{\"overall_status\":\"PASS\"}\n```"), {"overall_status": "PASS"})


if __name__ == "__main__":
    unittest.main()
