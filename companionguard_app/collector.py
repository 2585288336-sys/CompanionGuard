from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cases import build_conversation_template, flatten_single_turn_scenarios
from .config import COLLECTOR_CONFIG_PATH


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_collector_config(path: Path = COLLECTOR_CONFIG_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("products") or not data.get("phases"):
        raise ValueError("Collector configuration must define products and phases.")
    return data


def product_config(config: dict[str, Any], product_id: str) -> dict[str, Any]:
    for product in config.get("products", []):
        if product.get("id") == product_id:
            return product
    raise KeyError(f"Unknown product_id: {product_id}")


def allowed_criteria_for_product(
    criteria: dict[str, dict[str, Any]],
    collector_config: dict[str, Any],
    product_id: str,
) -> dict[str, dict[str, Any]]:
    product = product_config(collector_config, product_id)
    allowlist = product.get("criterion_allowlist")
    if not allowlist:
        return dict(criteria)
    allowed = set(allowlist)
    return {cid: obj for cid, obj in criteria.items() if cid in allowed}


def scenario_ids(criterion: dict[str, Any]) -> list[str]:
    template = criterion["judge_template"]
    if template in ("core_l1_l5", "hr02_crisis"):
        return [criterion["criterion_id"]]
    if template == "mr_minor_relationship":
        return list((criterion.get("canonical_scenario") or {}).keys())
    if template == "single_turn_regulatory_content":
        return list(flatten_single_turn_scenarios(criterion).keys())
    raise ValueError(f"Unsupported judge_template: {template}")


def available_conditions(criterion: dict[str, Any]) -> list[str | None]:
    template = criterion["judge_template"]
    if template not in ("core_l1_l5", "hr02_crisis"):
        return [None]
    conditions = ["C0"]
    if (criterion.get("pressure_variant") or {}).get("L5"):
        conditions.append("C1")
    conditions.append("C2")
    return conditions


def _consolidated_l1_l4(canonical: dict[str, Any]) -> str:
    return "\n\n".join(str(canonical.get(f"L{i}", "")).strip() for i in range(1, 5)).strip()


def build_collection_plan(
    criterion: dict[str, Any],
    *,
    condition: str | None,
    scenario_id: str,
) -> list[dict[str, Any]]:
    template = criterion["judge_template"]
    canonical = criterion.get("canonical_scenario") or {}

    if template in ("core_l1_l5", "hr02_crisis"):
        if condition not in available_conditions(criterion):
            raise ValueError(
                f"{criterion['criterion_id']} does not have a frozen/configured {condition} prompt."
            )
        if condition == "C2":
            return [
                {
                    "sequence": i,
                    "prompt_turn": f"L{i}",
                    "response_turn": f"A{i}",
                    "prompt": canonical[f"L{i}"],
                }
                for i in range(1, 6)
            ]

        l5 = canonical["L5"]
        if condition == "C1":
            l5 = criterion["pressure_variant"]["L5"]
        return [
            {
                "sequence": 1,
                "prompt_turn": "L1-L4",
                "response_turn": "A4",
                "prompt": _consolidated_l1_l4(canonical),
            },
            {
                "sequence": 2,
                "prompt_turn": "L5",
                "response_turn": "A5",
                "prompt": l5,
            },
        ]

    if template == "mr_minor_relationship":
        scenario = canonical[scenario_id]
        return [
            {"sequence": 1, "prompt_turn": "R1", "response_turn": "A_R1", "prompt": scenario["R1"]},
            {"sequence": 2, "prompt_turn": "R2", "response_turn": "A_R2", "prompt": scenario["R2"]},
        ]

    if template == "single_turn_regulatory_content":
        prompts = flatten_single_turn_scenarios(criterion)
        return [
            {"sequence": 1, "prompt_turn": "P1", "response_turn": "A1", "prompt": prompts[scenario_id]}
        ]

    raise ValueError(f"Unsupported judge_template: {template}")


def category_for_scenario(criterion: dict[str, Any], scenario_id: str) -> str | None:
    if criterion["judge_template"] != "single_turn_regulatory_content":
        return None
    criterion_id = criterion["criterion_id"]
    if scenario_id == criterion_id:
        return criterion_id
    return scenario_id.rsplit("-", 1)[0]


def _safe_id_part(value: str) -> str:
    value = value.strip().replace(" ", "-")
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-+", "-", value).strip("-_.")
    if not value:
        raise ValueError("ID component cannot be empty.")
    return value


def make_case_id(
    *,
    product_slug: str,
    criterion_id: str,
    scenario_id: str | None,
    condition: str | None,
    phase: str,
    run_number: int,
) -> str:
    subject = scenario_id or criterion_id
    return "_".join(
        [
            _safe_id_part(product_slug),
            _safe_id_part(subject),
            _safe_id_part(condition or "NA"),
            _safe_id_part(phase),
            f"run{int(run_number):02d}",
        ]
    )


def build_queue_items(
    *,
    criteria: dict[str, dict[str, Any]],
    criterion_ids: list[str],
    product_slug: str,
    phase: str,
    run_numbers: list[int],
    condition_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Expand configured criteria into queueable case specifications.

    This is deliberately criterion-agnostic: the expansion is driven by each
    criterion's judge_template, scenarios and configured conditions.
    """
    items: list[dict[str, Any]] = []
    position = 1
    for criterion_id in criterion_ids:
        criterion = criteria[criterion_id]
        conditions = available_conditions(criterion)
        if conditions == [None]:
            selected_conditions: list[str | None] = [None]
        else:
            allowed = set(condition_filter if condition_filter is not None else [c for c in conditions if c])
            selected_conditions = [c for c in conditions if c in allowed]
        for scenario_id in scenario_ids(criterion):
            for condition in selected_conditions:
                for run_number in run_numbers:
                    items.append({
                        "position": position,
                        "case_id": make_case_id(
                            product_slug=product_slug,
                            criterion_id=criterion_id,
                            scenario_id=scenario_id,
                            condition=condition,
                            phase=phase,
                            run_number=run_number,
                        ),
                        "criterion_id": criterion_id,
                        "scenario_id": scenario_id,
                        "condition": condition,
                        "run_number": int(run_number),
                        "status": "PENDING",
                        "session_id": None,
                    })
                    position += 1
    return items


def create_collection_queue(
    *,
    queue_id: str,
    queue_name: str,
    product_id: str,
    product_name: str,
    product_slug: str,
    product_role: str,
    phase: str,
    collection_date: str,
    items: list[dict[str, Any]],
    notes: str = "",
) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "queue_id": queue_id,
        "queue_name": queue_name or queue_id,
        "queue_status": "IN_PROGRESS" if items else "COMPLETE",
        "product_id": product_id,
        "product": product_name,
        "product_slug": product_slug,
        "product_role": product_role,
        "phase": phase,
        "collection_date": collection_date,
        "notes": notes,
        "items": deepcopy(items),
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }


def next_queue_item(queue: dict[str, Any]) -> dict[str, Any] | None:
    for item in queue.get("items", []):
        if item.get("status") in {"IN_PROGRESS", "PENDING"}:
            return item
    return None


def create_collection_session(
    *,
    criterion: dict[str, Any],
    product_id: str,
    product_name: str,
    product_slug: str,
    product_role: str,
    scenario_id: str,
    condition: str | None,
    run_number: int,
    phase: str,
    collection_date: str,
    notes: str = "",
    queue_id: str | None = None,
) -> dict[str, Any]:
    case_id = make_case_id(
        product_slug=product_slug,
        criterion_id=criterion["criterion_id"],
        scenario_id=scenario_id,
        condition=condition,
        phase=phase,
        run_number=run_number,
    )
    plan = build_collection_plan(criterion, condition=condition, scenario_id=scenario_id)
    for step in plan:
        step.update({"response": None, "draft_response": None, "saved_at": None, "evidence_files": []})

    now = utc_now_iso()
    return {
        "session_id": case_id,
        "case_id": case_id,
        "queue_id": queue_id,
        "collection_status": "IN_PROGRESS",
        "product_id": product_id,
        "product": product_name,
        "product_slug": product_slug,
        "product_role": product_role,
        "criterion_id": criterion["criterion_id"],
        "criterion_file": criterion.get("_source_file"),
        "criterion_status": criterion.get("status"),
        "judge_template": criterion["judge_template"],
        "scenario_id": scenario_id,
        "condition": condition,
        "run_number": int(run_number),
        "phase": phase,
        "collection_date": collection_date,
        "notes": notes,
        "current_step_index": 0,
        "steps": plan,
        "standard_conversation_template": build_conversation_template(
            criterion,
            condition=condition or "C0",
            scenario_id=scenario_id,
        ),
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }


def save_step_draft(
    session: dict[str, Any],
    *,
    step_index: int,
    draft_response: str,
) -> dict[str, Any]:
    """Persist an in-progress text draft without advancing the collection turn."""
    if session.get("collection_status") != "IN_PROGRESS":
        raise ValueError("Only IN_PROGRESS sessions can be edited.")
    if step_index < 0 or step_index >= len(session.get("steps", [])):
        raise IndexError("Invalid collection step index.")
    updated = deepcopy(session)
    updated["steps"][step_index]["draft_response"] = draft_response
    updated["updated_at"] = utc_now_iso()
    return updated


def save_step_response(
    session: dict[str, Any],
    *,
    step_index: int,
    response: str,
    evidence_files: list[str] | None = None,
) -> dict[str, Any]:
    if not response.strip():
        raise ValueError("Model response cannot be empty.")
    if session.get("collection_status") != "IN_PROGRESS":
        raise ValueError("Only IN_PROGRESS sessions can be edited.")
    if step_index < 0 or step_index >= len(session.get("steps", [])):
        raise IndexError("Invalid collection step index.")

    updated = deepcopy(session)
    step = updated["steps"][step_index]
    step["response"] = response
    step["draft_response"] = None
    step["saved_at"] = utc_now_iso()
    if evidence_files is not None:
        step["evidence_files"] = list(evidence_files)
    updated["current_step_index"] = min(step_index + 1, len(updated["steps"]))
    updated["updated_at"] = utc_now_iso()
    return updated


def previous_step(session: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(session)
    updated["current_step_index"] = max(int(updated.get("current_step_index", 0)) - 1, 0)
    updated["updated_at"] = utc_now_iso()
    return updated


def is_session_ready(session: dict[str, Any]) -> bool:
    steps = session.get("steps") or []
    return bool(steps) and all((step.get("response") or "").strip() for step in steps)


def _filled_conversation(session: dict[str, Any]) -> list[dict[str, str]]:
    response_by_turn = {
        step["response_turn"]: step["response"]
        for step in session["steps"]
        if step.get("response")
    }
    conversation = deepcopy(session["standard_conversation_template"])
    for turn in conversation:
        if turn.get("role") == "assistant":
            response = response_by_turn.get(turn.get("turn"))
            if not response:
                raise ValueError(f"Missing response for {turn.get('turn')}")
            turn["content"] = response
    return conversation


def build_raw_case(session: dict[str, Any], criterion: dict[str, Any]) -> dict[str, Any]:
    if not is_session_ready(session):
        raise ValueError("Collection session is not complete.")
    if session["criterion_id"] != criterion["criterion_id"]:
        raise ValueError("Session criterion does not match criterion configuration.")

    trace = [
        {
            "sequence": step["sequence"],
            "prompt_turn": step["prompt_turn"],
            "response_turn": step["response_turn"],
            "prompt": step["prompt"],
            "response": step["response"],
            "saved_at": step.get("saved_at"),
            "evidence_files": step.get("evidence_files") or [],
        }
        for step in session["steps"]
    ]
    category = category_for_scenario(criterion, session["scenario_id"])
    metadata = {
        "source": "data_collector",
        "scenario_id": session["scenario_id"],
        "phase": session["phase"],
        "run_number": session["run_number"],
        "collection_date": session["collection_date"],
        "notes": session.get("notes", ""),
        "product_id": session.get("product_id"),
        "product_role": session.get("product_role"),
        "collection_status": "COMPLETE",
        "queue_id": session.get("queue_id"),
    }
    case: dict[str, Any] = {
        "case_id": session["case_id"],
        "criterion_id": session["criterion_id"],
        "scenario_id": session["scenario_id"],
        "condition": session.get("condition"),
        "product": session["product"],
        "phase": session["phase"],
        "run_number": session["run_number"],
        "collection_date": session["collection_date"],
        "collection_status": "COMPLETE",
        "conversation": _filled_conversation(session),
        "collection_trace": trace,
        "metadata": metadata,
    }
    if category:
        case["category"] = category
    return case


def mark_session_complete(session: dict[str, Any]) -> dict[str, Any]:
    if not is_session_ready(session):
        raise ValueError("Cannot complete a session with missing responses.")
    updated = deepcopy(session)
    updated["collection_status"] = "COMPLETE"
    updated["current_step_index"] = len(updated["steps"])
    updated["completed_at"] = utc_now_iso()
    updated["updated_at"] = updated["completed_at"]
    return updated
