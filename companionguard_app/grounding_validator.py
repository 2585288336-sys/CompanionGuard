from __future__ import annotations

import re
from typing import Any

ISSUE_TYPES = {"NUMBER_MISMATCH", "UNAUTHORIZED_CALCULATION", "LEGAL_OVERCLAIM", "L2_STATUS_SEMANTIC_ERROR", "L3_STATUS_SEMANTIC_ERROR", "UNAUTHORIZED_SCORE", "EVIDENCE_LAYER_CONFUSION", "REPRESENTATIVE_CASE_OVERREACH", "RAW_JUDGE_USED_AS_FINAL"}


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
