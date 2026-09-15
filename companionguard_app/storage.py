from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adjudication import FULL_ADJUDICATION, SAMPLED_ADJUDICATION
from .config import ADJUDICATION_PATH, CASE_VALIDITIES, DATA_DIR, FINAL_RESULTS_PATH, JUDGE_RESULTS_PATH

ADJUDICATION_FIELDS = [
    "case_id",
    "auto_label",
    "human_label",
    "final_label",
    "override_reason",
    "review_note",
    "reviewed_at",
    "case_validity",
    "auto_case_validity",
    "final_case_validity",
    "validity_reason",
    "validity_note",
    "validity_reviewed_at",
]


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def append_judge_result(row: dict[str, Any], path: Path = JUDGE_RESULTS_PATH) -> None:
    ensure_data_dir()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_judge_results(path: Path = JUDGE_RESULTS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def completed_case_ids(path: Path = JUDGE_RESULTS_PATH) -> set[str]:
    return {
        row.get("case_id")
        for row in load_judge_results(path)
        if row.get("status") == "ok" and row.get("case_id")
    }


def load_adjudications(path: Path = ADJUDICATION_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_adjudication(
    *,
    case_id: str,
    auto_label: str,
    human_label: str,
    override_reason: str = "",
    review_note: str = "",
    case_validity: str = "VALID",
    auto_case_validity: str = "VALID",
    final_case_validity: str | None = None,
    validity_reason: str = "",
    validity_note: str = "",
    path: Path = ADJUDICATION_PATH,
) -> None:
    ensure_data_dir()
    final_case_validity = final_case_validity or case_validity
    if auto_case_validity not in CASE_VALIDITIES:
        raise ValueError(f"Unsupported auto case validity: {auto_case_validity}")
    if final_case_validity not in CASE_VALIDITIES:
        raise ValueError(f"Unsupported final case validity: {final_case_validity}")
    if human_label == auto_label:
        override_reason = ""
    if final_case_validity == "VALID":
        validity_reason = ""

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "case_id": case_id,
        "auto_label": auto_label,
        "human_label": human_label,
        "final_label": human_label,
        "override_reason": override_reason,
        "review_note": review_note,
        "reviewed_at": now,
        "case_validity": final_case_validity,
        "auto_case_validity": auto_case_validity,
        "final_case_validity": final_case_validity,
        "validity_reason": validity_reason,
        "validity_note": validity_note,
        "validity_reviewed_at": now,
    }

    existing = {r["case_id"]: r for r in load_adjudications(path)}
    existing[case_id] = row

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ADJUDICATION_FIELDS)
        writer.writeheader()
        writer.writerows(existing.values())


def _extract_evidence(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    items = list(result.get("evidence") or [])
    if result.get("safeguard_evidence"):
        items.extend(result["safeguard_evidence"])
    quotes = []
    for item in items:
        quote = item.get("quote") if isinstance(item, dict) else None
        if quote and quote not in quotes:
            quotes.append(quote)
    return " | ".join(quotes)


def _extract_tcodes(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    return ",".join(result.get("matched_target_behaviors") or [])


def build_final_results(
    criteria: dict[str, dict[str, Any]],
    *,
    judge_path: Path = JUDGE_RESULTS_PATH,
    adjudication_path: Path = ADJUDICATION_PATH,
    output_path: Path = FINAL_RESULTS_PATH,
    policy: str = FULL_ADJUDICATION,
) -> list[dict[str, Any]]:
    ensure_data_dir()
    adjudications = {r["case_id"]: r for r in load_adjudications(adjudication_path)}
    final_rows: list[dict[str, Any]] = []

    for row in load_judge_results(judge_path):
        if row.get("status") != "ok":
            continue
        adj = adjudications.get(row.get("case_id"))
        if not adj and policy != SAMPLED_ADJUDICATION:
            continue
        criterion = criteria.get(row.get("criterion_id"), {})
        result = row.get("result") or {}
        metadata = row.get("metadata") or {}
        auto_case_validity = row.get("auto_case_validity") or metadata.get("auto_case_validity") or "VALID"
        if adj:
            adjudication_status = "REVIEWED"
            human_label = adj.get("human_label", "")
            final_label = adj.get("final_label", "")
            final_case_validity = adj.get("final_case_validity") or adj.get("case_validity") or auto_case_validity
            validity_reason = adj.get("validity_reason", "")
            validity_note = adj.get("validity_note", "")
            validity_reviewed_at = adj.get("validity_reviewed_at", "")
        else:
            adjudication_status = "UNREVIEWED"
            human_label = ""
            final_label = ""
            final_case_validity = auto_case_validity
            validity_reason = row.get("auto_validity_reason", "")
            validity_note = ""
            validity_reviewed_at = ""
        final_rows.append({
            "case_id": row.get("case_id", ""),
            "criterion_id": row.get("criterion_id", ""),
            "criterion_name": criterion.get("criterion_name_zh", ""),
            "module": criterion.get("module", ""),
            "product": row.get("product") or "",
            "scenario_id": metadata.get("scenario_id", ""),
            "condition": row.get("condition") or "N/A",
            "phase": metadata.get("phase", ""),
            "run_number": metadata.get("run_number", ""),
            "collection_date": metadata.get("collection_date", ""),
            "coverage_type": metadata.get("coverage_type", ""),
            "auto_label": row.get("auto_label") or "",
            "human_label": human_label,
            "final_label": final_label,
            "analysis_label": final_label or row.get("auto_label") or "",
            "adjudication_status": adjudication_status,
            "adjudication_policy": policy,
            "override_reason": adj.get("override_reason", "") if adj else "",
            "review_note": adj.get("review_note", "") if adj else "",
            "case_validity": final_case_validity,
            "auto_case_validity": auto_case_validity,
            "final_case_validity": final_case_validity,
            "validity_reason": validity_reason,
            "validity_note": validity_note,
            "validity_reviewed_at": validity_reviewed_at,
            "matched_target_behaviors": _extract_tcodes(result),
            "evidence": _extract_evidence(result),
            "rationale": result.get("rationale", ""),
            "judge_provider": (row.get("judge") or {}).get("provider", ""),
            "judge_model": (row.get("judge") or {}).get("model", ""),
            "judge_template": row.get("judge_template", ""),
            "reviewed_at": adj.get("reviewed_at", "") if adj else "",
        })

    fieldnames = [
        "case_id", "criterion_id", "criterion_name", "module", "product", "scenario_id",
        "condition", "phase", "run_number", "collection_date", "coverage_type", "auto_label", "human_label", "final_label", "analysis_label", "adjudication_status", "adjudication_policy", "override_reason", "review_note",
        "case_validity", "auto_case_validity", "final_case_validity", "validity_reason", "validity_note", "validity_reviewed_at",
        "matched_target_behaviors", "evidence", "rationale", "judge_provider", "judge_model",
        "judge_template", "reviewed_at",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)
    return final_rows


def load_final_results(path: Path = FINAL_RESULTS_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
