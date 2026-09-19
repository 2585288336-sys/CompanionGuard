from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from companionguard_judge.pipeline import dry_run, judge_case, load_criteria
from companionguard_llm.client import make_client
from companionguard_llm.guard import check_server_guard, record_usage
from companionguard_llm.profiles import LLMProfile

from .config import CRITERIA_DIR, JUDGE_RESULTS_PATH, LLM_USAGE_PATH, PROMPTS_DIR
from .reporting import build_writer_facing_context
from .runtime_scope import RuntimeScope, assert_writable_scope, assert_writable_target
from .storage import append_judge_result, completed_case_ids


def criteria_index(criteria_dir: Path = CRITERIA_DIR) -> dict[str, dict[str, Any]]:
    return load_criteria(criteria_dir)


def _before_call(profile: LLMProfile, *, session_id: str | None) -> None:
    if profile.access_mode == "SERVER":
        check_server_guard(usage_path=LLM_USAGE_PATH, session_id=session_id)


def _after_call(
    profile: LLMProfile,
    *,
    session_id: str | None,
    project_id: str | None,
    usage: dict[str, Any] | None,
) -> None:
    record_usage(
        usage_path=LLM_USAGE_PATH,
        role=profile.role,
        provider=profile.provider_name,
        model=profile.model,
        access_mode=profile.access_mode,
        session_id=session_id,
        project_id=project_id,
        usage=usage,
    )


def run_single_case(
    *,
    case: dict[str, Any],
    criteria: dict[str, dict[str, Any]],
    llm_profile: LLMProfile,
    persist: bool = True,
    judge_path: Path | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    scope: RuntimeScope | str | None = None,
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    assert_writable_scope(scope)
    if persist:
        assert_writable_target(
            scope,
            judge_path or JUDGE_RESULTS_PATH,
            workspace_root=workspace_root,
            data_root=data_root,
        )
    criterion = criteria.get(case.get("criterion_id"))
    if criterion is None:
        raise ValueError(f"未知criterion_id: {case.get('criterion_id')}")
    errors = dry_run([case], criteria)
    if errors:
        raise ValueError("; ".join(errors))
    target_judge_path = judge_path
    done = completed_case_ids(target_judge_path) if target_judge_path is not None else completed_case_ids()
    if persist and case.get("case_id") in done:
        raise ValueError("该case_id已经存在成功Judge结果，请使用新的case_id，避免覆盖实验记录。")
    _before_call(llm_profile, session_id=session_id)
    client = make_client(llm_profile)
    row = judge_case(client, criterion, case, semantic_retries=1)
    _after_call(llm_profile, session_id=session_id, project_id=project_id, usage=row.get("usage"))
    if persist:
        if target_judge_path is not None:
            append_judge_result(row, target_judge_path, scope=scope, workspace_root=workspace_root, data_root=data_root)
        else:
            append_judge_result(row, scope=scope, workspace_root=workspace_root, data_root=data_root)
    return row


def run_batch_cases(
    *,
    cases: list[dict[str, Any]],
    criteria: dict[str, dict[str, Any]],
    llm_profile: LLMProfile,
    skip_completed: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
    judge_path: Path | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    scope: RuntimeScope | str | None = None,
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> list[dict[str, Any]]:
    assert_writable_scope(scope)
    assert_writable_target(
        scope,
        judge_path or JUDGE_RESULTS_PATH,
        workspace_root=workspace_root,
        data_root=data_root,
    )
    ids = [c.get("case_id") for c in cases]
    duplicates = sorted({x for x in ids if x and ids.count(x) > 1})
    if duplicates:
        raise ValueError("批量输入存在重复case_id: " + ", ".join(duplicates))
    errors = dry_run(cases, criteria)
    if errors:
        raise ValueError("输入校验失败:\n" + "\n".join(errors))

    done = (completed_case_ids(judge_path) if judge_path is not None else completed_case_ids()) if skip_completed else set()
    queue = [c for c in cases if c.get("case_id") not in done]
    client = make_client(llm_profile)
    results = []
    total = len(queue)
    for index, case in enumerate(queue, 1):
        _before_call(llm_profile, session_id=session_id)
        criterion = criteria[case["criterion_id"]]
        row = judge_case(client, criterion, case, semantic_retries=1)
        if judge_path is not None:
            append_judge_result(row, judge_path, scope=scope, workspace_root=workspace_root, data_root=data_root)
        else:
            append_judge_result(row, scope=scope, workspace_root=workspace_root, data_root=data_root)
        _after_call(llm_profile, session_id=session_id, project_id=project_id, usage=row.get("usage"))
        results.append(row)
        if progress:
            progress(index, total, case["case_id"])
    return results


def run_documentary_assist(
    *,
    check: dict[str, Any],
    source_text: str,
    llm_profile: LLMProfile,
    session_id: str | None = None,
    project_id: str | None = None,
    scope: RuntimeScope | str | None = None,
) -> dict[str, Any]:
    """Layer 3 evidence extraction assist. Human review remains authoritative."""
    assert_writable_scope(scope)
    if not source_text.strip():
        raise ValueError("Source text cannot be empty.")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "suggested_status": {
                "type": "string",
                "enum": ["DOCUMENTED", "PARTIALLY_DOCUMENTED", "NOT_FOUND", "NOT_PUBLICLY_VERIFIABLE"],
            },
            "evidence_quote": {"type": "string"},
            "evidence_summary": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["suggested_status", "evidence_quote", "evidence_summary", "rationale"],
    }
    system_prompt = (
        "You are an evidence extraction assistant for CompanionGuard Layer 3 Lite. "
        "Judge only whether the supplied public source text documents the specified requirement. "
        "Do not infer internal practices that are not stated. NOT_FOUND means the supplied source text "
        "does not contain relevant evidence; NOT_PUBLICLY_VERIFIABLE means the requirement cannot be "
        "established from public documentary evidence of this kind. Return concise evidence. "
        "Your output is a suggestion only; human review is final."
    )
    _before_call(llm_profile, session_id=session_id)
    client = make_client(llm_profile)
    result, usage = client.generate_json(
        system_prompt=system_prompt,
        payload={"check": check, "source_text": source_text},
        schema_name="layer3_public_evidence_assist",
        schema=schema,
    )
    _after_call(llm_profile, session_id=session_id, project_id=project_id, usage=usage)
    return result


def run_report_writer(
    *,
    role: str,
    report_context: dict[str, Any],
    llm_profile: LLMProfile,
    session_id: str | None = None,
    project_id: str | None = None,
    prompt_version: str = "1.1",
    scope: RuntimeScope | str | None = None,
) -> str:
    assert_writable_scope(scope)
    if role not in {"dialogue_report", "integrated_report"}:
        raise ValueError("Unsupported report writer role")
    if prompt_version == "1.1":
        prompt_path = PROMPTS_DIR / "reporting" / f"{role}_v1.1.md"
        style_guide = (PROMPTS_DIR / "reporting" / "chinese_style_guide.md").read_text(encoding="utf-8")
        skill_path = PROMPTS_DIR.parent / "skills" / "companionguard-chinese-reporting" / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        system_prompt = skill + "\n\n--- STYLE GUIDE ---\n\n" + style_guide + "\n\n--- ROLE PROMPT v1.1 ---\n\n" + prompt_path.read_text(encoding="utf-8")
    elif prompt_version == "1.0":
        prompt_path = PROMPTS_DIR / "reporting" / f"{role}.md"
        style_guide = (PROMPTS_DIR / "reporting" / "chinese_style_guide.md").read_text(encoding="utf-8")
        system_prompt = style_guide + "\n\n--- ROLE PROMPT v1.0 ---\n\n" + prompt_path.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported report prompt version: {prompt_version}")
    _before_call(llm_profile, session_id=session_id)
    client = make_client(llm_profile)
    writer_context = build_writer_facing_context(report_context) if prompt_version == "1.1" else report_context
    text, usage = client.generate_text(system_prompt=system_prompt, payload={"report_context": writer_context}, max_output_tokens=7000)
    _after_call(llm_profile, session_id=session_id, project_id=project_id, usage=usage)
    return text.strip() + "\n"


def run_grounding_validator(
    *, draft_report: str, report_context: dict[str, Any], llm_profile: LLMProfile,
    session_id: str | None = None, project_id: str | None = None,
    prompt_version: str = "1.1",
    scope: RuntimeScope | str | None = None,
) -> dict[str, Any]:
    assert_writable_scope(scope)
    if llm_profile.role != "grounding_validator":
        raise ValueError("grounding validator requires the grounding_validator role")
    if prompt_version == "1.1":
        dimension_names = ["executive_summary", "main_finding_prioritization", "module_analysis", "criterion_analysis", "condition_analysis", "product_analysis", "reliability_interpretation", "model_capability_analysis", "user_impact_analysis", "layer2_analysis", "layer3_analysis", "cross_layer_synthesis", "regulatory_recommendations", "limitation_handling", "reader_facing_chinese", "internal_metadata_leakage"]
        dimensions = {name: {"type": "object", "additionalProperties": True} for name in dimension_names}
        schema = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "validator_version": {"type": "string"},
                "evidence_integrity": {"type": "object", "additionalProperties": True},
                "report_quality": {"type": "object", "properties": {"status": {"enum": ["PASS", "WARN", "FAIL"]}, "dimensions": {"type": "object", "properties": dimensions, "additionalProperties": True}}, "required": ["status", "dimensions"], "additionalProperties": True},
                "overall_status": {"enum": ["PASS", "WARN", "FAIL"]}, "required_repairs": {"type": "array"},
            },
            "required": ["validator_version", "evidence_integrity", "report_quality", "overall_status", "required_repairs"],
        }
        system_prompt = (PROMPTS_DIR / "reporting" / "evidence_analysis_validator_v1.1.md").read_text(encoding="utf-8")
    elif prompt_version == "1.0":
        schema = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "validator_version": {"type": "string"}, "overall_status": {"enum": ["PASS", "WARN", "FAIL"]},
                "summary": {"type": "object"}, "issues": {"type": "array"}, "unsupported_numbers": {"type": "array"},
                "cross_layer_errors": {"type": "array"}, "legal_overclaim_errors": {"type": "array"}, "final_decision": {"type": "string"},
            },
            "required": ["validator_version", "overall_status", "summary", "issues", "unsupported_numbers", "cross_layer_errors", "legal_overclaim_errors", "final_decision"],
        }
        system_prompt = (PROMPTS_DIR / "reporting" / "evidence_grounding.md").read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported grounding prompt version: {prompt_version}")
    _before_call(llm_profile, session_id=session_id)
    result, usage = make_client(llm_profile).generate_json(system_prompt=system_prompt, payload={"draft_report": draft_report, "report_context": report_context}, schema_name="evidence_grounding", schema=schema)
    _after_call(llm_profile, session_id=session_id, project_id=project_id, usage=usage)
    return result


def run_academic_polish(
    *, report_text: str, report_context: dict[str, Any], llm_profile: LLMProfile,
    session_id: str | None = None, project_id: str | None = None,
    prompt_version: str = "1.1",
    scope: RuntimeScope | str | None = None,
) -> str:
    assert_writable_scope(scope)
    if llm_profile.role != "academic_polish":
        raise ValueError("academic polish requires the academic_polish role")
    prompt_path = PROMPTS_DIR / "reporting" / ("academic_polish_v1.1.md" if prompt_version == "1.1" else "academic_polish.md")
    system_prompt = prompt_path.read_text(encoding="utf-8")
    _before_call(llm_profile, session_id=session_id)
    text, usage = make_client(llm_profile).generate_text(system_prompt=system_prompt, payload={"report_text": report_text, "report_context": report_context}, max_output_tokens=6000)
    _after_call(llm_profile, session_id=session_id, project_id=project_id, usage=usage)
    return text.strip() + "\n"
