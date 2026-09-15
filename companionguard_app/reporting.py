from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .audits import load_jsonl
from .metrics import finding_rate, module_finding_rates, overall_macro_finding_rate, robustness_gap
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
    formal = [r for r in final_rows if r.get("phase") == "FORMAL"]
    rel = reliability_metrics(final_rows)
    l2 = load_jsonl(layer2_path)
    l3 = load_jsonl(layer3_path)

    product_names = [p.get("label") or p.get("name") or p.get("id", "") for p in project.get("products", [])]
    lines = [
        f"# CompanionGuard Integrated Report — {project.get('project_name', project.get('project_id'))}",
        "",
        f"- Project ID: `{project.get('project_id', '')}`",
        f"- Mode: `{project.get('mode', '')}`",
        f"- Products: {', '.join(product_names)}",
        "",
        "## Layer 1 — Dialogue Behavioral Testing",
        "",
        f"- Adjudicated FORMAL cases: {len(formal)}",
        f"- Overall Macro Finding Rate: {_pct(overall_macro_finding_rate(formal))}",
        f"- Pressure condition gap (C1−C0): {_pp(robustness_gap(formal, 'C1'))}",
        f"- Multi-turn condition gap (C2−C0): {_pp(robustness_gap(formal, 'C2'))}",
        "",
        "### Module Finding Rates",
    ]
    rates = module_finding_rates(formal)
    if rates:
        for module, rate in sorted(rates.items()):
            lines.append(f"- {module}: {_pct(rate)}")
    else:
        lines.append("- No complete FORMAL module results yet.")

    lines += ["", "### Product Dialogue Summary", "", "| Product | FORMAL cases | Finding rate |", "|---|---:|---:|"]
    for product in product_names:
        rows = [r for r in formal if r.get("product") == product]
        lines.append(f"| {_escape(product)} | {len(rows)} | {_pct(finding_rate(rows))} |")

    lines += [
        "",
        "### Judge–Human Reliability",
        f"- Cases compared: {rel['n']}",
        f"- Exact Agreement: {_pct(rel['exact_agreement'])}",
        "- Cohen's κ: " + ("N/A" if rel["cohen_kappa"] is None else f"{rel['cohen_kappa']:.3f}"),
        f"- Finding Precision: {_pct(rel['finding_precision'])}",
        f"- Finding Recall: {_pct(rel['finding_recall'])}",
        "",
        "## Layer 2 — Product Safeguard Checks",
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

    lines += ["", "## Layer 3 Lite — Public Compliance Evidence Audit", ""]
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
        "## Interpretation Boundary",
        "",
        "CompanionGuard reports traceable testing evidence and risk findings. It does not convert the three evidence layers into a single 0–100 safety/compliance score and does not make a formal legal compliance determination.",
    ]
    return "\n".join(lines) + "\n"
