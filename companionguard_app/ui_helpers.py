from __future__ import annotations

from typing import Any

import streamlit as st

from .collector_storage import resolve_evidence_path
from .display_labels import (
    CONDITION_LABELS,
    PHASE_LABELS,
    RISK_LABEL_TEXT,
    VALIDITY_LABEL_TEXT,
    condition_label,
    criterion_label,
    phase_label,
    turn_label,
)


def zh_en(zh: str, en: str) -> str:
    return f"{zh} / {en}"


def render_evidence_files(
    files: list[str] | None,
    *,
    project_root,
    key_prefix: str,
    show_metadata: bool = True,
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
                st.image(str(resolved), caption=f"截图 {index + 1}", use_container_width=True)
                st.download_button(
                    "下载截图",
                    data=resolved.read_bytes(),
                    file_name=resolved.name,
                    mime="image/*",
                    key=f"{key_prefix}::{index}::{stored_path}",
                )
    if show_metadata:
        with st.expander("文件路径 / Technical metadata", expanded=False):
            st.code("\n".join(str(path) for path in files), language=None)


def render_case_validity(case_validity: str | None, *, title: str = "案例有效性 / Case Validity") -> None:
    value = case_validity or "REVIEW"
    zh, description = VALIDITY_LABEL_TEXT.get(value, (value, ""))
    if value == "VALID":
        st.success(f"{title}：`{value}` · {zh} — {description}")
    elif value == "INVALID":
        st.warning(f"{title}：`{value}` · {zh} — {description}")
    else:
        st.info(f"{title}：`{value}` · {zh} — {description}")


def render_condition_banner(
    condition: str | None,
    *,
    template: str | None = None,
    first_turn: bool = True,
) -> None:
    if first_turn:
        st.info("操作提示：请先在被测产品中新建对话或清空当前上下文，再发送本轮 Prompt。")
        st.caption("C0、C1、C2、不同测试项目以及不同重复测试次数均视为独立测试案例。")
    else:
        st.info("操作提示：请继续使用当前产品对话，不要重置上下文。")
    if condition in {"C0", "C1", "C2"}:
        st.caption(f"当前条件：{condition_label(condition, template=template)}")


def render_case_conversation(
    case: dict[str, Any] | None,
    *,
    project_root,
    key_prefix: str,
    expanded: bool = True,
) -> None:
    """Render the collected prompt/response context with linked screenshots."""
    if not case:
        st.warning("未找到该案例的原始采集记录。")
        return
    template = case.get("judge_template")
    condition = case.get("condition")
    technical_paths: list[str] = []
    with st.expander("原始用户 Prompt 与产品回复 / Original Conversation", expanded=expanded):
        trace = case.get("collection_trace") or []
        if trace:
            for index, step in enumerate(trace):
                st.markdown(
                    f"**{turn_label(step.get('prompt_turn'), condition=condition, template=template)}**"
                )
                st.code(step.get("prompt", ""), language=None)
                st.markdown(
                    f"**{step.get('response_turn') or '产品回复'}｜产品回复 / Product Response**"
                )
                st.code(step.get("response", ""), language=None)
                render_evidence_files(
                    step.get("evidence_files"),
                    project_root=project_root,
                    key_prefix=f"{key_prefix}::{index}",
                    show_metadata=False,
                )
                technical_paths.extend(step.get("evidence_files") or [])
                if index < len(trace) - 1:
                    st.divider()
        else:
            for message in case.get("conversation") or []:
                turn = message.get("turn") or message.get("role") or "对话"
                st.markdown(f"**{turn}**")
                st.code(message.get("content", ""), language=None)
    if technical_paths:
        with st.expander("截图文件路径 / Technical metadata", expanded=False):
            st.code("\n".join(str(path) for path in technical_paths), language=None)


def render_criterion_context(criterion: dict[str, Any]) -> None:
    """Render criterion context needed for an in-page human adjudication."""
    targets = criterion.get("target_behaviors") or {}
    st.markdown("#### 目标风险行为 / Target Behaviors")
    if targets:
        for code, item in targets.items():
            if isinstance(item, dict):
                st.markdown(f"**{code}｜{item.get('name', '')}**")
                if item.get("definition"):
                    st.caption(item["definition"])
            else:
                st.markdown(f"**{code}** · {item}")
    else:
        st.caption("当前测试项未配置目标风险行为。")

    with st.expander("非目标风险行为 / Non-target Behaviors", expanded=False):
        non_targets = criterion.get("non_target_behaviors") or {}
        if not non_targets:
            st.caption("当前测试项未配置非目标风险行为。")
        for code, item in non_targets.items():
            if isinstance(item, dict):
                st.markdown(f"**{code}｜{item.get('name', '')}**")
                if item.get("definition"):
                    st.caption(item["definition"])
            else:
                st.markdown(f"**{code}** · {item}")

    with st.expander("判定边界 / Boundary Rules", expanded=False):
        rules = criterion.get("frozen_boundary_rules") or []
        if not rules:
            st.caption("当前测试项未配置额外判定边界。")
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            st.markdown(
                f"**{rule.get('rule_id', 'Boundary')} · {rule.get('label', '—')}**"
            )
            if rule.get("example"):
                st.code(rule["example"], language=None)
            if rule.get("reason"):
                st.caption(rule["reason"])


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
    zh_label, summary = RISK_LABEL_TEXT.get(label, (label, ""))

    st.markdown(f"### 自动判定结论 / Auto Judgment：`{label}` · {zh_label}")
    if label == "FINDING":
        st.error(summary)
    elif label == "NO_FINDING":
        st.success(summary)
    else:
        st.warning(summary)

    cols = st.columns(4)
    cols[0].metric("产品 / Product", row.get("product") or "—")
    cols[1].metric("测试项目 / Criterion", criterion_label(row.get("criterion_id")))
    cols[2].metric("条件 / Condition", condition_label(row.get("condition"), template=row.get("judge_template")))
    cols[3].metric("阶段 / Phase", phase_label((row.get("metadata") or {}).get("phase") or row.get("phase")))

    checkpoint_fields: list[tuple[str, Any]] = []
    if result.get("pre_trigger_label") is not None:
        checkpoint_fields.append(("触发前 A4 / Pre-trigger", result.get("pre_trigger_label")))
    if result.get("post_trigger_label") is not None:
        checkpoint_fields.append(("触发后 A5 / Post-trigger", result.get("post_trigger_label")))
    if result.get("r1_label") is not None:
        checkpoint_fields.append(("第一轮 R1 / First round", result.get("r1_label")))
    if result.get("r2_label") is not None:
        checkpoint_fields.append(("第二轮 R2 / Second round", result.get("r2_label")))
    if result.get("l4_safeguard_response") is not None:
        checkpoint_fields.append(("L4 保护性回应", result.get("l4_safeguard_response")))
    if result.get("l5_safeguard_response") is not None:
        checkpoint_fields.append(("L5 保护性回应", result.get("l5_safeguard_response")))
    if result.get("finding_type") is not None:
        checkpoint_fields.append(("Finding Type", result.get("finding_type")))
    if result.get("transition") is not None:
        checkpoint_fields.append(("判定状态变化 / Transition", result.get("transition")))
    if result.get("relationship_transition") is not None:
        checkpoint_fields.append(("关系状态变化 / Relationship transition", result.get("relationship_transition")))

    if checkpoint_fields:
        st.markdown("#### 关键检查点 / Checkpoints")
        c = st.columns(min(4, len(checkpoint_fields)))
        for i, (name, value) in enumerate(checkpoint_fields):
            c[i % len(c)].metric(name, str(value))

    tcodes = result.get("matched_target_behaviors") or []
    if tcodes:
        st.markdown("#### 命中的目标风险行为 / Matched Target Behaviors")
        st.write(" · ".join(f"`{x}`" for x in tcodes))
    else:
        st.caption("未命中目标风险行为 / No target behavior matched")

    evidence = result.get("evidence") or []
    safeguard = result.get("safeguard_evidence") or []
    if evidence or safeguard:
        st.markdown("#### 判定证据 / Evidence")
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
                st.markdown(f"**{turn} · 保护性证据 / Safeguard evidence**")
                st.code(quote, language=None)

    rationale = result.get("rationale") or ""
    if rationale:
        with st.expander("详细判定理由 / Detailed rationale", expanded=not compact):
            st.markdown(rationale)

    with st.expander("完整 Judge JSON / Full Judge JSON", expanded=False):
        st.json(result)
