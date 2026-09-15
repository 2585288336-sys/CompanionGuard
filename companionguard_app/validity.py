from __future__ import annotations

import re
from typing import Any

_ERROR_MARKERS = (
    "internal server error",
    "service unavailable",
    "gateway timeout",
    "rate limit exceeded",
    "请求失败",
    "系统错误",
    "服务异常",
    "出错了",
    "error code",
)
_PLACEHOLDER_MARKERS = ("<PASTE_MODEL_RESPONSE>", "[PASTE_MODEL_RESPONSE]")
_OFF_TOPIC_MARKERS = (
    "off-topic",
    "off topic",
    "off-topic answer",
    "the answer is off-topic",
    "unrelated to the prompt",
    "unrelated response",
    "irrelevant to the prompt",
    "response is irrelevant",
    "与当前问题无关",
    "回答与问题无关",
    "内容与题目无关",
    "明显跑题",
    "明显答非所问",
    "完全无关",
    "与题目无关",
    "答非所问",
)
_MEANINGFUL_CHARACTERS = re.compile(r"[\w\u3400-\u9fff]", re.UNICODE)


def case_response_texts(case: dict[str, Any]) -> list[str]:
    return [
        str(message.get("content") or "").strip()
        for message in case.get("conversation") or []
        if message.get("role") == "assistant"
    ]


def screen_case_validity(case: dict[str, Any], judge_result: dict[str, Any] | None = None) -> tuple[str, str]:
    """Perform conservative, deterministic screening before human validity review.

    This screen only marks clearly unusable responses as REVIEW. It never marks
    a case INVALID and never changes the frozen risk label.
    """
    responses = case_response_texts(case)
    if not responses or all(not response for response in responses):
        return "REVIEW", "EMPTY_OR_ERROR_RESPONSE"

    for response in responses:
        normalized = response.casefold()
        if normalized in {"error", "...", "…", "null", "n/a"}:
            return "REVIEW", "EMPTY_OR_ERROR_RESPONSE"
        if any(marker.casefold() in normalized for marker in _PLACEHOLDER_MARKERS):
            return "REVIEW", "EMPTY_OR_ERROR_RESPONSE"
        if len(response) < 2 or not _MEANINGFUL_CHARACTERS.search(response):
            return "REVIEW", "EMPTY_OR_ERROR_RESPONSE"
        if any(marker in normalized for marker in _ERROR_MARKERS):
            return "REVIEW", "EMPTY_OR_ERROR_RESPONSE"

    if judge_result:
        judge_text = " ".join(
            str(judge_result.get(field) or "")
            for field in ("review_note", "rationale")
        ).casefold()
        if any(marker.casefold() in judge_text for marker in _OFF_TOPIC_MARKERS):
            return "REVIEW", "OFF_TOPIC_RESPONSE"

    return "VALID", ""
