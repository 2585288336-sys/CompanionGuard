import hashlib
import json
from pathlib import Path

import pytest

from analysis.report_diagnostics import (
    _elicitation_metric,
    _hr02_metric,
    _mr_metric,
    _successful_judge_rows,
    analyze_project,
    write_analysis,
)


ROOT = Path(__file__).parents[1]
FROZEN = ROOT / "data" / "deployment_seed" / "CompanionGuard-Formal-Full-Benchmark-2026-09"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_dataset_diagnostics_match_v19_acceptance_values():
    result = analyze_project(FROZEN)
    assert result["provenance"]["judge_history_count"] == 287
    assert result["provenance"]["successful_unique_judge_case_count"] == 210
    assert result["robustness"]["pressure"]["gap_display"] == "+6.9 pp"
    assert result["robustness"]["multi_turn"]["gap_display"] == "-2.8 pp"
    flip = result["risk_transition"]["elicitation_flip"]
    assert (flip["eligible_pretrigger_no_finding"], flip["elicitation_flip_count"]) == (96, 8)
    assert flip["human_case_level_crosscheck"] == {"source_level": "HUMAN_FINAL", "finding": 8, "total": 8}
    mr = result["risk_transition"]["mr_second_request"]
    assert (mr["eligible_r1_no_finding"], mr["r1_to_r2_finding"], mr["rate"]) == (6, 0, 0.0)
    assert mr["supporting_transition_counts"] == {"LIMIT_RECOVERY": 1, "PERSISTENT_FINDING": 2, "STABLE_LIMIT": 6}
    hr = result["special_risk_diagnostics"]["hr02_safeguard"]
    assert hr["status_counts"] == {"PRESENT": 4, "ABSENT": 4, "REVIEW": 1}
    assert hr["failure_rate"] is None
    mc = result["special_risk_diagnostics"]["mc_subcategories"]
    assert {key: (value["finding"], value["total"]) for key, value in mc.items()} == {
        "MC-01": (2, 9), "MC-02": (4, 9), "MC-03": (2, 9)
    }


def test_success_selection_ignores_failed_history_and_rejects_duplicate_success():
    rows = [
        {"case_id": "case-1", "status": "error"},
        {"case_id": "case-1", "status": "ok", "result": {}},
        {"case_id": "case-2", "status": "error"},
        {"case_id": "case-2", "status": "ok", "result": {}},
    ]
    assert [row["case_id"] for row in _successful_judge_rows(rows)] == ["case-1", "case-2"]
    with pytest.raises(ValueError, match="Multiple successful"):
        _successful_judge_rows(rows + [{"case_id": "case-1", "status": "ok", "result": {}}])


def test_transition_denominators_are_explicit_and_missing_fields_fail_closed():
    core = [
        {"case_id": "core-1", "judge_template": "core_l1_l5", "result": {"pre_trigger_label": "NO_FINDING", "post_trigger_label": "FINDING"}},
        {"case_id": "core-2", "judge_template": "core_l1_l5", "result": {"pre_trigger_label": "FINDING", "post_trigger_label": "FINDING"}},
    ]
    finals = {"core-1": {"final_label": "FINDING"}, "core-2": {"final_label": "FINDING"}}
    assert _elicitation_metric(core, finals)["eligible_pretrigger_no_finding"] == 1
    mr = [{"case_id": "mr-1", "judge_template": "mr_minor_relationship", "result": {"r1_label": "NO_FINDING", "r2_label": "NO_FINDING", "relationship_transition": "STABLE_LIMIT"}}]
    assert _mr_metric(mr)["eligible_r1_no_finding"] == 1
    with pytest.raises(ValueError, match="missing required fields"):
        _hr02_metric([{ "case_id": "hr-1", "criterion_id": "HR-02", "result": {} }])


def test_hr02_review_is_not_counted_as_failure():
    rows = [
        {"case_id": "hr-1", "criterion_id": "HR-02", "result": {"l5_safeguard_response": "PRESENT"}},
        {"case_id": "hr-2", "criterion_id": "HR-02", "result": {"l5_safeguard_response": "ABSENT"}},
    ] * 4 + [{"case_id": "hr-9", "criterion_id": "HR-02", "result": {"l5_safeguard_response": "REVIEW"}}]
    result = _hr02_metric(rows)
    assert result["status_counts"] == {"PRESENT": 4, "ABSENT": 4, "REVIEW": 1}
    assert result["failure_rate"] is None


def test_artifact_is_byte_deterministic_and_inputs_are_unchanged(tmp_path):
    final_path = FROZEN / "final_results.csv"
    judge_path = FROZEN / "judge_results.jsonl"
    before = (_digest(final_path), _digest(judge_path))
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    write_analysis(FROZEN, first)
    write_analysis(FROZEN, second)
    assert first.read_bytes() == second.read_bytes()
    assert _digest(final_path) == before[0]
    assert _digest(judge_path) == before[1]
    assert json.loads(first.read_text(encoding="utf-8"))["schema_version"] == "1.0"
