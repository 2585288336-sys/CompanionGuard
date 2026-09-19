from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_scope import RuntimeScope, assert_writable_target

FULL_ADJUDICATION = "FULL_ADJUDICATION"
SAMPLED_ADJUDICATION = "SAMPLED_ADJUDICATION"
RANDOM_SAMPLE = "RANDOM_SAMPLE"
STRATIFIED_SAMPLE = "STRATIFIED_SAMPLE"


def adjudication_policy(project: dict[str, Any]) -> str:
    return project.get("human_adjudication_policy", FULL_ADJUDICATION)


def _is_formal(row: dict[str, Any]) -> bool:
    return str(row.get("phase") or (row.get("metadata") or {}).get("phase") or "") == "FORMAL"


def _auto_validity(row: dict[str, Any]) -> str:
    return row.get("auto_case_validity") or (row.get("metadata") or {}).get("auto_case_validity") or "VALID"


def _forced_case(row: dict[str, Any]) -> bool:
    return row.get("auto_label") == "REVIEW" or _auto_validity(row) == "REVIEW"


def build_sampling_plan(
    *,
    judge_rows: list[dict[str, Any]],
    project: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    formal = sorted(
        (row for row in judge_rows if row.get("status") == "ok" and _is_formal(row) and row.get("case_id")),
        key=lambda row: str(row["case_id"]),
    )
    forced = sorted({row["case_id"] for row in formal if _forced_case(row)})
    forced_set = set(forced)
    remaining = [row for row in formal if row["case_id"] not in forced_set]
    rate = min(max(float(project.get("human_adjudication_sample_rate", 0.25)), 0.0), 1.0)
    seed = int(project.get("human_adjudication_random_seed", 20260915))
    method = project.get("human_adjudication_sampling_method", STRATIFIED_SAMPLE)
    if method not in {RANDOM_SAMPLE, STRATIFIED_SAMPLE}:
        raise ValueError(f"Unsupported sampling method: {method}")
    strata = list(project.get("human_adjudication_strata") or ["product", "criterion_id", "condition"])
    target = min(len(remaining), max(0, math.ceil(len(formal) * rate) - len(forced)))
    rng = random.Random(seed)

    selected: list[str] = []
    if method == RANDOM_SAMPLE:
        selected = [row["case_id"] for row in rng.sample(remaining, target)] if target else []
    else:
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in remaining:
            key = tuple(str(row.get(field) or (row.get("metadata") or {}).get(field) or "N/A") for field in strata)
            groups[key].append(row)
        for group in groups.values():
            group.sort(key=lambda row: str(row["case_id"]))
        for key in sorted(groups, key=str):
            selected.append(rng.choice(groups[key])["case_id"])
        target = min(len(remaining), max(target, len(groups)))
        selected_set = set(selected)
        extra = [row for row in remaining if row["case_id"] not in selected_set]
        selected.extend(row["case_id"] for row in rng.sample(extra, min(target - len(selected), len(extra))))

    selected_case_ids = sorted(set(forced) | set(selected))
    return {
        "schema_version": "0.8.2",
        "project_id": project.get("project_id"),
        "policy": SAMPLED_ADJUDICATION,
        "sampling_method": method,
        "sample_rate": rate,
        "random_seed": seed,
        "strata": strata,
        "selected_case_ids": selected_case_ids,
        "forced_case_ids": forced,
        "formal_judge_case_count": len(formal),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }


def load_sampling_plan(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def save_sampling_plan(
    plan: dict[str, Any],
    path: Path,
    *,
    scope: RuntimeScope | str | None = None,
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> None:
    target = assert_writable_target(scope, path, workspace_root=workspace_root, data_root=data_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def review_case_ids(
    *,
    judge_rows: list[dict[str, Any]],
    project: dict[str, Any],
    sampling_plan: dict[str, Any] | None,
) -> set[str]:
    if adjudication_policy(project) != SAMPLED_ADJUDICATION:
        return {row.get("case_id") for row in judge_rows if row.get("case_id")}

    selected = set((sampling_plan or {}).get("selected_case_ids") or [])
    return {
        row["case_id"] for row in judge_rows
        if row.get("status") == "ok"
        and row.get("case_id")
        and (not _is_formal(row) or row["case_id"] in selected or _forced_case(row))
    }
