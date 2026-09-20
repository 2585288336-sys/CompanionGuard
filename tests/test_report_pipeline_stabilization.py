from __future__ import annotations

import json
from pathlib import Path

from companionguard_app.report_pipeline import report_artifact_dir, write_report_artifacts
from companionguard_app.report_validation import validate_report_hard
from companionguard_app.service import run_grounding_validator, run_report_writer
from companionguard_app.runtime_scope import RuntimeScope
from companionguard_llm.client import LLMResponseError
from companionguard_llm.profiles import LLMProfile


def _profile(role: str) -> LLMProfile:
    return LLMProfile(
        role=role,
        provider_type="openai_chat_compatible",
        provider_name="fixture",
        model="fixture-model",
        api_key="fixture-only",
    )


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    root = data_root / "runtime_sessions" / "session" / "projects" / "sandbox"
    root.mkdir(parents=True)
    (root / "layer2_product_safeguards.jsonl").write_text("", encoding="utf-8")
    (root / "layer3_public_evidence.jsonl").write_text("", encoding="utf-8")
    return data_root, root


class TextClient:
    def __init__(self, outputs: list[str], *, finish_reasons: list[str | None] | None = None, completion_tokens: list[int] | None = None):
        self.outputs = list(outputs)
        self.finish_reasons = list(finish_reasons or [None] * len(outputs))
        self.completion_tokens = list(completion_tokens or [3] * len(outputs))
        self.calls: list[dict] = []

    def generate_text(self, **kwargs):
        self.calls.append(kwargs)
        index = len(self.calls) - 1
        return self.outputs[index], {
            "prompt_tokens": 2,
            "completion_tokens": self.completion_tokens[index],
            "finish_reason": self.finish_reasons[index],
        }


class GroundingClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response, {"prompt_tokens": 2, "completion_tokens": 3}


def test_dialogue_uses_none_and_32k(monkeypatch, tmp_path):
    data_root, workspace = _workspace(tmp_path)
    client = TextClient(["dialogue output"])
    profiles = []
    monkeypatch.setattr("companionguard_app.service.make_client", lambda profile: profiles.append(profile) or client)

    result = run_report_writer(
        role="dialogue_report", report_context={}, llm_profile=_profile("dialogue_report"),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
        return_metadata=True, minimum_visible_chars=1,
    )

    assert result["status"] == "PASS"
    assert profiles[0].reasoning_effort == "none"
    assert client.calls[0]["max_output_tokens"] == 32000


def test_integrated_high_then_one_low_fallback(monkeypatch, tmp_path):
    data_root, workspace = _workspace(tmp_path)
    client = TextClient(["", "recovered integrated report"], finish_reasons=[None, None])
    profiles = []
    monkeypatch.setattr("companionguard_app.service.make_client", lambda profile: profiles.append(profile) or client)

    result = run_report_writer(
        role="integrated_report", report_context={}, llm_profile=_profile("integrated_report"),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
        return_metadata=True, minimum_visible_chars=1,
    )

    assert result["status"] == "PASS"
    assert [profile.reasoning_effort for profile in profiles] == ["high", "low"]
    assert [call["max_output_tokens"] for call in client.calls] == [64000, 64000]
    assert [attempt["attempt_number"] for attempt in result["attempts"]] == [1, 2]


def test_integrated_truncation_fallback_can_fail_once(monkeypatch, tmp_path):
    data_root, workspace = _workspace(tmp_path)
    client = TextClient(["partial", "still partial"], finish_reasons=["length", "length"])
    monkeypatch.setattr("companionguard_app.service.make_client", lambda _profile: client)

    result = run_report_writer(
        role="integrated_report", report_context={}, llm_profile=_profile("integrated_report"),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
        return_metadata=True, minimum_visible_chars=1,
    )

    assert result["status"] == "WRITER_TRUNCATED"
    assert len(result["attempts"]) == 2


def test_missing_finish_at_requested_limit_is_suspected_truncation(monkeypatch, tmp_path):
    data_root, workspace = _workspace(tmp_path)
    client = TextClient(["partial"], completion_tokens=[32000])
    monkeypatch.setattr("companionguard_app.service.make_client", lambda _profile: client)

    result = run_report_writer(
        role="dialogue_report", report_context={}, llm_profile=_profile("dialogue_report"),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
        return_metadata=True, minimum_visible_chars=1,
    )

    assert result["status"] == "WRITER_TRUNCATED_SUSPECTED"
    assert result["attempts"][0]["requested_output_limit"] == 32000


def _grounding_pass() -> dict:
    return {
        "validator_version": "fixture",
        "evidence_integrity": {"status": "PASS"},
        "report_quality": {"status": "PASS"},
        "overall_status": "PASS",
        "summary": {"sentences_checked": 1, "supported": 1},
        "required_repairs": [],
    }


def test_grounding_uses_low_16k_and_retries_empty_or_non_json(monkeypatch, tmp_path):
    data_root, workspace = _workspace(tmp_path)
    client = GroundingClient([LLMResponseError("GROUNDING_EMPTY_RESPONSE"), _grounding_pass()])
    monkeypatch.setattr("companionguard_app.service.make_client", lambda _profile: client)

    result = run_grounding_validator(
        draft_report="draft", report_context={}, llm_profile=_profile("grounding_validator"),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
    )

    assert result["overall_status"] == "PASS"
    assert len(client.calls) == 2
    assert all(call["max_output_tokens"] == 16000 for call in client.calls)


def test_grounding_non_json_twice_is_clean_failure(monkeypatch, tmp_path):
    data_root, workspace = _workspace(tmp_path)
    client = GroundingClient([
        LLMResponseError("GROUNDING_NON_JSON_RESPONSE"),
        LLMResponseError("GROUNDING_NON_JSON_RESPONSE"),
    ])
    monkeypatch.setattr("companionguard_app.service.make_client", lambda _profile: client)

    result = run_grounding_validator(
        draft_report="draft", report_context={}, llm_profile=_profile("grounding_validator"),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
    )

    assert result["overall_status"] == "FAIL"
    assert result["failure_type"] == "GROUNDING_VALIDATOR_RESPONSE_ERROR"
    assert result["response_error"] == "GROUNDING_NON_JSON_RESPONSE"


def test_hard_failure_skips_grounding_and_preserves_previous_final(tmp_path):
    data_root, workspace = _workspace(tmp_path)
    project = {"project_id": "fixture", "project_name": "Fixture", "products": []}
    grounding_calls = []

    first = write_report_artifacts(
        report_type="dialogue", project=project, final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl", layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", draft_text="stable report", minimum_visible_chars=1,
        grounding_validator=lambda _draft, _context: _grounding_pass(), scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace, data_root=data_root,
    )
    previous = first["paths"]["final"].read_text(encoding="utf-8")
    assert first["manifest"]["validation_status"] == "PASS"

    second = write_report_artifacts(
        report_type="dialogue", project=project, final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl", layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", draft_text="999", minimum_visible_chars=1,
        grounding_validator=lambda _draft, _context: grounding_calls.append(True) or _grounding_pass(), scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace, data_root=data_root,
    )
    assert second["manifest"]["latest_attempt_status"] == "HARD_VALIDATION_FAILED"
    assert second["grounding"]["overall_status"] == "SKIPPED"
    assert grounding_calls == []
    assert second["paths"]["final"].read_text(encoding="utf-8") == previous


def test_dialogue_and_integrated_artifacts_are_separate(tmp_path):
    data_root, workspace = _workspace(tmp_path)
    project = {"project_id": "fixture", "project_name": "Fixture", "products": []}
    dialogue = write_report_artifacts(
        report_type="dialogue", project=project, final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl", layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", draft_text="dialogue report", minimum_visible_chars=1,
        grounding_validator=lambda _draft, _context: _grounding_pass(), scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace, data_root=data_root,
    )
    integrated_text = "\n".join([
        "## EXECUTIVE_SUMMARY", "摘要：本报告说明当前证据。",
        "## SCOPE", "评测范围：当前项目。", "## LAYER_1_ANALYSIS", "Layer 1：结果。",
        "## LAYER_2_ANALYSIS", "Layer 2：结果。", "## LAYER_3_ANALYSIS", "Layer 3：结果。",
        "## CROSS_LAYER_SYNTHESIS", "跨层：当前证据需要结合分析。",
        "## REGULATORY_RECOMMENDATIONS", "监管建议：继续复核。", "## LIMITATIONS", "局限性：样本有限。",
    ])
    integrated = write_report_artifacts(
        report_type="integrated", project=project, final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl", layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", draft_text=integrated_text, minimum_visible_chars=1,
        grounding_validator=lambda _draft, _context: _grounding_pass(), scope=RuntimeScope.WORKSPACE,
        workspace_root=workspace, data_root=data_root,
    )
    assert dialogue["paths"]["final"].parent == report_artifact_dir(workspace / "reports", "dialogue")
    assert integrated["paths"]["final"].parent == report_artifact_dir(workspace / "reports", "integrated")
    assert dialogue["paths"]["final"] != integrated["paths"]["final"]
    assert not (workspace / "reports" / "final_report.md").exists()


def test_numeric_display_provenance_requires_exact_literal():
    context = {
        "meta": {"context_schema_version": "1.0", "report_type": "dialogue"},
        "coverage": {}, "overall": {}, "products": {}, "modules": {}, "criteria": {},
        "conditions": {"C0": {"finding_rate_display": "16.67%"}}, "comparisons": {},
        "reliability": {}, "representative_findings": [], "layer2": {}, "layer3": {},
        "cross_layer": {}, "limitations": [], "unresolved_questions": [], "verification_needed": [],
    }
    assert validate_report_hard(report_text="比例为16.67%。", context=context, report_type="dialogue")["overall_status"] == "PASS"
    rejected = validate_report_hard(report_text="比例为16.7%。", context=context, report_type="dialogue")
    assert rejected["overall_status"] == "FAIL"
    assert rejected["issues"][0]["sentence_excerpt"] == "比例为16.7%。"
    assert validate_report_hard(report_text="比例为17%。", context=context, report_type="dialogue")["overall_status"] == "FAIL"


def test_grounding_pass_with_zero_checked_sentences_is_failed(tmp_path):
    data_root, workspace = _workspace(tmp_path)
    project = {"project_id": "fixture", "project_name": "Fixture", "products": []}
    result = write_report_artifacts(
        report_type="dialogue", project=project, final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl", layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", draft_text="stable report", minimum_visible_chars=1,
        grounding_validator=lambda _draft, _context: {"overall_status": "PASS", "summary": {"sentences_checked": 0}},
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
    )
    assert result["grounding"]["overall_status"] == "FAIL"
    assert result["grounding"]["failure_type"] == "GROUNDING_ZERO_SENTENCES"
    assert result["manifest"]["report_pipeline_version"] == "phase7e-live-path"
