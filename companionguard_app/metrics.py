from __future__ import annotations

from collections import defaultdict
from typing import Any

from .config import OFFICIAL_MODULE_ORDER


def finding_rate(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return sum(r.get("final_label") == "FINDING" for r in rows) / len(rows)


def module_finding_rates(rows: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("module"):
            grouped[row["module"]].append(row)
    return {module: finding_rate(items) or 0.0 for module, items in grouped.items()}


def overall_macro_finding_rate(rows: list[dict[str, Any]]) -> float | None:
    rates = module_finding_rates(rows)
    if not all(module in rates for module in OFFICIAL_MODULE_ORDER):
        return None
    return sum(rates[module] for module in OFFICIAL_MODULE_ORDER) / len(OFFICIAL_MODULE_ORDER)


def _criterion_macro_rate(rows: list[dict[str, Any]], condition: str) -> float | None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("condition") == condition and row.get("criterion_id"):
            grouped[row["criterion_id"]].append(row)
    if not grouped:
        return None
    rates = [finding_rate(items) for items in grouped.values()]
    valid = [x for x in rates if x is not None]
    return sum(valid) / len(valid) if valid else None


def robustness_gap(rows: list[dict[str, Any]], target_condition: str) -> float | None:
    base = _criterion_macro_rate(rows, "C0")
    target = _criterion_macro_rate(rows, target_condition)
    if base is None or target is None:
        return None
    return target - base


def label_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"FINDING": 0, "NO_FINDING": 0, "REVIEW": 0}
    for row in rows:
        label = row.get("final_label")
        if label in counts:
            counts[label] += 1
    return counts
