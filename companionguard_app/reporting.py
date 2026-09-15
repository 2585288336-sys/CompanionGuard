from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .audits import load_jsonl
from .metrics import case_validity_counts, finding_rate, module_finding_rates, overall_macro_finding_rate, robustness_gap, valid_case_rows
from .reliability import reliability_metrics


def _pct(v: float | None) -> str:
    return "N/A" if v is None else f"{v * 100:.1f}%"


def _pp(v: float | None) -> str:
    return "N/A" if v is None else f"{v * 100:+.1f} pp"


def _escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


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
    rel = reliability_metrics(formal)
    l2 = load_jsonl(layer2_path)
    l3 = load_jsonl(layer3_path)

    product_names = [p.get("label") or p.get("name") or p.get("id", "") for p in project.get("products", [])]
    lines = [
        f"# CompanionGuard 综合测试报告 / Integrated Report — {project.get('project_name', project.get('project_id'))}",
        "",
        f"- Project ID: `{project.get('project_id', '')}`",
        f"- Mode: `{project.get('mode', '')}`",
        f"- Products: {', '.join(product_names)}",
        "",
        "## Layer 1｜对话行为测试 / Dialogue Behavioral Testing",
        "",
        f"- Adjudicated FORMAL cases: {len(formal)}",
        f"- Case Validity: VALID {validity['VALID']}; INVALID {validity['INVALID']}; REVIEW {validity['REVIEW']}",
        f"- FORMAL cases excluded by Case Validity: {validity['INVALID'] + validity['REVIEW']} (INVALID {validity['INVALID']}, REVIEW {validity['REVIEW']})",
        f"- Overall Macro Finding Rate: {_pct(overall_macro_finding_rate(formal))}",
        f"- Pressure condition gap (C1−C0): {_pp(robustness_gap(formal, 'C1'))}",
        f"- Multi-turn condition gap (C2−C0): {_pp(robustness_gap(formal, 'C2'))}",
        "",
        "### 模块风险发现率 / Module Finding Rates",
    ]
    rates = module_finding_rates(formal)
    if rates:
        for module, rate in sorted(rates.items()):
            lines.append(f"- {module}: {_pct(rate)}")
    else:
        lines.append("- No complete FORMAL module results yet.")

    lines += ["", "### 产品对话测试汇总 / Product Dialogue Summary", "", "| Product | FORMAL cases | Finding rate |", "|---|---:|---:|"]
    for product in product_names:
        rows = [r for r in formal if r.get("product") == product]
        lines.append(f"| {_escape(product)} | {len(rows)} | {_pct(finding_rate(rows))} |")

    lines += [
        "",
        "### Judge—人工一致性 / Judge–Human Reliability",
        f"- Cases compared: {rel['n']}",
        f"- Exact Agreement: {_pct(rel['exact_agreement'])}",
        "- Cohen's κ: " + ("N/A" if rel["cohen_kappa"] is None else f"{rel['cohen_kappa']:.3f}"),
        f"- Finding Precision: {_pct(rel['finding_precision'])}",
        f"- Finding Recall: {_pct(rel['finding_recall'])}",
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
    product_names = [p.get("label") or p.get("name") or p.get("id", "") for p in project.get("products", [])]
    products: dict[str, Any] = {}
    for product in product_names:
        rows = [r for r in formal if r.get("product") == product]
        coverage_types = sorted({str(r.get("coverage_type") or r.get("metadata", {}).get("coverage_type") or "UNKNOWN") for r in rows})
        products[product] = {
            "formal_cases": len(rows),
            "finding_rate": finding_rate(rows),
            "coverage_types": coverage_types,
        }
    return {
        "project": {
            "project_id": project.get("project_id"),
            "project_name": project.get("project_name"),
            "mode": project.get("mode"),
        },
        "formal_case_count": len(formal),
        "formal_case_validity": case_validity_counts(formal_all),
        "overall_macro_finding_rate": overall_macro_finding_rate(formal),
        "pressure_gap_c1_minus_c0": robustness_gap(formal, "C1"),
        "multi_turn_gap_c2_minus_c0": robustness_gap(formal, "C2"),
        "module_finding_rates": module_finding_rates(formal),
        "products": products,
        "reliability": rel,
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
    return {
        "dialogue": build_dialogue_report_context(project=project, final_rows=final_rows),
        "layer2_product_safeguards": load_jsonl(layer2_path),
        "layer3_public_compliance_evidence": load_jsonl(layer3_path),
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
        f"- FORMAL cases: {context['formal_case_count']}",
        f"- Case Validity: VALID {context['formal_case_validity']['VALID']}; INVALID {context['formal_case_validity']['INVALID']}; REVIEW {context['formal_case_validity']['REVIEW']}",
        f"- FORMAL cases excluded by Case Validity: {sum(context['formal_case_validity'][key] for key in ('INVALID', 'REVIEW'))} (INVALID {context['formal_case_validity']['INVALID']}, REVIEW {context['formal_case_validity']['REVIEW']})",
        f"- Overall Macro Finding Rate: {_pct(context['overall_macro_finding_rate'])}",
        f"- Pressure condition gap (C1−C0): {_pp(context['pressure_gap_c1_minus_c0'])}",
        f"- Multi-turn condition gap (C2−C0): {_pp(context['multi_turn_gap_c2_minus_c0'])}",
        "",
        "## Module Finding Rates",
    ]
    for module, rate in sorted(context["module_finding_rates"].items()):
        lines.append(f"- {module}: {_pct(rate)}")
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
