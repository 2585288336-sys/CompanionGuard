from __future__ import annotations

from collections import Counter
from typing import Any

LABELS = ["FINDING", "NO_FINDING", "REVIEW"]


def reliability_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        (str(r.get("auto_label")), str(r.get("human_label")))
        for r in rows
        if r.get("auto_label") in LABELS and r.get("human_label") in LABELS
    ]
    n = len(pairs)
    matrix = {a: {h: 0 for h in LABELS} for a in LABELS}
    for auto, human in pairs:
        matrix[auto][human] += 1
    if not n:
        return {"n": 0, "exact_agreement": None, "cohen_kappa": None, "matrix": matrix, "finding_precision": None, "finding_recall": None}

    exact = sum(a == h for a, h in pairs) / n
    auto_counts = Counter(a for a, _ in pairs)
    human_counts = Counter(h for _, h in pairs)
    pe = sum((auto_counts[label] / n) * (human_counts[label] / n) for label in LABELS)
    kappa = (exact - pe) / (1 - pe) if pe < 1 else 1.0

    tp = matrix["FINDING"]["FINDING"]
    auto_findings = sum(matrix["FINDING"].values())
    human_findings = sum(matrix[a]["FINDING"] for a in LABELS)
    precision = tp / auto_findings if auto_findings else None
    recall = tp / human_findings if human_findings else None
    return {
        "n": n,
        "exact_agreement": exact,
        "cohen_kappa": kappa,
        "matrix": matrix,
        "finding_precision": precision,
        "finding_recall": recall,
    }
