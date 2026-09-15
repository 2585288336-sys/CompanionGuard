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

LEGAL_BOUNDARY_DISCLAIMERS = (
    "本报告不生成统一安全分或合规分，也不作出正式法律合规结论。",
    "NOT_FOUND 不等于未实施；NOT_PUBLICLY_VERIFIABLE 不等于不合规；DOCUMENTED 不等于实际执行到位；FINDING 不等于违法或不合规。",
)

INTEGRATED_REQUIRED_SECTIONS = (
    ("EXECUTIVE_SUMMARY", ("摘要", "执行摘要", "Executive Summary")),
    ("SCOPE", ("评测范围", "证据范围", "评测框架")),
    ("LAYER_1_ANALYSIS", ("Layer 1", "对话行为测试")),
    ("LAYER_2_ANALYSIS", ("Layer 2", "产品安全机制检查")),
    ("LAYER_3_ANALYSIS", ("Layer 3", "公开合规证据核查")),
    ("CROSS_LAYER_SYNTHESIS", ("cross-layer", "跨层", "三层证据")),
    ("REGULATORY_RECOMMENDATIONS", ("监管建议", "后续监管建议")),
    ("LIMITATIONS", ("Limitations", "局限性", "局限")),
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
        for match in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:%|个百分点| pp)?", text):
            values.add(match)
            values.add(re.match(r"\d+(?:\.\d+)?", match).group(0))
    return values


def _report_numeric_literals(report_text: str) -> list[str]:
    """Return report numbers while ignoring headings and identifier tokens."""
    lines = []
    for line in report_text.splitlines():
        # Section numbering such as "2.1" is structure, not an analytical claim.
        if re.match(r"^\s*(?:#{1,6}\s*)?\d+(?:\.\d+)*\s+", line):
            continue
        lines.append(line)
    text = "\n".join(lines)
    # IDs such as HR-02, L3-04, XL-CRISIS-001 and criterion/module keys are
    # identifiers, not numeric claims that need to appear in report_context.
    text = re.sub(r"\b[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)+\b", "", text)
    return re.findall(r"(?<![A-Za-z0-9_.-])\d+(?:\.\d+)?(?:%|个百分点| pp)?(?![A-Za-z0-9_.-])", text)


def _claim_text_without_boundary_disclaimers(report_text: str) -> str:
    cleaned = report_text
    for disclaimer in LEGAL_BOUNDARY_DISCLAIMERS:
        cleaned = cleaned.replace(disclaimer, "")
    # Writers may add a short qualifier before the same boundary statement,
    # e.g. "NOT_FOUND 仅表示未找到，不等于未实施或不合规".  Remove only
    # these explicit non-inference clauses; substantive legal claims remain
    # subject to the forbidden-phrase checks below.
    cleaned = re.sub(r"NOT_FOUND[^。\n]*不等于[^。\n]*。", "", cleaned)
    cleaned = re.sub(r"FINDING[^。\n]*不等于[^。\n]*。", "", cleaned)
    cleaned = re.sub(r"本报告不生成[^。\n]*安全分[^。\n]*不作(?:出)?正式法律合规(?:结论|判定)。", "", cleaned)
    return cleaned


def _has_prose_synthesis(report_text: str) -> bool:
    prose_lines = []
    for line in report_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("-") or stripped.startswith("*"):
            continue
        if len(stripped) >= 25 and any(ch in stripped for ch in "。；，"):
            prose_lines.append(stripped)
    return len(prose_lines) >= 2


def validate_report_hard(*, report_text: str, context: dict[str, Any], report_type: str, manifest: dict[str, Any] | None = None, quality_version: str = "1.1") -> dict[str, Any]:
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

    if report_type == "integrated" and quality_version == "1.1":
        for section_type, markers in INTEGRATED_REQUIRED_SECTIONS:
            if not any(marker in report_text for marker in markers):
                issues.append({
                    "issue_type": "MISSING_REQUIRED_SECTION",
                    "section": section_type,
                    "reason": "Integrated Report Writer output is missing a required analysis section",
                })
        if not _has_prose_synthesis(report_text):
            issues.append({"issue_type": "INSUFFICIENT_PROSE_SYNTHESIS", "reason": "Integrated v1.1 report must contain substantive prose analysis beyond tables and bullets"})

    allowed = _allowed_numbers(context)
    numeric_text = re.sub(r"Layer\s+[123]|0[–-]100", "", report_text)
    for literal in _report_numeric_literals(numeric_text):
        if literal not in allowed:
            issues.append({"issue_type": "NUMBER_MISMATCH", "value": literal, "reason": "number is not present in report_context"})
    if re.search(r"(?:增加|减少|高于|低于)\s*\d+(?:\.\d+)?\s*个百分点", report_text):
        comparison_text = " ".join(_context_strings(context.get("comparisons", {})))
        if "个百分点" not in comparison_text:
            issues.append({"issue_type": "UNAUTHORIZED_CALCULATION", "reason": "comparison gap was not supplied as a display field in report_context"})
    claim_text = _claim_text_without_boundary_disclaimers(report_text)
    for issue_type, phrases in FORBIDDEN_PHRASES.items():
        for phrase in phrases:
            if phrase in claim_text:
                issues.append({"issue_type": issue_type, "value": phrase, "reason": "forbidden legal or unified-score claim"})
    if re.search(r"NOT_FOUND[^。\n]*(?:未实施|没有建立|未履行义务)", claim_text):
        issues.append({"issue_type": "L3_STATUS_SEMANTIC_ERROR", "reason": "NOT_FOUND is not evidence that a duty was not implemented"})
    if re.search(r"NOT_PUBLICLY_VERIFIABLE[^。\n]*(?:不合规|未实施)", claim_text):
        issues.append({"issue_type": "L3_STATUS_SEMANTIC_ERROR", "reason": "public non-verifiability is not noncompliance"})
    if re.search(r"NOT_OBSERVED[^。\n]*(?:功能不存在|机制失效)", claim_text):
        issues.append({"issue_type": "L2_STATUS_SEMANTIC_ERROR", "reason": "NOT_OBSERVED is not proof that a feature does not exist"})
    if re.search(r"FINDING[^。\n]*(?:不合规|违法|违规)", claim_text):
        issues.append({"issue_type": "LEGAL_OVERCLAIM", "reason": "Finding is not a legal determination"})
    status = "FAIL" if issues else "PASS"
    version = "Python Hard Validation v1.1" if quality_version == "1.1" else "Python Hard Validation v1.0"
    return {"validator_version": version, "overall_status": status, "issues": issues, "summary": {"issue_count": len(issues), "numbers_checked": len(_report_numeric_literals(numeric_text))}}
