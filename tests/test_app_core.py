import tempfile
import unittest
from pathlib import Path

from companionguard_app.cases import build_conversation_template, flatten_single_turn_scenarios
from companionguard_app.metrics import overall_macro_finding_rate, robustness_gap
from companionguard_app.storage import build_final_results, load_adjudications, save_adjudication
from companionguard_app.runtime_scope import RuntimeScope


class AppCoreTests(unittest.TestCase):
    def test_core_template_uses_pressure_l5(self):
        criterion = {
            "judge_template": "core_l1_l5",
            "canonical_scenario": {"L1": "1", "L2": "2", "L3": "3", "L4": "4", "L5": "base"},
            "pressure_variant": {"L5": "pressure"},
        }
        turns = build_conversation_template(criterion, condition="C1")
        self.assertEqual(turns[-2]["content"], "pressure")

    def test_flatten_mc_scenarios(self):
        criterion = {
            "criterion_id": "MC",
            "canonical_scenario": {
                "MC-01": {"tests": {"MC-01-A": {"prompt": "p"}}}
            },
        }
        self.assertEqual(flatten_single_turn_scenarios(criterion), {"MC-01-A": "p"})

    def test_adjudication_upsert(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "adj.csv"
            save_adjudication(
                case_id="c1", auto_label="FINDING", human_label="FINDING", path=path, scope=RuntimeScope.WORKSPACE
            )
            save_adjudication(
                case_id="c1", auto_label="FINDING", human_label="NO_FINDING",
                override_reason="FALSE_POSITIVE_TARGET_BEHAVIOR", path=path, scope=RuntimeScope.WORKSPACE,
            )
            rows = load_adjudications(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["final_label"], "NO_FINDING")

    def test_official_macro_requires_all_five_modules(self):
        rows = [{"module": "relationship_safety", "final_label": "FINDING"}]
        self.assertIsNone(overall_macro_finding_rate(rows))


    def test_final_results_propagate_collection_phase(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            judge_path = root / "judge.jsonl"
            adj_path = root / "adj.csv"
            output_path = root / "final.csv"
            judge_row = {
                "case_id": "c1", "criterion_id": "DS-01", "status": "ok",
                "product": "MoMood", "condition": None, "auto_label": "NO_FINDING",
                "judge_template": "core_l1_l5", "judge": {"model": "demo"},
                "metadata": {"phase": "FORMAL", "scenario_id": "DS-01", "run_number": 1, "collection_date": "2026-09-14"},
                "result": {"matched_target_behaviors": [], "evidence": [], "rationale": "ok"},
            }
            judge_path.write_text(__import__("json").dumps(judge_row, ensure_ascii=False) + "\n", encoding="utf-8")
            save_adjudication(case_id="c1", auto_label="NO_FINDING", human_label="NO_FINDING", path=adj_path, scope=RuntimeScope.WORKSPACE)
            rows = build_final_results(
                {"DS-01": {"criterion_name_zh": "x", "module": "relationship_safety"}},
                judge_path=judge_path, adjudication_path=adj_path, output_path=output_path, scope=RuntimeScope.WORKSPACE,
            )
            self.assertEqual(rows[0]["phase"], "FORMAL")
            self.assertEqual(rows[0]["scenario_id"], "DS-01")
            self.assertEqual(rows[0]["condition"], "N/A")
            self.assertEqual(rows[0]["case_validity"], "VALID")

    def test_robustness_gap(self):
        rows = [
            {"criterion_id": "A", "condition": "C0", "final_label": "NO_FINDING"},
            {"criterion_id": "A", "condition": "C1", "final_label": "FINDING"},
        ]
        self.assertEqual(robustness_gap(rows, "C1"), 1.0)


if __name__ == "__main__":
    unittest.main()
