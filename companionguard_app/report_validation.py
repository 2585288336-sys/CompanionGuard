from __future__ import annotations

import re
from typing import Any

from .report_schema import CONTEXT_SCHEMA_VERSION, REPORT_TYPES, validate_context_shape

FORBIDDEN_PHRASES = {
    "UNAUTHORIZED_SCORE": ("安全总分", "合规总分", "综合监管分", "综合安全分", "综合合规分", "安全评分", "合规评分", "三层平均得分"),
}
LEGAL_SUBJECTS = ("产品", "企业", "公司", "平台", "服务商", "该产品", "该企业", "该公司", "该平台", "该服务商")
LEGAL_PREDICATE_FAMILIES = {
    "LEGAL_STATUS": ("违法违规", "不合规", "违法", "违规"),
    "LEGAL_VIOLATION": (r"违反(?:[^。！？!?，,；;\n]{0,18}(?:法律|法规|规定|监管要求))",),
    "COMPLIANCE_DETERMINATION": ("不符合监管要求",),
    "LEGAL_DUTY_DETERMINATION": ("未履行法定义务", "未履行法律义务"),
}
LEGAL_BOUNDARY_MARKERS = ("不等于", "不构成", "并不表示", "不能据此认定", "不代表", "不作出", "不得理解为", "并非", "不认定", "不能认定", "不对")
UI_ATTRIBUTION_MARKERS = (
    "页面显示", "页面出现", "页面写明", "系统提示", "界面提示", "返回", "提示为", "标记为", "截图显示",
    "页面", "画面", "界面", "回答", "输入", "给出", "显示", "原文", "证据显示", "记录显示",
)
DOCUMENT_ATTRIBUTION_MARKERS = (
    "用户协议", "隐私政策", "公开材料", "公开文本", "条款", "制度", "举报分类", "证据记录", "证据原文",
    "材料写明", "证据写有", "证据引用", "制度材料原文", "产品 UI 原文", "UI 原文",
    "source excerpt", "evidence quote", "source text",
)
LEGAL_INFERENCE_CONNECTORS = ("因此", "所以", "这说明", "表明", "可见", "意味着", "由此")
L2_BAD = ("功能不存在", "机制失效")
L3_BAD = ("未实施", "没有建立", "未履行义务")

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


def _number_is_context_supported(literal: str, allowed: set[str]) -> bool:
    return literal in allowed


def _numeric_sentence_excerpt(report_text: str, literal: str) -> str:
    for sentence in re.split(r"(?<=[。！？!?])\s*|\n+", report_text):
        if literal in sentence:
            return sentence.strip()
    return report_text.strip()


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


def _quoted_spans(sentence: str) -> list[tuple[int, int]]:
    return [
        match.span()
        for match in re.finditer(r"“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|\"[^\"]*\"|'[^']*'", sentence)
    ]


def _mask_spans(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(start, end):
            if chars[index] not in "。！？!?\n":
                chars[index] = " "
    return "".join(chars)


def _attribution_spans(sentence: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for marker in (*UI_ATTRIBUTION_MARKERS, *DOCUMENT_ATTRIBUTION_MARKERS):
        start = 0
        while True:
            marker_start = sentence.find(marker, start)
            if marker_start < 0:
                break
            end_candidates = [len(sentence)]
            for boundary in ("。", "！", "？", "!", "?", "\n", "；", ";", "，", ","):
                position = sentence.find(boundary, marker_start + len(marker))
                if position >= 0:
                    end_candidates.append(position + 1)
            for connector in LEGAL_INFERENCE_CONNECTORS:
                position = sentence.find(connector, marker_start + len(marker))
                if position >= 0:
                    end_candidates.append(position)
            spans.append((marker_start, min(end_candidates)))
            start = marker_start + len(marker)
    return spans


def _boundary_spans(sentence: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    boundary_pattern = "|".join(map(re.escape, LEGAL_BOUNDARY_MARKERS))
    for match in re.finditer(rf"(?:{boundary_pattern})", sentence):
        end_candidates = [len(sentence)]
        for connector in LEGAL_INFERENCE_CONNECTORS:
            position = sentence.find(connector, match.end())
            if position >= 0:
                end_candidates.append(position)
        for boundary in ("。", "！", "？", "!", "?", "\n", "；", ";", "，", ","):
            position = sentence.find(boundary, match.end())
            if position >= 0:
                end_candidates.append(position + 1)
        spans.append((match.start(), min(end_candidates)))
    for match in re.finditer(r"(?:不构成|不生成|不提供|不使用|不作出)[^。！？!?\n]{0,40}(?:安全|合规)(?:总分|评分|分)", sentence):
        spans.append(match.span())
    return spans


def _protected_semantic_spans(sentence: str) -> list[tuple[int, int]]:
    """Return quotation, attribution, and explicit-boundary spans to exclude from claims."""
    return _quoted_spans(sentence) + _attribution_spans(sentence) + _boundary_spans(sentence)


def _claim_text_without_boundary_disclaimers(report_text: str) -> str:
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", report_text)
    return "\n".join(_mask_spans(part, _boundary_spans(part)) for part in parts if part)


def _subject_pattern(context: dict[str, Any]) -> str:
    subjects = set(LEGAL_SUBJECTS)
    for product in (context.get("products") or {}):
        if str(product).strip():
            subjects.add(str(product).strip())
    for item in context.get("product_layer_coverage") or []:
        for key in ("product_id", "display_name"):
            value = str(item.get(key) or "").strip()
            if value:
                subjects.add(value)
    return "|".join(re.escape(subject) for subject in sorted(subjects, key=len, reverse=True))


def _legal_claim_patterns(context: dict[str, Any]) -> tuple[tuple[str, re.Pattern[str]], ...]:
    subject = _subject_pattern(context)
    def predicate_pattern(category: str) -> str:
        return "(?:" + "|".join(LEGAL_PREDICATE_FAMILIES[category]) + ")"

    status_predicates = predicate_pattern("LEGAL_STATUS")
    violation_predicates = predicate_pattern("LEGAL_VIOLATION")
    compliance_predicates = predicate_pattern("COMPLIANCE_DETERMINATION")
    duty_predicates = predicate_pattern("LEGAL_DUTY_DETERMINATION")
    return (
        (
            "LEGAL_STATUS",
            re.compile(
                rf"(?P<subject>{subject})\s*(?:(?:存在|属于|是|为|构成|表现为|被认定为|认定为)\s*)?"
                rf"(?P<predicate>{status_predicates})(?!内容|信息|分类|提示|情形|标签)"
            ),
        ),
        (
            "LEGAL_VIOLATION",
            re.compile(rf"(?P<subject>{subject})\s*(?P<predicate>{violation_predicates})"),
        ),
        (
            "COMPLIANCE_DETERMINATION",
            re.compile(rf"(?P<subject>{subject})\s*(?P<predicate>{compliance_predicates})"),
        ),
        (
            "LEGAL_DUTY_DETERMINATION",
            re.compile(rf"(?P<subject>{subject})\s*(?P<predicate>{duty_predicates})"),
        ),
    )


def _detect_legal_claims(report_text: str, context: dict[str, Any]) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    for sentence in (part for part in re.split(r"(?<=[。！？!?])\s*|\n+", report_text) if part.strip()):
        protected = _protected_semantic_spans(sentence)
        masked = _mask_spans(sentence, protected)
        for category, pattern in _legal_claim_patterns(context):
            for match in pattern.finditer(masked):
                claims.append({
                    "value": match.group("predicate"),
                    "sentence_excerpt": sentence.strip(),
                    "detected_subject": match.group("subject"),
                    "detected_predicate": match.group("predicate"),
                    "predicate_category": category,
                })
    return claims


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
            issues.append({
                "issue_type": "NUMBER_MISMATCH",
                "value": literal,
                "sentence_excerpt": _numeric_sentence_excerpt(report_text, literal),
                "reason": "number is not present in report_context with exact display provenance",
            })
    if re.search(r"(?:增加|减少|高于|低于)\s*\d+(?:\.\d+)?\s*个百分点", report_text):
        comparison_text = " ".join(_context_strings(context.get("comparisons", {})))
        if "个百分点" not in comparison_text:
            issues.append({"issue_type": "UNAUTHORIZED_CALCULATION", "reason": "comparison gap was not supplied as a display field in report_context"})
    claim_text = _claim_text_without_boundary_disclaimers(report_text)
    for issue_type, phrases in FORBIDDEN_PHRASES.items():
        for phrase in phrases:
            if phrase in claim_text:
                issues.append({"issue_type": issue_type, "value": phrase, "reason": "forbidden legal or unified-score claim"})
    for claim in _detect_legal_claims(report_text, context):
        issues.append({
            "issue_type": "LEGAL_OVERCLAIM",
            "value": claim["value"],
            "sentence_excerpt": claim["sentence_excerpt"],
            "detected_subject": claim["detected_subject"],
            "detected_predicate": claim["detected_predicate"],
            "predicate_category": claim["predicate_category"],
            "reason": "report text asserts a legal conclusion about the detected subject",
        })
    if re.search(r"NOT_FOUND[^。\n]*(?:未实施|没有建立|未履行义务)", claim_text):
        issues.append({"issue_type": "L3_STATUS_SEMANTIC_ERROR", "reason": "NOT_FOUND is not evidence that a duty was not implemented"})
    if re.search(r"NOT_PUBLICLY_VERIFIABLE[^。\n]*(?:不合规|未实施)", claim_text):
        issues.append({"issue_type": "L3_STATUS_SEMANTIC_ERROR", "reason": "public non-verifiability is not noncompliance"})
    if re.search(r"NOT_OBSERVED[^。\n]*(?:功能不存在|机制失效)", claim_text):
        issues.append({"issue_type": "L2_STATUS_SEMANTIC_ERROR", "reason": "NOT_OBSERVED is not proof that a feature does not exist"})
    status = "FAIL" if issues else "PASS"
    version = "Python Hard Validation v1.1" if quality_version == "1.1" else "Python Hard Validation v1.0"
    return {"validator_version": version, "overall_status": status, "issues": issues, "summary": {"issue_count": len(issues), "numbers_checked": len(_report_numeric_literals(numeric_text))}}
