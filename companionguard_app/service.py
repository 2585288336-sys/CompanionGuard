from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from companionguard_judge.pipeline import dry_run, judge_case, load_criteria

from .config import CRITERIA_DIR
from .storage import append_judge_result, completed_case_ids


def criteria_index(criteria_dir: Path = CRITERIA_DIR) -> dict[str, dict[str, Any]]:
    return load_criteria(criteria_dir)


def make_deepseek_client(api_key: str | None = None):
    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("缺少DeepSeek API Key。")
    from companionguard_judge.client import DeepSeekJudgeClient
    return DeepSeekJudgeClient(
        key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        reasoning_effort=os.environ.get("DEEPSEEK_REASONING_EFFORT", "none"),
        temperature=float(os.environ.get("DEEPSEEK_TEMPERATURE", "0")),
    )


def run_single_case(
    *,
    case: dict[str, Any],
    criteria: dict[str, dict[str, Any]],
    api_key: str | None = None,
    persist: bool = True,
    judge_path: Path | None = None,
) -> dict[str, Any]:
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
    client = make_deepseek_client(api_key)
    row = judge_case(client, criterion, case, semantic_retries=1)
    if persist:
        append_judge_result(row, target_judge_path) if target_judge_path is not None else append_judge_result(row)
    return row


def run_batch_cases(
    *,
    cases: list[dict[str, Any]],
    criteria: dict[str, dict[str, Any]],
    api_key: str | None = None,
    skip_completed: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
    judge_path: Path | None = None,
) -> list[dict[str, Any]]:
    ids = [c.get("case_id") for c in cases]
    duplicates = sorted({x for x in ids if x and ids.count(x) > 1})
    if duplicates:
        raise ValueError("批量输入存在重复case_id: " + ", ".join(duplicates))
    errors = dry_run(cases, criteria)
    if errors:
        raise ValueError("输入校验失败:\n" + "\n".join(errors))

    done = (completed_case_ids(judge_path) if judge_path is not None else completed_case_ids()) if skip_completed else set()
    queue = [c for c in cases if c.get("case_id") not in done]
    client = make_deepseek_client(api_key)
    results = []
    total = len(queue)
    for index, case in enumerate(queue, 1):
        criterion = criteria[case["criterion_id"]]
        row = judge_case(client, criterion, case, semantic_retries=1)
        append_judge_result(row, judge_path) if judge_path is not None else append_judge_result(row)
        results.append(row)
        if progress:
            progress(index, total, case["case_id"])
    return results


def run_documentary_assist(
    *,
    check: dict[str, Any],
    source_text: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Optional Layer 3 evidence extraction assist. Human review remains authoritative."""
    if not source_text.strip():
        raise ValueError("Source text cannot be empty.")
    client = make_deepseek_client(api_key)
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
    payload = {"check": check, "source_text": source_text}
    result, _ = client.judge(
        system_prompt=system_prompt,
        payload=payload,
        schema_name="layer3_public_evidence_assist",
        schema=schema,
    )
    return result
