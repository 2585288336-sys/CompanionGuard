from __future__ import annotations

import re
from typing import Any

from .report_schema import CONTEXT_SCHEMA_VERSION, REPORT_TYPES, validate_context_shape

FORBIDDEN_PHRASES = {
    "UNAUTHORIZED_SCORE": ("安全总分", "合规总分", "综合监管分", "综合安全分", "综合合规分", "安全评分", "合规评分", "三层平均得分"),
    "LEGAL_OVERCLAIM": ("不合规", "违法", "违规", "法律违反", "监管认定"),
}
L2_BAD = ("功能不存在", "机制失效")
L3_BAD = ("未实施", "没有建立", "未履行义务")

INTEGRATED_REQUIRED_SECTIONS = (
    ("LAYER_1_ANALYSIS", ("Layer 1", "对话行为测试")),
    ("LAYER_2_ANALYSIS", ("Layer 2", "产品安全机制检查")),
    ("LAYER_3_ANALYSIS", ("Layer 3", "公开合规证据核查")),
    ("CROSS_LAYER_SYNTHESIS", ("cross-layer", "跨层", "三层证据")),
    ("REGULATORY_ATTENTION", ("监管关注点", "监管关注")),
    ("LIMITATIONS", ("Limitations", "局限性")),
)


def _context_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_context_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_context_strings(item))
        return result
    return [str(value)] if value is not None else []


def _allowed_numbers(context: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for text in _context_strings(context):
        values.update(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:%|个百分点| pp)?", text))
    return values


def validate_report_hard(*, report_text: str, context: dict[str, Any], report_type: str, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    context_errors = validate_context_shape(context)
    if report_type not in REPORT_TYPES:
        issues.append({"issue_type": "REPORT_TYPE_MISMATCH", "reason": report_type})
    if context_errors:
        issues.extend({"issue_type": "SCHEMA_ERROR", "reason": error} for error in context_errors)
    if manifest:
        if manifest.get("context_schema_version") != CONTEXT_SCHEMA_VERSION:
            issues.append({"issue_type": "SCHEMA_VERSION_MISMATCH", "reason": "manifest/context version mismatch"})
        if manifest.get("report_type") != report_type:
            issues.append({"issue_type": "REPORT_TYPE_MISMATCH", "reason": "manifest/report type mismatch"})

    if report_type == "integrated":
        for section_type, markers in INTEGRATED_REQUIRED_SECTIONS:
            if not any(marker in report_text for marker in markers):
                issues.append({
                    "issue_type": "MISSING_REQUIRED_SECTION",
                    "section": section_type,
                    "reason": "Integrated Report Writer output is missing a required analysis section",
                })

    allowed = _allowed_numbers(context)
    numeric_text = re.sub(r"Layer\s+[123]|0[–-]100", "", report_text)
    for literal in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:%|个百分点| pp)?", numeric_text):
        if literal not in allowed:
            issues.append({"issue_type": "NUMBER_MISMATCH", "value": literal, "reason": "number is not present in report_context"})
    if re.search(r"(?:增加|减少|高于|低于)\s*\d+(?:\.\d+)?\s*个百分点", report_text):
        comparison_text = " ".join(_context_strings(context.get("comparisons", {})))
        if "个百分点" not in comparison_text:
            issues.append({"issue_type": "UNAUTHORIZED_CALCULATION", "reason": "comparison gap was not supplied as a display field in report_context"})
    for issue_type, phrases in FORBIDDEN_PHRASES.items():
        for phrase in phrases:
            if phrase in report_text:
                issues.append({"issue_type": issue_type, "value": phrase, "reason": "forbidden legal or unified-score claim"})
    if "NOT_FOUND" in report_text and any(p in report_text for p in L3_BAD):
        issues.append({"issue_type": "L3_STATUS_SEMANTIC_ERROR", "reason": "NOT_FOUND is not evidence that a duty was not implemented"})
    if "NOT_PUBLICLY_VERIFIABLE" in report_text and any(p in report_text for p in ("不合规", "未实施")):
        issues.append({"issue_type": "L3_STATUS_SEMANTIC_ERROR", "reason": "public non-verifiability is not noncompliance"})
    if "NOT_OBSERVED" in report_text and any(p in report_text for p in L2_BAD):
        issues.append({"issue_type": "L2_STATUS_SEMANTIC_ERROR", "reason": "NOT_OBSERVED is not proof that a feature does not exist"})
    if "FINDING" in report_text and any(p in report_text for p in ("不合规", "违法", "违规")):
        issues.append({"issue_type": "LEGAL_OVERCLAIM", "reason": "Finding is not a legal determination"})
    status = "FAIL" if issues else "PASS"
    return {"validator_version": "Python Hard Validation v1.0", "overall_status": status, "issues": issues, "summary": {"issue_count": len(issues), "numbers_checked": len(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:%|个百分点| pp)?", numeric_text))}}
