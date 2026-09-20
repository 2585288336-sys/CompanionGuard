from __future__ import annotations

import json
import warnings
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from companionguard_judge.pipeline import dry_run, judge_case, load_criteria
from companionguard_llm.client import LLMResponseError, is_deepseek_provider, make_client
from companionguard_llm.guard import check_server_guard, record_usage
from companionguard_llm.profiles import LLMProfile

from .config import CRITERIA_DIR, JUDGE_RESULTS_PATH, LLM_USAGE_PATH, PROMPTS_DIR
from .grounding_validator import normalize_grounding_result
from .reporting import build_writer_facing_context
from .report_schema import REPORT_PIPELINE_VERSION
from .runtime_scope import RuntimeScope, assert_writable_scope, assert_writable_target
from .storage import append_judge_result, completed_case_ids


def criteria_index(criteria_dir: Path = CRITERIA_DIR) -> dict[str, dict[str, Any]]:
    return load_criteria(criteria_dir)


def _workspace_usage_path(
    *,
    scope: RuntimeScope | str | None,
    workspace_root: Path | None,
    data_root: Path | None = None,
) -> Path:
    """Return the validated project-level usage path for the active Workspace."""

    assert_writable_scope(scope)
    if workspace_root is None:
        raise ValueError("A validated Workspace root is required for LLM usage logging.")
    return assert_writable_target(
        scope,
        Path(workspace_root) / "llm_usage.jsonl",
        workspace_root=workspace_root,
        data_root=data_root,
    )


def _before_call(profile: LLMProfile, *, session_id: str | None) -> None:
    if profile.access_mode == "SERVER":
        check_server_guard(usage_path=LLM_USAGE_PATH, session_id=session_id)


def _after_call(
    profile: LLMProfile,
    *,
    session_id: str | None,
    project_id: str | None,
    usage: dict[str, Any] | None,
    project_usage_path: Path,
    observability: dict[str, Any] | None = None,
) -> None:
    try:
        record_usage(
            usage_path=project_usage_path,
            role=profile.role,
            provider=profile.provider_name,
            model=profile.model,
            access_mode=profile.access_mode,
            session_id=session_id,
            project_id=project_id,
            usage=usage,
            observability=observability,
        )
    except Exception as exc:
        warnings.warn(
            f"Unable to persist Workspace LLM usage; business output is preserved: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )

    # The global file is infrastructure-only state for server-funded quota
    # enforcement.  It is deliberately separate from the exported Workspace
    # project artifact above.
    if profile.access_mode == "SERVER":
        record_usage(
            usage_path=LLM_USAGE_PATH,
            role=profile.role,
            provider=profile.provider_name,
            model=profile.model,
            access_mode=profile.access_mode,
            session_id=session_id,
            project_id=project_id,
            usage=usage,
            observability=observability,
        )


REPORT_ROLE_DEFAULTS = {
    "dialogue_report": ("none", 32000),
    "integrated_report": ("high", 64000),
    "grounding_validator": ("low", 16000),
    "academic_polish": ("low", 6000),
}


def _configured_int(role: str, suffix: str, default: int) -> int:
    raw = os.environ.get(f"COMPANIONGUARD_{role.upper()}_{suffix}", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid {suffix} for role={role}: {raw}") from exc
    if value <= 0:
        raise ValueError(f"{suffix} for role={role} must be positive")
    return value


def _effective_report_profile(profile: LLMProfile, *, role: str, fallback: bool = False) -> LLMProfile:
    default_reasoning, _ = REPORT_ROLE_DEFAULTS[role]
    env_name = f"COMPANIONGUARD_{role.upper()}_{'FALLBACK_' if fallback else ''}REASONING_EFFORT"
    fallback_default = "low" if role == "integrated_report" and fallback else default_reasoning
    reasoning = os.environ.get(env_name, "").strip() or fallback_default
    return replace(profile, reasoning_effort=reasoning)


def report_profile_diagnostics(profile: LLMProfile, *, requested_output_limit: int) -> dict[str, Any]:
    """Return non-secret diagnostics for a report request."""
    is_chat = profile.provider_type == "openai_chat_compatible"
    return {
        "provider_type": profile.provider_type,
        "provider_name": profile.provider_name,
        "model": profile.model,
        "adapter_type": profile.provider_type,
        "reasoning_effort": profile.reasoning_effort,
        "thinking_mode": (
            "disabled" if profile.reasoning_effort == "none" else "enabled"
        ) if is_chat and is_deepseek_provider(profile) else None,
        "requested_output_limit": requested_output_limit,
    }


def _response_meta(usage: dict[str, Any] | None) -> dict[str, Any]:
    return dict(usage or {})


def _writer_status(
    text: str | None,
    usage: dict[str, Any] | None,
    *,
    minimum_chars: int = 500,
    requested_output_limit: int | None = None,
) -> str:
    value = (text or "").strip()
    meta = _response_meta(usage)
    finish_reason = str(meta.get("finish_reason") or "").lower()
    incomplete_reason = str(meta.get("incomplete_reason") or "").lower()
    if finish_reason in {"length", "max_tokens", "max_output_tokens"} or incomplete_reason in {"length", "max_tokens", "max_output_tokens"}:
        return "WRITER_TRUNCATED"
    if finish_reason in {"content_filter", "insufficient_system_resource", "aborted", "unknown"} or incomplete_reason in {"content_filter", "insufficient_system_resource", "aborted", "unknown"}:
        return "WRITER_INCOMPLETE"
    token_count = meta.get("completion_tokens") or meta.get("output_tokens")
    if not finish_reason and requested_output_limit and isinstance(token_count, (int, float)) and token_count >= requested_output_limit:
        return "WRITER_TRUNCATED_SUSPECTED"
    if not value or len(value) < minimum_chars:
        return "WRITER_EMPTY_OUTPUT"
    return "PASS"


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
    project_usage_path = _workspace_usage_path(scope=scope, workspace_root=workspace_root, data_root=data_root)
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
    if persist:
        try:
            if target_judge_path is not None:
                append_judge_result(row, target_judge_path, scope=scope, workspace_root=workspace_root, data_root=data_root)
            else:
                append_judge_result(row, scope=scope, workspace_root=workspace_root, data_root=data_root)
        finally:
            _after_call(
                llm_profile,
                session_id=session_id,
                project_id=project_id,
                usage=row.get("usage"),
                project_usage_path=project_usage_path,
            )
    else:
        _after_call(
            llm_profile,
            session_id=session_id,
            project_id=project_id,
            usage=row.get("usage"),
            project_usage_path=project_usage_path,
        )
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
    project_usage_path = _workspace_usage_path(scope=scope, workspace_root=workspace_root, data_root=data_root)
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
        try:
            if judge_path is not None:
                append_judge_result(row, judge_path, scope=scope, workspace_root=workspace_root, data_root=data_root)
            else:
                append_judge_result(row, scope=scope, workspace_root=workspace_root, data_root=data_root)
        finally:
            _after_call(
                llm_profile,
                session_id=session_id,
                project_id=project_id,
                usage=row.get("usage"),
                project_usage_path=project_usage_path,
            )
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
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Layer 3 evidence extraction assist. Human review remains authoritative."""
    project_usage_path = _workspace_usage_path(scope=scope, workspace_root=workspace_root, data_root=data_root)
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
    _after_call(llm_profile, session_id=session_id, project_id=project_id, usage=usage, project_usage_path=project_usage_path)
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
    workspace_root: Path | None = None,
    data_root: Path | None = None,
    return_metadata: bool = False,
    minimum_visible_chars: int = 500,
) -> str | dict[str, Any]:
    project_usage_path = _workspace_usage_path(scope=scope, workspace_root=workspace_root, data_root=data_root)
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
    writer_context = build_writer_facing_context(report_context) if prompt_version == "1.1" else report_context
    default_reasoning, default_limit = REPORT_ROLE_DEFAULTS[role]
    attempts: list[dict[str, Any]] = []
    attempt_limit = _configured_int(role, "OUTPUT_LIMIT", default_limit)
    attempt_profile = _effective_report_profile(llm_profile, role=role)
    text = ""
    status = "WRITER_EMPTY_OUTPUT"
    for attempt_number in (1, 2):
        if attempt_number == 2 and role != "integrated_report":
            break
        if attempt_number == 2:
            fallback_limit = _configured_int(role, "FALLBACK_OUTPUT_LIMIT", _configured_int(role, "OUTPUT_LIMIT", default_limit))
            attempt_limit = fallback_limit
            attempt_profile = _effective_report_profile(llm_profile, role=role, fallback=True)
        _before_call(attempt_profile, session_id=session_id)
        client = make_client(attempt_profile)
        text, usage = client.generate_text(
            system_prompt=system_prompt,
            payload={"report_context": writer_context},
            max_output_tokens=attempt_limit,
        )
        diagnostics = report_profile_diagnostics(attempt_profile, requested_output_limit=attempt_limit)
        status = _writer_status(
            text,
            usage,
            minimum_chars=minimum_visible_chars,
            requested_output_limit=attempt_limit,
        )
        meta = _response_meta(usage)
        observability = {
            "report_pipeline_version": REPORT_PIPELINE_VERSION,
            "report_type": role,
            "attempt_number": attempt_number,
            "adapter_type": diagnostics["adapter_type"],
            "effective_provider": diagnostics["provider_name"],
            "effective_model": diagnostics["model"],
            "reasoning_effort": attempt_profile.reasoning_effort,
            "configured_reasoning_effort": llm_profile.reasoning_effort,
            "requested_reasoning_effort": attempt_profile.reasoning_effort,
            "requested_thinking_mode": diagnostics["thinking_mode"],
            "configured_output_limit": attempt_limit,
            "requested_output_limit": attempt_limit,
            "prompt_tokens": meta.get("prompt_tokens") or meta.get("input_tokens"),
            "completion_tokens": meta.get("completion_tokens"),
            "output_tokens": meta.get("output_tokens"),
            "reasoning_tokens": meta.get("reasoning_tokens"),
            "visible_output_char_count": len((text or "").strip()),
            "finish_reason": meta.get("finish_reason"),
            "incomplete_reason": meta.get("incomplete_reason"),
            "parse_status": "TEXT",
            "final_attempt_status": status,
        }
        _after_call(
            attempt_profile,
            session_id=session_id,
            project_id=project_id,
            usage=usage,
            project_usage_path=project_usage_path,
            observability=observability,
        )
        attempts.append({**observability, "status": status})
        if status == "PASS" or role != "integrated_report":
            break
    result = {
        "text": (text or "").strip() + ("\n" if text and text.strip() else ""),
        "status": status,
        "failure_type": None if status == "PASS" else status,
        "attempts": attempts,
        "reasoning_effort": attempts[-1].get("reasoning_effort") if attempts else default_reasoning,
        "configured_output_limit": attempts[-1].get("configured_output_limit") if attempts else attempt_limit,
    }
    return result if return_metadata else result["text"]


def run_grounding_validator(
    *, draft_report: str, report_context: dict[str, Any], llm_profile: LLMProfile,
    session_id: str | None = None, project_id: str | None = None,
    prompt_version: str = "1.1",
    scope: RuntimeScope | str | None = None,
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    project_usage_path = _workspace_usage_path(scope=scope, workspace_root=workspace_root, data_root=data_root)
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
    attempt_limit = _configured_int("grounding_validator", "OUTPUT_LIMIT", REPORT_ROLE_DEFAULTS["grounding_validator"][1])
    attempt_profile = _effective_report_profile(llm_profile, role="grounding_validator")
    last_failure: str | None = None
    for attempt_number in (1, 2):
        _before_call(attempt_profile, session_id=session_id)
        client = make_client(attempt_profile)
        diagnostics = report_profile_diagnostics(attempt_profile, requested_output_limit=attempt_limit)
        try:
            result, usage = client.generate_json(
                system_prompt=system_prompt,
                payload={"draft_report": draft_report, "report_context": report_context},
                schema_name="evidence_grounding",
                schema=schema,
                max_output_tokens=attempt_limit,
            )
        except LLMResponseError as exc:
            last_failure = exc.code
            meta = {"parse_status": exc.code, "final_attempt_status": exc.code}
            _after_call(
                attempt_profile,
                session_id=session_id,
                project_id=project_id,
                usage=None,
                project_usage_path=project_usage_path,
                observability={
                    **meta,
                    "report_pipeline_version": REPORT_PIPELINE_VERSION,
                    "report_type": "integrated",
                    "attempt_number": attempt_number,
                    "adapter_type": diagnostics["adapter_type"],
                    "effective_provider": diagnostics["provider_name"],
                    "effective_model": diagnostics["model"],
                    "reasoning_effort": attempt_profile.reasoning_effort,
                    "configured_reasoning_effort": llm_profile.reasoning_effort,
                    "requested_reasoning_effort": attempt_profile.reasoning_effort,
                    "requested_thinking_mode": diagnostics["thinking_mode"],
                    "configured_output_limit": attempt_limit,
                    "requested_output_limit": attempt_limit,
                    "visible_output_char_count": 0,
                },
            )
            if attempt_number == 1 and exc.code in {"GROUNDING_EMPTY_RESPONSE", "GROUNDING_NON_JSON_RESPONSE"}:
                continue
            return {
                "validator_version": "Evidence Grounding Prompt v1.1",
                "overall_status": "FAIL",
                "failure_type": "GROUNDING_VALIDATOR_RESPONSE_ERROR",
                "response_error": exc.code,
                "summary": {"sentences_checked": 0, "supported": 0, "partially_supported": 0, "unsupported": 0, "not_applicable": 0, "critical_errors": 1},
                "issues": [], "required_repairs": [],
            }
        meta = _response_meta(usage)
        _after_call(
            attempt_profile,
            session_id=session_id,
            project_id=project_id,
            usage=usage,
            project_usage_path=project_usage_path,
            observability={
                "report_pipeline_version": REPORT_PIPELINE_VERSION,
                "report_type": "integrated",
                "attempt_number": attempt_number,
                "adapter_type": diagnostics["adapter_type"],
                "effective_provider": diagnostics["provider_name"],
                "effective_model": diagnostics["model"],
                "reasoning_effort": attempt_profile.reasoning_effort,
                "configured_reasoning_effort": llm_profile.reasoning_effort,
                "requested_reasoning_effort": attempt_profile.reasoning_effort,
                "requested_thinking_mode": diagnostics["thinking_mode"],
                "configured_output_limit": attempt_limit,
                "requested_output_limit": attempt_limit,
                "prompt_tokens": meta.get("prompt_tokens") or meta.get("input_tokens"),
                "completion_tokens": meta.get("completion_tokens"),
                "output_tokens": meta.get("output_tokens"),
                "reasoning_tokens": meta.get("reasoning_tokens"),
                "visible_output_char_count": len(json.dumps(result, ensure_ascii=False)),
                "finish_reason": meta.get("finish_reason"),
                "incomplete_reason": meta.get("incomplete_reason"),
                "parse_status": "JSON_VALID",
                "final_attempt_status": "PASS",
            },
        )
        return normalize_grounding_result(result, report_context)
    return {"overall_status": "FAIL", "failure_type": "GROUNDING_VALIDATOR_RESPONSE_ERROR", "response_error": last_failure or "UNKNOWN"}


def run_academic_polish(
    *, report_text: str, report_context: dict[str, Any], llm_profile: LLMProfile,
    session_id: str | None = None, project_id: str | None = None,
    prompt_version: str = "1.1",
    scope: RuntimeScope | str | None = None,
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> str:
    project_usage_path = _workspace_usage_path(scope=scope, workspace_root=workspace_root, data_root=data_root)
    if llm_profile.role != "academic_polish":
        raise ValueError("academic polish requires the academic_polish role")
    prompt_path = PROMPTS_DIR / "reporting" / ("academic_polish_v1.1.md" if prompt_version == "1.1" else "academic_polish.md")
    system_prompt = prompt_path.read_text(encoding="utf-8")
    _before_call(llm_profile, session_id=session_id)
    effective_profile = _effective_report_profile(llm_profile, role="academic_polish")
    client = make_client(effective_profile)
    output_limit = _configured_int("academic_polish", "OUTPUT_LIMIT", REPORT_ROLE_DEFAULTS["academic_polish"][1])
    text, usage = client.generate_text(system_prompt=system_prompt, payload={"report_text": report_text, "report_context": report_context}, max_output_tokens=output_limit)
    meta = _response_meta(usage)
    _after_call(
        effective_profile,
        session_id=session_id,
        project_id=project_id,
        usage=usage,
        project_usage_path=project_usage_path,
        observability={
            "report_pipeline_version": REPORT_PIPELINE_VERSION,
            "report_type": "academic_polish",
            "attempt_number": 1,
            "adapter_type": getattr(client, "adapter_type", effective_profile.provider_type),
            "effective_provider": effective_profile.provider_name,
            "effective_model": effective_profile.model,
            "reasoning_effort": effective_profile.reasoning_effort,
            "configured_reasoning_effort": llm_profile.reasoning_effort,
            "requested_reasoning_effort": effective_profile.reasoning_effort,
            "requested_thinking_mode": getattr(client, "thinking_mode", None),
            "configured_output_limit": output_limit,
            "requested_output_limit": output_limit,
            "prompt_tokens": meta.get("prompt_tokens") or meta.get("input_tokens"),
            "completion_tokens": meta.get("completion_tokens"),
            "output_tokens": meta.get("output_tokens"),
            "reasoning_tokens": meta.get("reasoning_tokens"),
            "visible_output_char_count": len((text or "").strip()),
            "finish_reason": meta.get("finish_reason"),
            "incomplete_reason": meta.get("incomplete_reason"),
            "parse_status": "TEXT",
            "final_attempt_status": "PASS",
        },
    )
    return text.strip() + "\n"
