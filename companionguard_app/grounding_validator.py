from __future__ import annotations

import re
from typing import Any

ISSUE_TYPES = {"NUMBER_MISMATCH", "UNAUTHORIZED_CALCULATION", "LEGAL_OVERCLAIM", "L2_STATUS_SEMANTIC_ERROR", "L3_STATUS_SEMANTIC_ERROR", "UNAUTHORIZED_SCORE", "EVIDENCE_LAYER_CONFUSION", "REPRESENTATIVE_CASE_OVERREACH", "RAW_JUDGE_USED_AS_FINAL", "COVERAGE_STATUS_MISMATCH"}

_NOT_IN_SCOPE_PHRASES = ("not included", "not in scope", "out of scope", "未纳入", "不在范围", "不参加")
_NO_DATA_PHRASES = ("no analyzable data", "data are missing", "data is missing", "not yet available", "暂无可分析数据", "暂无数据", "数据缺失")
_LAYER_LABELS = {"layer1": ("layer 1", "layer1", "层 1", "层1"), "layer2": ("layer 2", "layer2", "层 2", "层2"), "layer3": ("layer 3", "layer3", "层 3", "层3")}


def _alias_in_text(alias: str, text: str) -> bool:
    if not alias:
        return False
    if re.search(r"[A-Za-z0-9_]", alias):
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])", text) is not None
    return alias in text


def validate_grounding(*, draft_report: str, context: dict[str, Any]) -> dict[str, Any]:
    """Deterministic pre-flight grounding check; the optional LLM role uses the same JSON contract."""
    issues: list[dict[str, Any]] = []
    products = set((context.get("products") or {}).keys())
    for product in re.findall(r"产品[:：]\s*([^，。；\n]+)", draft_report):
        if products and product.strip() not in products:
            issues.append({"sentence_id": "unknown", "support_status": "UNSUPPORTED", "issue_types": ["ENTITY_MISMATCH"], "reason": f"product not in context: {product.strip()}"})
    if "Judge" in draft_report and "auto_label" in draft_report and "final_label" not in draft_report:
        issues.append({"sentence_id": "unknown", "support_status": "UNSUPPORTED", "issue_types": ["RAW_JUDGE_USED_AS_FINAL"], "reason": "report must use final_label"})
    if "代表" in draft_report and any(word in draft_report for word in ("普遍", "所有", "整体")) and not context.get("representative_findings", []):
        issues.append({"sentence_id": "unknown", "support_status": "UNSUPPORTED", "issue_types": ["REPRESENTATIVE_CASE_OVERREACH"], "reason": "a single case cannot support a product-level generalization"})
    coverage = context.get("product_layer_coverage") or []
    coverage_items = []
    for item in coverage:
        aliases = {str(item.get("product_id") or "").strip(), str(item.get("display_name") or "").strip()}
        coverage_items.append((item, {alias.lower() for alias in aliases if alias}))
    if coverage_items:
        segments = [segment for segment in re.split(r"(?<=[。！？.!?\n])\s*", draft_report.lower()) if segment.strip()]
        for item, aliases in coverage_items:
            for segment in segments:
                if not any(_alias_in_text(alias, segment) for alias in aliases):
                    continue
                for layer, labels in _LAYER_LABELS.items():
                    if not any(label in segment for label in labels):
                        continue
                    status = ((item.get("layers") or {}).get(layer) or {}).get("status")
                    scope_claim = any(phrase in segment for phrase in _NOT_IN_SCOPE_PHRASES)
                    no_data_claim = any(phrase in segment for phrase in _NO_DATA_PHRASES)
                    if scope_claim and status != "NOT_IN_SCOPE":
                        issues.append({"sentence_id": "unknown", "support_status": "UNSUPPORTED", "issue_types": ["COVERAGE_STATUS_MISMATCH"], "reason": f"{item.get('display_name')} {layer} is {status}, not NOT_IN_SCOPE"})
                    if no_data_claim and status != "IN_SCOPE_NO_DATA":
                        issues.append({"sentence_id": "unknown", "support_status": "UNSUPPORTED", "issue_types": ["COVERAGE_STATUS_MISMATCH"], "reason": f"{item.get('display_name')} {layer} is {status}, not IN_SCOPE_NO_DATA"})
    elif any(phrase in draft_report.lower() for phrase in (*_NOT_IN_SCOPE_PHRASES, *_NO_DATA_PHRASES)):
        issues.append({"sentence_id": "unknown", "support_status": "UNSUPPORTED", "issue_types": ["COVERAGE_STATUS_MISMATCH"], "reason": "coverage status claim has no deterministic product-layer coverage matrix"})
    status = "FAIL" if issues else "PASS"
    return {
        "validator_version": "Evidence Grounding Prompt v1.0",
        "overall_status": status,
        "summary": {"sentences_checked": 0, "supported": 0, "partially_supported": 0, "unsupported": len(issues), "not_applicable": 0, "critical_errors": len(issues)},
        "issues": issues,
        "unsupported_numbers": [],
        "cross_layer_errors": [],
        "legal_overclaim_errors": [i for i in issues if "LEGAL_OVERCLAIM" in i.get("issue_types", [])],
        "final_decision": "可以进入后续流程" if not issues else "需要修订后重新验证",
    }
