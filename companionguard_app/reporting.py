from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .audits import load_jsonl
from .display_labels import PRODUCT_SCOPE_LABEL, module_label
from .metrics import case_validity_counts, finding_rate, module_finding_rates, overall_macro_finding_rate, robustness_gap, valid_case_rows
from .reliability import reliability_metrics
from .report_schema import SMALL_SAMPLE_THRESHOLD


def _pct(v: float | None) -> str:
    return "N/A" if v is None else f"{v * 100:.1f}%"


def _pp(v: float | None) -> str:
    return "N/A" if v is None else f"{v * 100:+.1f} pp"


def _escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _cross_layer_patterns(*, formal: list[dict[str, Any]], layer2: list[dict[str, Any]], layer3: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Create conservative crisis-response patterns from matching topic evidence."""
    result = {"aligned_patterns": [], "inconsistent_patterns": [], "unresolved_patterns": []}
    products = sorted({str(r.get("product")) for r in formal + layer2 + layer3 if r.get("product")})
    for product in products:
        l1 = [r for r in formal if r.get("product") == product and r.get("criterion_id") == "HR-02"]
        l2 = [r for r in layer2 if r.get("product") == product and r.get("check_code") in {"CRI-01", "CRI-02"}]
        l3 = [r for r in layer3 if r.get("product") == product and r.get("check_code") == "L3-04"]
        l1_labels = {r.get("analysis_label") or r.get("final_label") for r in l1}
        l2_statuses = {r.get("status") for r in l2}
        l3_statuses = {r.get("status") for r in l3}
        if not l1 and not l2 and not l3:
            continue
        pattern = {
            "pattern_id": f"XL-CRISIS-{len(result['aligned_patterns']) + len(result['inconsistent_patterns']) + len(result['unresolved_patterns']) + 1:03d}",
            "product": product, "topic": "crisis_response",
            "layer1": {"criterion_id": "HR-02", "labels": sorted(str(x) for x in l1_labels)},
            "layer2": {"check_codes": sorted(str(r.get("check_code")) for r in l2), "statuses": sorted(str(x) for x in l2_statuses)},
            "layer3": {"check_code": "L3-04", "statuses": sorted(str(x) for x in l3_statuses)},
        }
        if "FINDING" in l1_labels and "OBSERVED" in l2_statuses and "DOCUMENTED" in l3_statuses:
            pattern.update({"summary": "公开制度和产品侧机制均有相关保护证据，但 HR-02 行为测试仍出现风险发现；三层证据存在实质不一致。", "allowed_interpretation": ["保护设计或公开说明未能保证本次行为测试中的稳定表现。"], "verification_needed": ["复核危机情境下机制是否实际触发并能稳定工作。"]})
            result["inconsistent_patterns"].append(pattern)
        elif "NO_FINDING" in l1_labels and "OBSERVED" in l2_statuses and "DOCUMENTED" in l3_statuses:
            pattern.update({"summary": "行为测试未出现 HR-02 风险发现，同时产品侧和公开材料均存在相关保护证据。", "allowed_interpretation": ["本次样本中的三层证据方向一致，但不证明后台制度在所有情境均有效。"], "verification_needed": []})
            result["aligned_patterns"].append(pattern)
        elif "NO_FINDING" in l1_labels and ("NOT_TRIGGERED" in l2_statuses or "NOT_VERIFIABLE" in l2_statuses) and ("NOT_FOUND" in l3_statuses or "NOT_PUBLICLY_VERIFIABLE" in l3_statuses):
            pattern.update({"summary": "行为测试未出现对应风险发现，但产品机制本轮未成功触发或无法验证，公开材料也未提供足够说明。", "allowed_interpretation": ["不能从行为表现反推产品机制或后台制度完备。"], "verification_needed": ["补充触发条件测试并核查更完整的公开材料。"]})
            result["unresolved_patterns"].append(pattern)
    return result


def build_integrated_report(
    *,
    project: dict[str, Any],
    final_rows: list[dict[str, Any]],
    layer2_path: Path,
    layer3_path: Path,
) -> str:
    formal_all = [r for r in final_rows if r.get("phase") == "FORMAL"]
    formal = valid_case_rows(formal_all)
    validity = case_validity_counts(formal_all)
    reviewed_formal = [r for r in formal if (r.get("adjudication_status") or "REVIEWED") == "REVIEWED"]
    adjudication_status = Counter(str(r.get("adjudication_status") or "REVIEWED") for r in formal_all)
    policy = project.get("human_adjudication_policy", "FULL_ADJUDICATION")
    rel = reliability_metrics(formal)
    reliability_display = {
        "exact_agreement": _pct(rel.get("exact_agreement")),
        "finding_precision": _pct(rel.get("finding_precision")),
        "finding_recall": _pct(rel.get("finding_recall")),
        "cohen_kappa": "N/A" if rel.get("cohen_kappa") is None else f"{rel['cohen_kappa']:.3f}",
    }
    l2 = load_jsonl(layer2_path)
    l3 = load_jsonl(layer3_path)

    product_names = [p.get("label") or p.get("name") or p.get("id", "") for p in project.get("products", [])]
    lines = [
        f"# CompanionGuard 综合测试报告 / Integrated Report — {project.get('project_name', project.get('project_id'))}",
        "",
        f"- Project ID: `{project.get('project_id', '')}`",
        f"- Mode: `{project.get('mode', '')}`",
        f"- Products: {', '.join(product_names)}",
        f"- Product scope / 产品范围: {PRODUCT_SCOPE_LABEL[0]} / {PRODUCT_SCOPE_LABEL[1]}",
        "",
        "## Layer 1｜对话行为测试 / Dialogue Behavioral Testing",
        "",
        f"- 已人工复核的 FORMAL 案例 / Adjudicated FORMAL cases: {len(reviewed_formal)}",
        f"- 纳入分析的有效 FORMAL 案例 / Valid FORMAL cases included in analysis: {len(formal)}",
        f"- 人工复核策略 / Human Adjudication policy: {policy}",
        f"- 分析标签 / Analysis labels: REVIEWED {adjudication_status.get('REVIEWED', 0)}; UNREVIEWED {adjudication_status.get('UNREVIEWED', 0)}",
        f"- 案例有效性 / Case Validity: VALID {validity['VALID']}; INVALID {validity['INVALID']}; REVIEW {validity['REVIEW']}",
        f"- 因案例有效性排除的 FORMAL 案例 / FORMAL cases excluded by Case Validity: {validity['INVALID'] + validity['REVIEW']} (INVALID {validity['INVALID']}, REVIEW {validity['REVIEW']})",
        f"- 总体宏平均风险发现率 / Overall Macro Finding Rate: {_pct(overall_macro_finding_rate(formal))}",
        f"- 压力条件差值 / Pressure condition gap (C1−C0): {_pp(robustness_gap(formal, 'C1'))}",
        f"- 多轮条件差值 / Multi-turn condition gap (C2−C0): {_pp(robustness_gap(formal, 'C2'))}",
        "",
        "### 模块风险发现率 / Module Finding Rates",
    ]
    rates = module_finding_rates(formal)
    if rates:
        for module, rate in sorted(rates.items()):
            lines.append(f"- {module_label(module)}: {_pct(rate)}")
    else:
        lines.append("- No complete FORMAL module results yet.")

    lines += ["", "### 产品对话测试汇总 / Product Dialogue Summary", "", "| Product | FORMAL cases | Finding rate |", "|---|---:|---:|"]
    for product in product_names:
        rows = [r for r in formal if r.get("product") == product]
        lines.append(f"| {_escape(product)} | {len(rows)} | {_pct(finding_rate(rows))} |")

    lines += [
        "",
        "### Judge—人工一致性 / Judge–Human Reliability",
        f"- 比较案例数 / Cases compared: {rel['n']}",
        f"- 完全一致率 / Exact Agreement: {_pct(rel['exact_agreement'])}",
        "- Cohen's κ: " + ("N/A" if rel["cohen_kappa"] is None else f"{rel['cohen_kappa']:.3f}"),
        f"- 风险发现精确率 / Finding Precision: {_pct(rel['finding_precision'])}",
        f"- 风险发现召回率 / Finding Recall: {_pct(rel['finding_recall'])}",
        "",
        "## Layer 2｜产品安全机制检查 / Product Safeguard Checks",
        "",
    ]
    l2_counts = Counter(str(r.get("status")) for r in l2)
    lines.append(f"Recorded checks: {len(l2)}")
    for status, count in sorted(l2_counts.items()):
        lines.append(f"- {status}: {count}")
    if l2:
        lines += ["", "| Product | Check | Status | Evidence summary |", "|---|---|---|---|"]
        for r in sorted(l2, key=lambda x: (str(x.get("product")), str(x.get("check_code")))):
            lines.append(f"| {_escape(r.get('product'))} | {_escape(r.get('check_code'))} | {_escape(r.get('status'))} | {_escape(r.get('evidence_summary'))} |")

    lines += ["", "## Layer 3 Lite｜公开合规证据核查 / Public Compliance Evidence Audit", ""]
    l3_counts = Counter(str(r.get("status")) for r in l3)
    lines.append(f"Recorded checks: {len(l3)}")
    for status, count in sorted(l3_counts.items()):
        lines.append(f"- {status}: {count}")
    if l3:
        lines += ["", "| Product | Requirement | Status | Evidence summary | Source |", "|---|---|---|---|---|"]
        for r in sorted(l3, key=lambda x: (str(x.get("product")), str(x.get("check_code")))):
            lines.append(
                f"| {_escape(r.get('product'))} | {_escape(r.get('check_code'))} | {_escape(r.get('status'))} | "
                f"{_escape(r.get('evidence_summary'))} | {_escape(r.get('source'))} |"
            )

    lines += [
        "",
        "## 解释边界 / Interpretation Boundary",
        "",
        "CompanionGuard reports traceable testing evidence and risk findings. It does not convert the three evidence layers into a single 0–100 safety/compliance score and does not make a formal legal compliance determination.",
    ]
    return "\n".join(lines) + "\n"


def build_dialogue_report_context(*, project: dict[str, Any], final_rows: list[dict[str, Any]]) -> dict[str, Any]:
    formal_all = [r for r in final_rows if r.get("phase") == "FORMAL"]
    formal = valid_case_rows(formal_all)
    rel = reliability_metrics(formal)
    reviewed_formal = [r for r in formal if (r.get("adjudication_status") or "REVIEWED") == "REVIEWED"]
    adjudication_status = Counter(str(r.get("adjudication_status") or "REVIEWED") for r in formal_all)
    product_names = [p.get("label") or p.get("name") or p.get("id", "") for p in project.get("products", [])]
    products: dict[str, Any] = {}
    for product in product_names:
        rows = [r for r in formal if r.get("product") == product]
        coverage_types = sorted({str(r.get("coverage_type") or r.get("metadata", {}).get("coverage_type") or "UNKNOWN") for r in rows})
        products[product] = {
            "formal_cases": len(rows),
            "finding_rate": finding_rate(rows),
            "finding_rate_display": _pct(finding_rate(rows)),
            "coverage_types": coverage_types,
        }
    modules = module_finding_rates(formal)
    criteria = {}
    for row in formal:
        cid = row.get("criterion_id")
        if not cid:
            continue
        bucket = criteria.setdefault(cid, {"criterion_name": row.get("criterion_name", ""), "module": row.get("module", ""), "formal_cases": 0, "finding_rate": None})
        bucket["formal_cases"] += 1
    for cid, bucket in criteria.items():
        bucket["finding_rate"] = finding_rate([r for r in formal if r.get("criterion_id") == cid])
    condition_rates = {}
    for condition in ("C0", "C1", "C2"):
        condition_rates[condition] = finding_rate([r for r in formal if r.get("condition") == condition])
    pressure = robustness_gap(formal, "C1")
    multi_turn = robustness_gap(formal, "C2")
    representative = []
    for row in formal:
        if (row.get("analysis_label") or row.get("final_label")) == "FINDING":
            representative.append({
                "case_id": row.get("case_id"), "product": row.get("product"), "condition": row.get("condition"),
                "criterion_id": row.get("criterion_id"), "final_label": "FINDING", "finding_type": row.get("matched_target_behaviors", ""),
                "evidence_excerpt": row.get("evidence", ""), "why_representative": "deterministically selected first valid FINDING per available evidence",
                "supported_aggregate": False,
            })
            if len(representative) >= 10:
                break
    validity = case_validity_counts(formal_all)
    reliability_display = {
        "exact_agreement": _pct(rel.get("exact_agreement")),
        "finding_precision": _pct(rel.get("finding_precision")),
        "finding_recall": _pct(rel.get("finding_recall")),
        "cohen_kappa": "N/A" if rel.get("cohen_kappa") is None else f"{rel['cohen_kappa']:.3f}",
    }
    return {
        "meta": {"context_schema_version": "1.0", "report_type": "dialogue", "project_id": project.get("project_id"), "source_policy": "FORMAL-only metrics"},
        "coverage": {"formal_case_count": len(formal), "adjudicated_formal_case_count": len(reviewed_formal), "phases_included": ["FORMAL"]},
        "overall": {"macro_finding_rate": overall_macro_finding_rate(formal), "macro_finding_rate_display": _pct(overall_macro_finding_rate(formal)), "case_validity": validity},
        "project": {
            "project_id": project.get("project_id"),
            "project_name": project.get("project_name"),
            "mode": project.get("mode"),
        },
        "formal_case_count": len(formal),
        "adjudicated_formal_case_count": len(reviewed_formal),
        "formal_case_validity": case_validity_counts(formal_all),
        "human_adjudication_policy": project.get("human_adjudication_policy", "FULL_ADJUDICATION"),
        "adjudication_status_counts": {
            "REVIEWED": adjudication_status.get("REVIEWED", 0),
            "UNREVIEWED": adjudication_status.get("UNREVIEWED", 0),
        },
        "overall_macro_finding_rate": overall_macro_finding_rate(formal),
        "overall_macro_finding_rate_display": _pct(overall_macro_finding_rate(formal)),
        "pressure_gap_c1_minus_c0": pressure,
        "pressure_gap_c1_minus_c0_display": _pp(pressure),
        "multi_turn_gap_c2_minus_c0": multi_turn,
        "multi_turn_gap_c2_minus_c0_display": _pp(multi_turn),
        "module_finding_rates": modules,
        "module_finding_rates_display": {key: _pct(value) for key, value in modules.items()},
        "products": products,
        "reliability": rel,
        "reliability_display": reliability_display,
        "modules": modules,
        "criteria": criteria,
        "conditions": {key: {"finding_rate": value, "finding_rate_display": _pct(value), "sample_size": sum(1 for r in formal if r.get("condition") == key), "small_sample": sum(1 for r in formal if r.get("condition") == key) < SMALL_SAMPLE_THRESHOLD} for key, value in condition_rates.items()},
        "comparisons": {
            "pressure": {"supported": pressure is not None, "raw_value": pressure, "display_value": _pp(pressure), "allowed_interpretation": ["C1与C0的正式风险发现率差异"] if pressure is not None else []},
            "multi_turn": {"supported": multi_turn is not None, "raw_value": multi_turn, "display_value": _pp(multi_turn), "allowed_interpretation": ["C2与C0的正式风险发现率差异"] if multi_turn is not None else []},
        },
        "representative_findings": representative,
        "layer2": {}, "layer3": {}, "cross_layer": {"aligned_patterns": [], "inconsistent_patterns": [], "unresolved_patterns": []},
        "limitations": ["仅使用 phase == FORMAL 的有效案例计算正式对话指标。"],
        "unresolved_questions": [], "verification_needed": [],
        "interpretation_boundary": {
            "no_single_safety_score": True,
            "no_formal_legal_compliance_determination": True,
            "subset_warning": "BENCHMARK_SUBSET/CUSTOM coverage must not be presented as directly equivalent to a full benchmark aggregate.",
        },
    }


def build_integrated_report_context(
    *,
    project: dict[str, Any],
    final_rows: list[dict[str, Any]],
    layer2_path: Path,
    layer3_path: Path,
) -> dict[str, Any]:
    dialogue = build_dialogue_report_context(project=project, final_rows=final_rows)
    layer2 = load_jsonl(layer2_path)
    layer3 = load_jsonl(layer3_path)
    dialogue["meta"]["report_type"] = "integrated"
    dialogue["layer2"] = {"records": layer2, "record_count": len(layer2)}
    dialogue["layer3"] = {"records": layer3, "record_count": len(layer3)}
    dialogue["cross_layer"] = _cross_layer_patterns(formal=[r for r in final_rows if r.get("phase") == "FORMAL" and (r.get("final_case_validity") or r.get("case_validity", "VALID")) == "VALID"], layer2=layer2, layer3=layer3)
    return {
        **dialogue,
        "dialogue": dialogue,
        "layer2_product_safeguards": layer2,
        "layer3_public_compliance_evidence": layer3,
        "evidence_boundary": {
            "dialogue_evidence_cannot_substitute_product_evidence": True,
            "product_evidence_cannot_substitute_documentary_evidence": True,
            "documentary_evidence_does_not_prove_unobserved_runtime_behavior": True,
        },
    }


def build_dialogue_report(project: dict[str, Any], final_rows: list[dict[str, Any]]) -> str:
    context = build_dialogue_report_context(project=project, final_rows=final_rows)
    lines = [
        f"# CompanionGuard Dialogue Report — {project.get('project_name', project.get('project_id'))}",
        "",
        f"- FORMAL 案例数 / FORMAL cases: {context['formal_case_count']}",
        f"- 已人工复核的 FORMAL 案例 / Adjudicated FORMAL cases: {context['adjudicated_formal_case_count']}",
        f"- 人工复核策略 / Human Adjudication policy: {context['human_adjudication_policy']}",
        f"- 分析标签 / Analysis labels: REVIEWED {context['adjudication_status_counts']['REVIEWED']}; UNREVIEWED {context['adjudication_status_counts']['UNREVIEWED']}",
        f"- 案例有效性 / Case Validity: VALID {context['formal_case_validity']['VALID']}; INVALID {context['formal_case_validity']['INVALID']}; REVIEW {context['formal_case_validity']['REVIEW']}",
        f"- 因案例有效性排除的 FORMAL 案例 / FORMAL cases excluded by Case Validity: {sum(context['formal_case_validity'][key] for key in ('INVALID', 'REVIEW'))} (INVALID {context['formal_case_validity']['INVALID']}, REVIEW {context['formal_case_validity']['REVIEW']})",
        f"- 总体宏平均风险发现率 / Overall Macro Finding Rate: {_pct(context['overall_macro_finding_rate'])}",
        f"- 压力条件差值 / Pressure condition gap (C1−C0): {_pp(context['pressure_gap_c1_minus_c0'])}",
        f"- 多轮条件差值 / Multi-turn condition gap (C2−C0): {_pp(context['multi_turn_gap_c2_minus_c0'])}",
        "",
        "## Module Finding Rates",
    ]
    for module, rate in sorted(context["module_finding_rates"].items()):
        lines.append(f"- {module_label(module)}: {_pct(rate)}")
    lines += ["", "## Product Coverage", "", "| Product | FORMAL cases | Finding rate | Coverage |", "|---|---:|---:|---|"]
    for product, row in context["products"].items():
        lines.append(f"| {_escape(product)} | {row['formal_cases']} | {_pct(row['finding_rate'])} | {_escape(', '.join(row['coverage_types']))} |")
    lines += [
        "",
        "## 解释边界 / Interpretation Boundary",
        "",
        "Benchmark-subset/custom results are targeted evaluations and must not be presented as directly equivalent to full-benchmark aggregates. CompanionGuard does not output a single 0–100 safety score or a formal legal compliance determination.",
    ]
    return "\n".join(lines) + "\n"
