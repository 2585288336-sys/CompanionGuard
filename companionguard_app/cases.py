from __future__ import annotations

import json
from typing import Any


def flatten_single_turn_scenarios(criterion: dict[str, Any]) -> dict[str, str]:
    canonical = criterion.get("canonical_scenario", {})
    out: dict[str, str] = {}

    if "prompt" in canonical:
        out[criterion["criterion_id"]] = canonical["prompt"]
        return out

    for key, value in canonical.items():
        if not isinstance(value, dict):
            continue
        if "prompt" in value:
            out[key] = value["prompt"]
            continue
        tests = value.get("tests")
        if isinstance(tests, dict):
            for test_id, test in tests.items():
                if isinstance(test, dict) and test.get("prompt"):
                    out[test_id] = test["prompt"]
    return out


def build_conversation_template(
    criterion: dict[str, Any],
    *,
    condition: str = "C0",
    scenario_id: str | None = None,
) -> list[dict[str, str]]:
    template = criterion["judge_template"]
    canonical = criterion.get("canonical_scenario", {})

    if template in ("core_l1_l5", "hr02_crisis"):
        l5 = canonical.get("L5", "")
        if condition == "C1":
            pressure_l5 = (criterion.get("pressure_variant") or {}).get("L5")
            if not pressure_l5:
                raise ValueError("该criterion尚未配置冻结的C1 pressure prompt，不能把C0静默当作C1。")
            l5 = pressure_l5

        if condition == "C2":
            turns: list[dict[str, str]] = []
            for i in range(1, 6):
                user_text = canonical.get(f"L{i}", "")
                if i == 5:
                    user_text = l5
                turns.append({"role": "user", "turn": f"L{i}", "content": user_text})
                turns.append({"role": "assistant", "turn": f"A{i}", "content": "<PASTE_MODEL_RESPONSE>"})
            return turns

        return [
            {"role": "user", "turn": "L1", "content": canonical.get("L1", "")},
            {"role": "user", "turn": "L2", "content": canonical.get("L2", "")},
            {"role": "user", "turn": "L3", "content": canonical.get("L3", "")},
            {"role": "user", "turn": "L4", "content": canonical.get("L4", "")},
            {"role": "assistant", "turn": "A4", "content": "<PASTE_MODEL_RESPONSE>"},
            {"role": "user", "turn": "L5", "content": l5},
            {"role": "assistant", "turn": "A5", "content": "<PASTE_MODEL_RESPONSE>"},
        ]

    if template == "mr_minor_relationship":
        if not scenario_id:
            scenario_id = next(iter(canonical))
        scenario = canonical[scenario_id]
        return [
            {"role": "user", "turn": "R1", "content": scenario["R1"]},
            {"role": "assistant", "turn": "A_R1", "content": "<PASTE_MODEL_RESPONSE>"},
            {"role": "user", "turn": "R2", "content": scenario["R2"]},
            {"role": "assistant", "turn": "A_R2", "content": "<PASTE_MODEL_RESPONSE>"},
        ]

    if template == "single_turn_regulatory_content":
        scenarios = flatten_single_turn_scenarios(criterion)
        if not scenario_id:
            scenario_id = next(iter(scenarios))
        return [
            {"role": "user", "turn": "P1", "content": scenarios[scenario_id]},
            {"role": "assistant", "turn": "A1", "content": "<PASTE_MODEL_RESPONSE>"},
        ]

    raise ValueError(f"Unsupported judge_template: {template}")


def conversation_json(conversation: list[dict[str, str]]) -> str:
    return json.dumps(conversation, ensure_ascii=False, indent=2)


def parse_conversation_json(text: str) -> list[dict[str, str]]:
    value = json.loads(text)
    if not isinstance(value, list):
        raise ValueError("conversation JSON 必须是数组。")
    for i, turn in enumerate(value):
        if not isinstance(turn, dict):
            raise ValueError(f"第 {i + 1} 个turn不是object。")
        for field in ("role", "turn", "content"):
            if field not in turn:
                raise ValueError(f"第 {i + 1} 个turn缺少 {field}。")
        if turn["role"] not in ("user", "assistant"):
            raise ValueError(f"第 {i + 1} 个turn role必须是user/assistant。")
        if turn["content"] == "<PASTE_MODEL_RESPONSE>":
            raise ValueError(f"第 {i + 1} 个turn仍是占位符，请粘贴真实模型回复。")
    return value


def build_case(
    *,
    case_id: str,
    criterion_id: str,
    product: str,
    condition: str | None,
    conversation: list[dict[str, str]],
    category: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case = {
        "case_id": case_id,
        "criterion_id": criterion_id,
        "condition": condition,
        "product": product,
        "conversation": conversation,
        "metadata": metadata or {},
    }
    if category:
        case["category"] = category
    return case
