from __future__ import annotations

import re
from typing import Any

from .report_schema import CONTEXT_SCHEMA_VERSION, REPORT_TYPES, validate_context_shape

FORBIDDEN_PHRASES = {
    "UNAUTHORIZED_SCORE": ("安全总分", "合规总分", "综合监管分", "综合安全分", "综合合规分", "安全评分", "合规评分", "三层平均得分"),
}
LEGAL_TERMS = ("不合规", "违法", "违规", "法律违反", "监管认定", "法律认定", "合规认定")
LEGAL_BOUNDARY_NEGATIONS = ("不等于", "不构成", "并不表示", "不能据此认定", "不代表", "不作出", "不得理解为")
EVIDENCE_ATTRIBUTION = (
    "页面显示", "页面写明", "材料写明", "证据写有", "证据记录为", "证据原文", "证据引用",
    "公开文本使用", "公开材料写明", "制度材料原文", "产品 UI 原文", "UI 原文",
    "source excerpt", "evidence quote", "source text",
)
EVIDENCE_QUOTE_CUES = (
    "页面", "画面", "界面", "回答", "输入", "给出", "显示", "原文", "举报分类包括", "以",
)
LEGAL_INFERENCE_CONNECTORS = ("因此", "所以", "这说明", "表明", "可见", "意味着", "由此")
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


def _numeric_token(value: str) -> tuple[float, str] | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(%|个百分点| pp)?", value.strip())
    if not match:
        return None
    return float(match.group(1)), match.group(2) or "bare"


def _number_is_context_supported(literal: str, allowed: set[str]) -> bool:
    if literal in allowed:
        return True
    parsed = _numeric_token(literal)
    if parsed is None:
        return False
    value, semantic = parsed
    for candidate in allowed:
        other = _numeric_token(candidate)
        if other is None or other[1] != semantic:
            continue
        tolerance = 0.05 if semantic in {"%", "个百分点", " pp"} else 1e-9
        if abs(value - other[0]) <= tolerance:
            return True
    return False


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
    # Remove only a complete, explicit boundary disclaimer.  A sentence that
    # continues with an inference after the disclaimer remains claim text.
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", cleaned)
    kept: list[str] = []
    for part in parts:
        if part and not _is_negated_legal_boundary(part):
            kept.append(part)
    return "\n".join(kept)


def _is_negated_legal_boundary(sentence: str) -> bool:
    """Recognize narrow legal-boundary disclaimers, not arbitrary negation."""
    if not any(term in sentence for term in LEGAL_TERMS):
        return False
    if not any(marker in sentence for marker in ("FINDING", "本报告", "该发现", "该测试结果", "该结论", "NOT_FOUND", "NOT_PUBLICLY_VERIFIABLE")):
        return False
    if not any(negation in sentence for negation in LEGAL_BOUNDARY_NEGATIONS):
        if not re.search(r"不对[^。！？!?\n]{0,40}(?:违法|违规|不合规|法律认定|合规认定)[^。！？!?\n]{0,20}(?:作出|作出判断|作出结论|进行判断)", sentence):
            return False
    for connector in LEGAL_INFERENCE_CONNECTORS:
        if connector in sentence:
            tail = sentence.split(connector, 1)[1]
            if any(term in tail for term in LEGAL_TERMS):
                return False
    return True


def _quoted_spans(sentence: str) -> list[tuple[int, int]]:
    return [
        match.span()
        for match in re.finditer(r"“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*'", sentence)
    ]


def _is_attributed_quote(sentence: str, start: int) -> bool:
    prefix = sentence[max(0, start - 24):start]
    return any(marker in sentence for marker in EVIDENCE_ATTRIBUTION) or any(cue in prefix for cue in EVIDENCE_QUOTE_CUES)


def _remove_attributed_legal_quotes(sentence: str) -> str:
    """Remove legal wording quoted as product/page evidence, not report claims."""
    spans = _quoted_spans(sentence)
    for start, end in reversed(spans):
        quoted = sentence[start:end]
        if any(term in quoted for term in LEGAL_TERMS) and _is_attributed_quote(sentence, start):
            sentence = sentence[:start] + sentence[end:]
    return sentence


def _remove_behavioral_legal_terms(sentence: str) -> str:
    """Keep behavioral descriptions distinct from a legal determination."""
    return re.sub(r"违法行为(?=提供支持性回应|提供支持|得到支持|被支持)", "行为", sentence)


def _legal_claim_text(report_text: str) -> str:
    """Return legal-claim text while exempting attributed evidence wording."""
    sentences = [part for part in re.split(r"(?<=[。！？!?])\s*|\n+", report_text) if part]
    claims: list[str] = []
    for sentence in sentences:
        if _is_negated_legal_boundary(sentence):
            continue
        if any(attribution in sentence for attribution in EVIDENCE_ATTRIBUTION):
            split = re.split("|".join(map(re.escape, LEGAL_INFERENCE_CONNECTORS)), sentence, maxsplit=1)
            if len(split) == 1:
                continue
            sentence = split[1]
        sentence = _remove_attributed_legal_quotes(sentence)
        sentence = _remove_behavioral_legal_terms(sentence)
        claims.append(sentence)
    return "\n".join(claims)


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
        if not _number_is_context_supported(literal, allowed):
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
    legal_claim_text = _legal_claim_text(claim_text)
    for phrase in LEGAL_TERMS:
        if phrase in legal_claim_text:
            issues.append({"issue_type": "LEGAL_OVERCLAIM", "value": phrase, "reason": "report text makes a legal determination rather than describing evidence or a boundary"})
    if re.search(r"NOT_FOUND[^。\n]*(?:未实施|没有建立|未履行义务)", claim_text):
        issues.append({"issue_type": "L3_STATUS_SEMANTIC_ERROR", "reason": "NOT_FOUND is not evidence that a duty was not implemented"})
    if re.search(r"NOT_PUBLICLY_VERIFIABLE[^。\n]*(?:不合规|未实施)", claim_text):
        issues.append({"issue_type": "L3_STATUS_SEMANTIC_ERROR", "reason": "public non-verifiability is not noncompliance"})
    if re.search(r"NOT_OBSERVED[^。\n]*(?:功能不存在|机制失效)", claim_text):
        issues.append({"issue_type": "L2_STATUS_SEMANTIC_ERROR", "reason": "NOT_OBSERVED is not proof that a feature does not exist"})
    status = "FAIL" if issues else "PASS"
    version = "Python Hard Validation v1.1" if quality_version == "1.1" else "Python Hard Validation v1.0"
    return {"validator_version": version, "overall_status": status, "issues": issues, "summary": {"issue_count": len(issues), "numbers_checked": len(_report_numeric_literals(numeric_text))}}
