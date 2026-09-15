import unittest

from companionguard_app.display_labels import (
    HUMAN_VALIDITY_OPTIONS,
    condition_label,
    criterion_label,
    human_validity_index,
    module_label,
    structure_label,
    turn_label,
)


class V083UiLabelTests(unittest.TestCase):
    def test_conditions_use_the_frozen_chinese_first_terminology(self):
        self.assertEqual(condition_label("C0"), "C0｜标准条件 / Baseline Condition")
        self.assertEqual(condition_label("C1"), "C1｜压力条件 / Pressure Condition")
        self.assertEqual(condition_label("C2"), "C2｜多轮条件 / Sequential Multi-turn Condition")

    def test_single_turn_structures_do_not_render_as_not_applicable(self):
        for template in ("mr_minor_relationship", "single_turn_regulatory_content"):
            label = condition_label(None, template=template)
            self.assertNotIn("N/A", label)
            self.assertNotIn("不适用", label)
        self.assertIn("两轮追问测试", structure_label("mr_minor_relationship"))
        self.assertIn("单轮专项测试", structure_label("single_turn_regulatory_content"))

    def test_turn_labels_distinguish_pressure_l5_and_sequential_turns(self):
        self.assertEqual(turn_label("L1-L4"), "L1–L4｜合并输入 / Consolidated Input")
        self.assertEqual(turn_label("L5", condition="C1"), "Pressure L5｜压力触发 / Pressure Trigger")
        self.assertEqual(turn_label("L5", condition="C0"), "L5｜标准触发 / Standard Trigger")
        self.assertIn("L2｜个人与关系背景", turn_label("L2", template="core_l1_l5"))

    def test_official_module_and_criterion_labels_are_display_only(self):
        self.assertIn("Module A｜关系安全", module_label("relationship_safety"))
        self.assertEqual(criterion_label("DS-01"), "DS-01｜排他性关系判断")
        self.assertEqual(criterion_label("MC"), "MC｜未成年人内容保护专项测试")
        self.assertEqual(criterion_label("PC-07"), "PC-07｜谣言、侮辱诽谤与第三方权益侵害")

    def test_human_validity_control_requires_explicit_choice_for_auto_review(self):
        self.assertEqual(HUMAN_VALIDITY_OPTIONS, ("VALID", "INVALID"))
        self.assertEqual(human_validity_index(None, "VALID"), 0)
        self.assertIsNone(human_validity_index(None, "REVIEW"))
        self.assertEqual(human_validity_index("INVALID", "REVIEW"), 1)


if __name__ == "__main__":
    unittest.main()
