from __future__ import annotations

import unittest

from companionguard_app.grounding_validator import validate_grounding
from companionguard_app.report_validation import validate_report_hard


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

    def test_unified_score_is_rejected(self):
        self.check_fail("综合安全分为80分。", "UNAUTHORIZED_SCORE")

    def test_representative_case_overreach(self):
        result = validate_grounding(draft_report="该代表案例说明该产品普遍强化用户依赖。", context=context())
        self.assertEqual(result["overall_status"], "FAIL")
        self.assertIn("REPRESENTATIVE_CASE_OVERREACH", result["issues"][0]["issue_types"])

    def test_grounding_accepts_cross_layer_limited_statement(self):
        result = validate_grounding(draft_report="公开材料和产品机制均有相关记录，但部分行为测试仍出现 Finding。", context=context())
        self.assertEqual(result["overall_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
