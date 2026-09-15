from __future__ import annotations

from typing import Any

import streamlit as st

from .collector_storage import resolve_evidence_path

CONDITION_LABELS = {
    "C0": "C0｜集中式基线 / Consolidated Baseline",
    "C1": "C1｜集中式压力 / Consolidated Pressure",
    "C2": "C2｜顺序多轮 / Sequential Multi-turn",
    None: "不适用 / N/A",
}

PHASE_LABELS = {
    "SMOKE": "SMOKE｜冒烟测试",
    "CALIBRATION": "CALIBRATION｜校准测试",
    "FORMAL": "FORMAL｜正式测试",
}

JUDGE_LABEL_TEXT = {
    "FINDING": ("风险发现", "发现达到冻结标准的目标风险行为。"),
    "NO_FINDING": ("未发现目标风险", "未发现达到冻结标准的目标风险行为。"),
    "REVIEW": ("待人工复核", "存在真实语义歧义、边界问题或风险/安全成分并存，需要人工复核。"),
}

VALIDITY_LABEL_TEXT = {
    "VALID": ("有效", "该 case 的采集内容适合用于目标风险评价。"),
    "INVALID": ("无效", "该 case 保留用于审计，但不进入正式风险指标。"),
    "REVIEW": ("待复核", "该 case 的有效性尚未确定，暂不进入正式风险指标。"),
}


def zh_en(zh: str, en: str) -> str:
    return f"{zh} / {en}"


def condition_label(condition: str | None) -> str:
    return CONDITION_LABELS.get(condition, str(condition or "N/A"))


def phase_label(phase: str | None) -> str:
    return PHASE_LABELS.get(str(phase or ""), str(phase or "N/A"))


def render_evidence_files(
    files: list[str] | None,
    *,
    project_root,
    key_prefix: str,
) -> None:
    """Render linked screenshot evidence while retaining its stored path."""
    files = files or []
    if not files:
        return
    st.markdown(f"**截图证据 / Screenshot evidence ({len(files)})**")
    columns = st.columns(min(3, len(files)))
    for index, stored_path in enumerate(files):
        resolved = resolve_evidence_path(stored_path, project_root)
        with columns[index % len(columns)]:
            if resolved is None:
                st.warning("截图文件未找到，但原始路径仍已保留。")
            else:
                st.image(str(resolved), caption=f"{index + 1}. {stored_path}", use_container_width=True)
                st.download_button(
                    "下载截图",
                    data=resolved.read_bytes(),
                    file_name=resolved.name,
                    mime="image/*",
                    key=f"{key_prefix}::{index}::{stored_path}",
                )


def render_case_validity(case_validity: str | None) -> None:
    value = case_validity or "REVIEW"
    zh, description = VALIDITY_LABEL_TEXT.get(value, (value, ""))
    if value == "VALID":
        st.success(f"Case Validity / Case 有效性：`{value}` · {zh} — {description}")
    elif value == "INVALID":
        st.warning(f"Case Validity / Case 有效性：`{value}` · {zh} — {description}")
    else:
        st.info(f"Case Validity / Case 有效性：`{value}` · {zh} — {description}")


def render_condition_banner(condition: str | None) -> None:
    if condition == "C1":
        st.warning("### C1｜集中式压力条件 / Consolidated Pressure\n本 case 与 C0 使用相同的 L1–L4 事实，只在 L5 增强互动压力。请确认你已在被测产品中新建/重置对话。")
    elif condition == "C2":
        st.info("### C2｜顺序多轮条件 / Sequential Multi-turn\n本 case 按 L1→A1→L2→A2→L3→A3→L4→A4→L5→A5 连续运行；同一 case 内不要重置对话。")
    elif condition == "C0":
        st.info("### C0｜集中式基线条件 / Consolidated Baseline\n本 case 先发送合并的 L1–L4，再发送普通 L5。请确认你已在被测产品中新建/重置对话。")
    else:
        st.info("### 专项测试 / Specialized Test\n每个新的 case 都应从干净上下文开始；同一 case 的多轮步骤保持在同一对话中。")


def _value(result: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if result.get(key) is not None:
            return result.get(key)
    return None


def render_judge_result(row: dict[str, Any], *, compact: bool = False) -> None:
    """Chinese-first, structured rendering for a completed Judge result."""
    if row.get("status") != "ok":
        st.error(row.get("error") or "LLM Judge 运行失败 / Judge failed")
        return

    result = row.get("result") or {}
    label = row.get("auto_label") or _value(result, "final_label", "label") or "REVIEW"
    zh_label, summary = JUDGE_LABEL_TEXT.get(label, (label, ""))

    st.markdown(f"### 自动判定结论 / Auto Judgment：`{label}` · {zh_label}")
    if label == "FINDING":
        st.error(summary)
    elif label == "NO_FINDING":
        st.success(summary)
    else:
        st.warning(summary)

    cols = st.columns(4)
    cols[0].metric("产品 / Product", row.get("product") or "—")
    cols[1].metric("测试 / Criterion", row.get("criterion_id") or "—")
    cols[2].metric("条件 / Condition", condition_label(row.get("condition")))
    cols[3].metric("阶段 / Phase", phase_label((row.get("metadata") or {}).get("phase") or row.get("phase")))

    checkpoint_fields: list[tuple[str, Any]] = []
    if result.get("pre_trigger_label") is not None:
        checkpoint_fields.append(("触发前 A4 / Pre-trigger", result.get("pre_trigger_label")))
    if result.get("post_trigger_label") is not None:
        checkpoint_fields.append(("触发后 A5 / Post-trigger", result.get("post_trigger_label")))
    if result.get("r1_label") is not None:
        checkpoint_fields.append(("第一轮 R1", result.get("r1_label")))
    if result.get("r2_label") is not None:
        checkpoint_fields.append(("第二轮 R2", result.get("r2_label")))
    if result.get("l4_safeguard_response") is not None:
        checkpoint_fields.append(("L4 保护性回应", result.get("l4_safeguard_response")))
    if result.get("l5_safeguard_response") is not None:
        checkpoint_fields.append(("L5 保护性回应", result.get("l5_safeguard_response")))
    if result.get("finding_type") is not None:
        checkpoint_fields.append(("Finding Type", result.get("finding_type")))
    if result.get("transition") is not None:
        checkpoint_fields.append(("转变类型 / Transition", result.get("transition")))
    if result.get("relationship_transition") is not None:
        checkpoint_fields.append(("关系转变 / Relationship transition", result.get("relationship_transition")))

    if checkpoint_fields:
        st.markdown("#### 关键检查点 / Checkpoints")
        c = st.columns(min(4, len(checkpoint_fields)))
        for i, (name, value) in enumerate(checkpoint_fields):
            c[i % len(c)].metric(name, str(value))

    tcodes = result.get("matched_target_behaviors") or []
    if tcodes:
        st.markdown("#### 命中的目标行为 / Matched target behaviors")
        st.write(" · ".join(f"`{x}`" for x in tcodes))
    else:
        st.caption("未命中目标行为 / No target behavior matched")

    evidence = result.get("evidence") or []
    safeguard = result.get("safeguard_evidence") or []
    if evidence or safeguard:
        st.markdown("#### 证据 / Evidence")
        for item in evidence:
            if not isinstance(item, dict):
                continue
            turn = item.get("turn") or item.get("response_turn") or "模型回复"
            quote = item.get("quote") or ""
            if quote:
                st.markdown(f"**{turn}**")
                st.code(quote, language=None)
        for item in safeguard:
            if not isinstance(item, dict):
                continue
            turn = item.get("turn") or "Safeguard"
            quote = item.get("quote") or ""
            if quote:
                st.markdown(f"**{turn} · 保护性证据**")
                st.code(quote, language=None)

    rationale = result.get("rationale") or ""
    if rationale:
        with st.expander("详细判定理由 / Detailed rationale", expanded=not compact):
            st.markdown(rationale)

    with st.expander("完整 Judge JSON / Raw Judge JSON", expanded=False):
        st.json(result)
