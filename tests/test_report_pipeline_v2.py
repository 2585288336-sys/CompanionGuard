from __future__ import annotations

from pathlib import Path

from companionguard_app.report_pipeline import write_report_artifacts
from companionguard_app.runtime_scope import RuntimeScope


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    workspace = data_root / "runtime_sessions" / "session" / "projects" / "sandbox"
    workspace.mkdir(parents=True)
    (workspace / "layer2_product_safeguards.jsonl").write_text("", encoding="utf-8")
    (workspace / "layer3_public_evidence.jsonl").write_text("", encoding="utf-8")
    return data_root, workspace


def _project() -> dict:
    return {"project_id": "fixture", "project_name": "Fixture", "products": []}


def _pass() -> dict:
    return {"overall_status": "PASS", "summary": {"sentences_checked": 1, "supported": 1}}


def _write(tmp_path: Path, **kwargs):
    data_root, workspace = _workspace(tmp_path)
    return write_report_artifacts(
        report_type="dialogue", project=_project(), final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl",
        layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace, data_root=data_root, minimum_visible_chars=1,
        **kwargs,
    )


def test_hard_repair_is_one_shot_and_receives_deterministic_issues(tmp_path):
    payloads = []
    result = _write(
        tmp_path, draft_text="999", grounding_validator=lambda _draft, _context: _pass(),
        hard_repair=lambda payload: payloads.append(payload) or "repaired report",
    )

    assert result["hard_validation"]["overall_status"] == "PASS"
    assert result["grounding"]["overall_status"] == "PASS"
    assert result["manifest"]["hard_validation_attempts"] == 2
    assert result["manifest"]["grounding_attempts"] == 1
    assert result["manifest"]["targeted_repair_attempted"] is True
    assert result["targeted_repair"]["status"] == "PASS"
    assert len(payloads) == 1
    assert payloads[0]["repair_kind"] == "HARD_VALIDATION"
    assert payloads[0]["issues"][0]["issue_type"] == "NUMBER_MISMATCH"
    assert payloads[0]["repair_contract"]["max_attempts"] == 1


def test_grounding_repair_runs_once_only_for_localized_issue(tmp_path):
    calls = []
    repairs = []

    def grounding(draft, _context):
        calls.append(draft)
        if len(calls) == 1:
            return {
                "overall_status": "FAIL",
                "summary": {"sentences_checked": 1, "critical_errors": 1},
                "issues": [{"sentence_id": "s1", "sentence_excerpt": draft, "issue_types": ["UNSUPPORTED_CLAIM"]}],
            }
        return _pass()

    result = _write(
        tmp_path, draft_text="stable report", grounding_validator=grounding,
        grounding_repair=lambda payload: repairs.append(payload) or "repaired report",
    )

    assert calls == ["stable report", "repaired report"]
    assert len(repairs) == 1
    assert repairs[0]["repair_kind"] == "GROUNDING"
    assert result["manifest"]["hard_validation_attempts"] == 2
    assert result["manifest"]["grounding_attempts"] == 2
    assert result["manifest"]["final_status"] == "PASS"
    assert result["paths"]["final"].read_text(encoding="utf-8") == "repaired report"


def test_unknown_grounding_issue_does_not_trigger_targeted_repair(tmp_path):
    repairs = []
    result = _write(
        tmp_path, draft_text="stable report",
        grounding_validator=lambda _draft, _context: {
            "overall_status": "FAIL",
            "summary": {"sentences_checked": 1, "critical_errors": 1},
            "issues": [{"sentence_id": "unknown", "issue_types": ["UNSUPPORTED_CLAIM"]}],
        },
        grounding_repair=lambda payload: repairs.append(payload) or "must not be used",
    )

    assert repairs == []
    assert result["targeted_repair"]["attempted"] is False
    assert result["manifest"]["targeted_repair_attempted"] is False
    assert result["grounding"]["summary"]["critical_errors"] == 0
    assert result["grounding"]["blocking_issue_count"] == 0


def test_failed_repair_preserves_previous_final(tmp_path):
    first = _write(tmp_path, draft_text="stable report", grounding_validator=lambda _draft, _context: _pass())
    previous = first["paths"]["final"].read_text(encoding="utf-8")

    data_root = first["paths"]["final"].parents[6]
    workspace = first["paths"]["final"].parents[2]
    second = write_report_artifacts(
        report_type="dialogue", project=_project(), final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl",
        layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", draft_text="999",
        hard_repair=lambda _payload: "998", grounding_validator=lambda _draft, _context: _pass(),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
        minimum_visible_chars=1,
    )

    assert second["manifest"]["validation_status"] == "FAIL"
    assert second["targeted_repair"]["status"] == "FAILED"
    assert second["paths"]["final"].read_text(encoding="utf-8") == previous
