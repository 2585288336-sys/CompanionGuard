from __future__ import annotations
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

from . import __version__
if TYPE_CHECKING:
    from companionguard_llm.client import LLMClient
from .prompts import PROMPT_VERSION, SYSTEM_PROMPTS
from .schemas import SCHEMAS
from .validation import auto_label, validate_case, validate_result


def load_criteria(criteria_dir: Path) -> dict[str, dict[str, Any]]:
    index = {}
    for path in sorted(criteria_dir.glob("*.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        cid = obj.get("criterion_id")
        template = obj.get("judge_template")
        if not cid or template not in SCHEMAS:
            continue
        obj["_source_file"] = path.name
        index[cid] = obj
    if not index:
        raise ValueError(f"No usable criteria found in {criteria_dir}")
    return index


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {e}") from e
        case_id = row.get("case_id")
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        rows.append(row)
    return rows


def _criterion_payload(criterion: dict[str, Any]) -> dict[str, Any]:
    keep = [
        "criterion_id", "criterion_name_zh", "criterion", "evaluation_scope",
        "target_behaviors", "non_target_behaviors", "frozen_boundary_rules",
        "review_policy", "machine_checks", "safeguard_rules", "finding_type_rules",
    ]
    return {k: criterion[k] for k in keep if k in criterion}


def _completed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") == "ok":
            done.add(row.get("case_id"))
    return done


def _write_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def dry_run(cases: list[dict[str, Any]], criteria: dict[str, dict[str, Any]]) -> list[str]:
    errors = []
    for case in cases:
        criterion = criteria.get(case.get("criterion_id"))
        if criterion is None:
            errors.append(f"{case.get('case_id')}: unknown criterion_id={case.get('criterion_id')}")
            continue
        errors.extend(f"{case.get('case_id')}: {e}" for e in validate_case(case, criterion["judge_template"]))
    return errors


def judge_case(client: "LLMClient", criterion: dict[str, Any], case: dict[str, Any], semantic_retries: int = 1) -> dict[str, Any]:
    template = criterion["judge_template"]
    input_errors = validate_case(case, template)
    if input_errors:
        return _error_row(case, criterion, "; ".join(input_errors))

    feedback = None
    usage = None
    for attempt in range(semantic_retries + 1):
        payload = {
            "criteria": _criterion_payload(criterion),
            "case": case,
        }
        if feedback:
            payload["correction_request"] = {
                "instruction": "上一结果通过了JSON Schema，但未通过业务语义校验。请完整重新判定。",
                "validation_errors": feedback,
            }
        try:
            result, usage = client.judge(
                system_prompt=SYSTEM_PROMPTS[template],
                payload=payload,
                schema_name=template,
                schema=SCHEMAS[template],
            )
        except Exception as e:
            return _error_row(case, criterion, f"API_ERROR: {type(e).__name__}: {e}")

        semantic_errors = validate_result(result, criterion, case)
        if not semantic_errors:
            return {
                "case_id": case["case_id"],
                "criterion_id": criterion["criterion_id"],
                "criterion_file": criterion.get("_source_file"),
                "judge_template": template,
                "status": "ok",
                "auto_label": auto_label(result, template),
                "result": result,
                "judge": {
                    "provider": getattr(client, "provider_name", getattr(getattr(client, "profile", None), "provider_name", "LLM")),
                    "provider_type": getattr(getattr(client, "profile", None), "provider_type", None),
                    "model": client.model,
                    "reasoning_effort": getattr(client, "reasoning_effort", "none"),
                    "temperature": getattr(client, "temperature", None) if getattr(client, "reasoning_effort", "none") == "none" else None,
                    "prompt_version": PROMPT_VERSION,
                    "app_version": __version__,
                },
                "attempts": attempt + 1,
                "usage": usage,
                "condition": case.get("condition"),
                "product": case.get("product"),
                "metadata": case.get("metadata", {}),
                "error": None,
            }
        feedback = semantic_errors

    return _error_row(case, criterion, "SEMANTIC_VALIDATION_ERROR: " + "; ".join(feedback or []))


def _error_row(case: dict[str, Any], criterion: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "criterion_id": criterion.get("criterion_id"),
        "criterion_file": criterion.get("_source_file"),
        "judge_template": criterion.get("judge_template"),
        "status": "error",
        "auto_label": None,
        "result": None,
        "error": error,
        "condition": case.get("condition"),
        "product": case.get("product"),
        "metadata": case.get("metadata", {}),
    }


def run_batch(*, client: "LLMClient", input_path: Path, criteria_dir: Path, output_path: Path, semantic_retries: int = 1, overwrite: bool = False, limit: int | None = None) -> tuple[int, int]:
    criteria = load_criteria(criteria_dir)
    cases = read_jsonl(input_path)
    errors = dry_run(cases, criteria)
    if errors:
        raise ValueError("Input validation failed:\n" + "\n".join(f"- {e}" for e in errors))

    if overwrite and output_path.exists():
        output_path.unlink()
    done = set() if overwrite else _completed_ids(output_path)
    queue = [c for c in cases if c["case_id"] not in done]
    if limit is not None:
        queue = queue[:limit]

    ok = failed = 0
    for i, case in enumerate(queue, 1):
        row = judge_case(client, criteria[case["criterion_id"]], case, semantic_retries)
        _write_row(output_path, row)
        ok += row["status"] == "ok"
        failed += row["status"] != "ok"
        print(f"[{i}/{len(queue)}] {case['case_id']} -> {row['status']}" + (f" / {row['auto_label']}" if row['status'] == 'ok' else ''))
    return int(ok), int(failed)
