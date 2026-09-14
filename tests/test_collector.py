import json
import tempfile
import unittest
from pathlib import Path

from companionguard_app.collector import (
    allowed_criteria_for_product,
    build_collection_plan,
    build_raw_case,
    create_collection_session,
    load_collector_config,
    make_case_id,
    mark_session_complete,
    save_step_response,
)
from companionguard_app.collector_storage import (
    append_raw_case,
    get_collection_session,
    load_raw_cases,
    save_evidence_files,
    upsert_collection_session,
)
from companionguard_app.service import criteria_index
from companionguard_judge.pipeline import dry_run


class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.criteria = criteria_index()
        cls.config = load_collector_config()

    def _complete_session(self, criterion_id, scenario_id, condition):
        criterion = self.criteria[criterion_id]
        session = create_collection_session(
            criterion=criterion,
            product_id="MoMood",
            product_name="MoMood",
            product_slug="MoMood",
            product_role="Primary",
            scenario_id=scenario_id,
            condition=condition,
            run_number=1,
            phase="FORMAL",
            collection_date="2026-09-14",
        )
        for i in range(len(session["steps"])):
            session = save_step_response(session, step_index=i, response=f"verbatim response {i + 1}")
        return session, build_raw_case(session, criterion)

    def test_c0_plan_is_consolidated_then_l5(self):
        criterion = self.criteria["DS-01"]
        plan = build_collection_plan(criterion, condition="C0", scenario_id="DS-01")
        self.assertEqual([x["response_turn"] for x in plan], ["A4", "A5"])
        self.assertEqual(plan[0]["prompt_turn"], "L1-L4")
        for i in range(1, 5):
            self.assertIn(criterion["canonical_scenario"][f"L{i}"], plan[0]["prompt"])

    def test_c2_plan_has_five_fixed_turns(self):
        criterion = self.criteria["DS-01"]
        plan = build_collection_plan(criterion, condition="C2", scenario_id="DS-01")
        self.assertEqual([x["prompt_turn"] for x in plan], ["L1", "L2", "L3", "L4", "L5"])
        self.assertEqual([x["response_turn"] for x in plan], ["A1", "A2", "A3", "A4", "A5"])

    def test_hr02_pressure_uses_frozen_pressure_l5(self):
        criterion = self.criteria["HR-02"]
        plan = build_collection_plan(criterion, condition="C1", scenario_id="HR-02")
        self.assertEqual(plan[1]["prompt"], criterion["pressure_variant"]["L5"])

    def test_mr_and_single_turn_shapes(self):
        mr = build_collection_plan(self.criteria["MR"], condition=None, scenario_id="MR-02")
        self.assertEqual([x["response_turn"] for x in mr], ["A_R1", "A_R2"])
        mc = build_collection_plan(self.criteria["MC"], condition=None, scenario_id="MC-01-A")
        pc = build_collection_plan(self.criteria["PC-01"], condition=None, scenario_id="PC-01-A")
        self.assertEqual(len(mc), 1)
        self.assertEqual(len(pc), 1)
        self.assertEqual(mc[0]["response_turn"], "A1")

    def test_doubao_is_restricted_by_config_not_python_rule_branches(self):
        allowed = allowed_criteria_for_product(self.criteria, self.config, "Doubao")
        self.assertEqual(set(allowed), {"DS-01", "DS-02", "FD-01", "FD-03", "HR-02", "MR"})

    def test_case_id_is_readable_and_phase_prevents_stage_collision(self):
        case_id = make_case_id(
            product_slug="MoMood",
            criterion_id="DS-01",
            scenario_id="DS-01",
            condition="C1",
            phase="FORMAL",
            run_number=1,
        )
        self.assertEqual(case_id, "MoMood_DS-01_C1_FORMAL_run01")

    def test_complete_raw_cases_are_judge_ready_for_all_structures(self):
        specs = [
            ("DS-01", "DS-01", "C0"),
            ("DS-01", "DS-01", "C2"),
            ("HR-02", "HR-02", "C1"),
            ("MR", "MR-02", None),
            ("MC", "MC-01-A", None),
            ("PC-01", "PC-01-A", None),
        ]
        for criterion_id, scenario_id, condition in specs:
            with self.subTest(criterion_id=criterion_id, scenario_id=scenario_id, condition=condition):
                session, case = self._complete_session(criterion_id, scenario_id, condition)
                self.assertEqual(dry_run([case], self.criteria), [])
                self.assertEqual(case["phase"], "FORMAL")
                self.assertEqual(case["collection_status"], "COMPLETE")
                self.assertTrue(case["collection_trace"])
                if criterion_id == "MC":
                    self.assertEqual(case["category"], "MC-01")
                complete = mark_session_complete(session)
                self.assertEqual(complete["collection_status"], "COMPLETE")


    def test_response_is_preserved_verbatim(self):
        criterion = self.criteria["MC"]
        session = create_collection_session(
            criterion=criterion,
            product_id="MoMood", product_name="MoMood", product_slug="MoMood",
            product_role="Primary", scenario_id="MC-01-A", condition=None,
            run_number=1, phase="SMOKE", collection_date="2026-09-14",
        )
        raw = "  exact response with boundary whitespace\n"
        session = save_step_response(session, step_index=0, response=raw)
        self.assertEqual(session["steps"][0]["response"], raw)
        case = build_raw_case(session, criterion)
        self.assertEqual(case["conversation"][-1]["content"], raw)

    def test_session_resume_and_raw_append(self):
        criterion = self.criteria["MR"]
        session = create_collection_session(
            criterion=criterion,
            product_id="MoMood",
            product_name="MoMood",
            product_slug="MoMood",
            product_role="Primary",
            scenario_id="MR-01",
            condition=None,
            run_number=2,
            phase="CALIBRATION",
            collection_date="2026-09-14",
        )
        session = save_step_response(session, step_index=0, response="first raw response")
        with tempfile.TemporaryDirectory() as td:
            sessions_path = Path(td) / "sessions.jsonl"
            raw_path = Path(td) / "raw.jsonl"
            upsert_collection_session(session, path=sessions_path)
            restored = get_collection_session(session["session_id"], path=sessions_path)
            self.assertEqual(restored["steps"][0]["response"], "first raw response")
            restored = save_step_response(restored, step_index=1, response="second raw response")
            case = build_raw_case(restored, criterion)
            append_raw_case(case, path=raw_path)
            self.assertEqual(load_raw_cases(raw_path)[0]["case_id"], case["case_id"])
            with self.assertRaises(ValueError):
                append_raw_case(case, path=raw_path)

    def test_evidence_is_stored_under_case_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "evidence"
            paths = save_evidence_files(
                case_id="MoMood_DS-01_C0_FORMAL_run01",
                response_turn="A4",
                files=[("screen.png", b"not-a-real-png-but-storage-is-byte-preserving")],
                evidence_dir=root,
            )
            self.assertEqual(len(paths), 1)
            self.assertTrue((root / "MoMood_DS-01_C0_FORMAL_run01" / "A4_01.png").exists())


if __name__ == "__main__":
    unittest.main()
