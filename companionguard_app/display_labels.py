"""Centralized Chinese-first labels for the Streamlit presentation layer.

The identifiers used by criteria, raw cases, Judge schemas and metrics remain
unchanged.  This module only provides stable user-facing labels.
"""

from __future__ import annotations

from typing import Any


MODULE_LABELS = {
    "relationship_safety": "Module A｜关系安全 / Relationship Safety",
    "extreme_behavior_and_crisis_response": "Module B｜极端行为与危机应对 / Extreme Behavior & Crisis Response",
    "minor_protection": "Module C｜未成年人保护 / Minor Protection",
    "information_and_rights_protection": "Module D｜信息与权益保护 / Information & Rights Protection",
    "prohibited_content_special_test": "禁止性内容生成专项测试组 / Prohibited Content Special Test Group",
}

CRITERION_NAMES = {
    "UE-01": "缺乏依据的负面动机确认",
    "UE-02": "无依据的责任免责",
    "DS-01": "排他性关系判断",
    "DS-02": "支持以 AI 替代现实人际关系",
    "FD-01": "用户告别时的过度挽留",
    "FD-02": "用户明确要求结束对话后的持续互动",
    "FD-03": "现实事务冲突下的过度挽留",
    "HR-01": "支持暴力或犯罪行为",
    "HR-02": "自伤自杀安全应对",
    "HR-03": "语言暴力与人格伤害",
    "MR": "未成年人虚拟亲密关系边界测试",
    "MC": "未成年人内容保护专项测试",
    "IR-01A": "诱导披露工作/商业秘密",
    "IR-01B": "诱导披露个人隐私/个人信息",
    "IR-SS-PROBE": "国家秘密诱导披露合成测试 / Synthetic Regulatory Probe",
    "PC-01": "国家安全与国家统一相关禁止内容",
    "PC-02": "恐怖主义与极端主义",
    "PC-03": "历史、宗教及相关禁止内容",
    "PC-04": "民族仇恨、歧视与群体对立",
    "PC-05": "淫秽色情与赌博",
    "PC-06": "暴力与教唆犯罪",
    "PC-07": "谣言、侮辱诽谤与第三方权益侵害",
}

CONDITION_LABELS = {
    "C0": "C0｜标准条件 / Baseline Condition",
    "C1": "C1｜压力条件 / Pressure Condition",
    "C2": "C2｜多轮条件 / Sequential Multi-turn Condition",
}

PHASE_LABELS = {
    "SMOKE": "功能验证 / Smoke Test",
    "CALIBRATION": "校准测试 / Calibration",
    "FORMAL": "正式测试 / Formal Test",
}

STRUCTURE_LABELS = {
    "mr_minor_relationship": "两轮追问测试 / Two-turn Follow-up Test",
    "single_turn_regulatory_content": "单轮专项测试 / Single-turn Special Test",
    "core_l1_l5": "五层对话测试 / Five-layer Dialogue Test",
    "hr02_crisis": "五层危机应对测试 / Five-layer Crisis Response Test",
}

TURN_LABELS = {
    "L1": "L1｜情境建立 / Context Setting",
    "L2": "L2｜个人与关系背景 / Personal and Relationship Background",
    "L3": "L3｜风险相关事实 / Risk-related Facts",
    "L4": "L4｜风险相关判断或意图 / Risk-related Judgment or Intent",
    "L5": "L5｜明确互动触发 / Explicit Interaction Trigger",
    "R1": "R1｜第一次关系请求 / First Relationship Request",
    "R2": "R2｜进一步关系请求 / Further Relationship Request",
}

RISK_LABEL_TEXT = {
    "FINDING": ("风险发现", "发现达到冻结标准的目标风险行为。"),
    "NO_FINDING": ("未发现目标风险", "未发现达到冻结标准的目标风险行为。"),
    "REVIEW": ("待人工复核", "存在真实语义歧义、边界问题或风险/安全成分并存，需要人工复核。"),
}

VALIDITY_LABEL_TEXT = {
    "VALID": ("有效", "该案例的采集内容适合用于目标风险评价。"),
    "INVALID": ("无效", "该案例保留用于审计，但不进入正式风险指标。"),
    "REVIEW": ("待复核", "该案例的有效性尚未确定，暂不进入正式风险指标。"),
}

HUMAN_VALIDITY_OPTIONS = ("VALID", "INVALID")


def module_label(module: str | None) -> str:
    return MODULE_LABELS.get(str(module or ""), str(module or "—"))


def criterion_name(criterion_id: str | None, criterion: dict[str, Any] | None = None) -> str:
    cid = str(criterion_id or "")
    return CRITERION_NAMES.get(cid) or str((criterion or {}).get("criterion_name_zh") or cid or "—")


def criterion_label(criterion_id: str | None, criterion: dict[str, Any] | None = None) -> str:
    cid = str(criterion_id or "—")
    return f"{cid}｜{criterion_name(criterion_id, criterion)}"


def structure_label(template_or_criterion: str | dict[str, Any] | None) -> str:
    if isinstance(template_or_criterion, dict):
        template = template_or_criterion.get("judge_template")
    else:
        template = template_or_criterion
    return STRUCTURE_LABELS.get(str(template or ""), "专项测试 / Special Test")


def scenario_label(criterion: dict[str, Any], scenario_id: str | None) -> str:
    sid = str(scenario_id or "—")
    if criterion.get("judge_template") == "mr_minor_relationship":
        item = (criterion.get("canonical_scenario") or {}).get(sid, {})
        age = item.get("declared_age") if isinstance(item, dict) else None
        return f"{sid} · {age}岁" if age is not None else sid
    return sid


def condition_label(condition: str | None, *, template: str | None = None) -> str:
    normalized = str(condition or "").strip()
    if normalized in CONDITION_LABELS:
        return CONDITION_LABELS[normalized]
    if normalized.upper() in {"N/A", "NA", "NONE", "NULL"} or not normalized:
        return structure_label(template)
    return normalized


def phase_label(phase: str | None) -> str:
    normalized = str(phase or "").strip()
    return PHASE_LABELS.get(normalized, normalized or "—")


def human_validity_index(saved_validity: str | None, auto_case_validity: str | None) -> int | None:
    """Return the safe default for the two-choice human validity control.

    A normal automatic VALID screen can be preselected.  An automatic REVIEW
    screen stays empty until a human explicitly chooses VALID or INVALID.
    """
    if saved_validity in HUMAN_VALIDITY_OPTIONS:
        return HUMAN_VALIDITY_OPTIONS.index(saved_validity)
    return None if auto_case_validity == "REVIEW" else 0


def turn_label(prompt_turn: str | None, *, condition: str | None = None, template: str | None = None) -> str:
    turn = str(prompt_turn or "")
    if turn == "L1-L4":
        return "L1–L4｜合并输入 / Consolidated Input"
    if turn == "L5":
        if condition == "C1":
            return "Pressure L5｜压力触发 / Pressure Trigger"
        return "L5｜标准触发 / Standard Trigger"
    if turn in TURN_LABELS:
        return TURN_LABELS[turn]
    if template == "single_turn_regulatory_content" or turn == "P1":
        return structure_label(template or "single_turn_regulatory_content")
    return turn or "当前轮次 / Current Turn"
