from __future__ import annotations

import json
import random
from typing import Any

import pandas as pd
import streamlit as st

from .cases import (
    build_case,
    build_conversation_template,
    conversation_json,
    flatten_single_turn_scenarios,
    parse_conversation_json,
)
from .adjudication import (
    SAMPLED_ADJUDICATION,
    adjudication_policy,
    build_sampling_plan,
    load_sampling_plan,
    review_case_ids,
    save_sampling_plan,
)
from .collector_storage import get_raw_case, load_raw_cases
from .config import OVERRIDE_REASONS
from .display_labels import HUMAN_VALIDITY_OPTIONS, criterion_label, human_validity_index, module_label, scenario_label
from .metrics import case_validity_counts, label_counts, module_finding_rates, overall_macro_finding_rate, robustness_gap, valid_case_rows
from .platform_ui import active_project, active_paths
from .llm_ui import llm_session_id, render_llm_profile_selector
from .service import criteria_index, run_batch_cases, run_single_case
from .ui_helpers import condition_label, phase_label, render_case_conversation, render_case_validity, render_criterion_context, render_judge_result
from .storage import (
    build_final_results,
    load_adjudications,
    load_final_results,
    load_judge_results,
    save_adjudication,
)
from .runtime_scope import RuntimeScope


@st.cache_data(show_spinner=False)
def get_criteria() -> dict[str, dict[str, Any]]:
    return criteria_index()


def _criterion_label(item: tuple[str, dict[str, Any]]) -> str:
    cid, obj = item
    return criterion_label(cid, obj)


def _judge_result_card(row: dict[str, Any]) -> None:
    render_judge_result(row, compact=False)


def _run_collected_batch_cases(
    *,
    project: dict[str, Any],
    paths,
    criteria: dict[str, dict[str, Any]],
    llm_profile,
) -> None:
    """Run Judge over selected COMPLETE raw cases without JSONL re-entry."""
    all_cases = sorted(load_raw_cases(paths.raw_cases), key=lambda case: str(case.get("case_id", "")))
    if not all_cases:
        st.info("当前项目还没有已完成的独立测试案例。请先进入“对话采集”。")
        return

    judged_ids = {
        row.get("case_id")
        for row in load_judge_results(paths.judge_results)
        if row.get("status") == "ok" and row.get("case_id")
    }
    pending = [case for case in all_cases if case.get("case_id") not in judged_ids]
    st.caption(f"当前项目共有 {len(all_cases)} 个已完成案例，其中 {len(pending)} 个尚未完成 Judge。")
    if not pending:
        st.success("当前没有尚未判定的已采集案例。")
        return

    labels = {
        case.get("case_id"): (
            f"{criterion_label(case.get('criterion_id'), criteria.get(case.get('criterion_id'), {}))} · "
            f"{case.get('product') or '—'} · {case.get('condition') or '单轮专项测试'}"
        )
        for case in pending
    }
    selected_ids = st.multiselect(
        "选择要判定的案例 / Cases to Judge",
        [case.get("case_id") for case in pending],
        default=[case.get("case_id") for case in pending],
        format_func=lambda case_id: labels.get(case_id, str(case_id)),
        key="collected_batch_case_ids",
    )
    selected_cases = [case for case in pending if case.get("case_id") in set(selected_ids)]
    st.dataframe(
        [
            {
                "案例编号": case.get("case_id"),
                "模块": module_label(criteria.get(case.get("criterion_id"), {}).get("module")),
                "测试项目": criterion_label(case.get("criterion_id"), criteria.get(case.get("criterion_id"), {})),
                "场景": scenario_label(
                    criteria.get(case.get("criterion_id"), {}),
                    case.get("scenario_id") or (case.get("metadata") or {}).get("scenario_id"),
                ),
                "条件": condition_label(case.get("condition"), template=criteria.get(case.get("criterion_id"), {}).get("judge_template")),
                "阶段": phase_label(case.get("phase") or (case.get("metadata") or {}).get("phase")),
            }
            for case in selected_cases
        ],
        use_container_width=True,
        hide_index=True,
    )
    if st.button("开始批量判定", type="primary", disabled=not selected_cases, key="run_collected_batch"):
        if not llm_profile:
            st.error("请先配置 Judge 模型。")
            return
        progress_bar = st.progress(0.0)
        status_box = st.empty()

        def progress(index: int, total: int, case_name: str) -> None:
            progress_bar.progress(index / max(total, 1))
            status_box.caption(f"正在判定：{index} / {total} · {case_name}")

        with st.spinner("正在运行 Judge..."):
            try:
                results = run_batch_cases(
                    cases=selected_cases,
                    criteria=criteria,
                    llm_profile=llm_profile,
                    progress=progress,
                    judge_path=paths.judge_results,
                    session_id=llm_session_id(),
                    project_id=project.get("project_id"),
                    scope=RuntimeScope.PUBLISHED,
                )
            except Exception as exc:
                st.error(str(exc))
                return
        ok = sum(row.get("status") == "ok" for row in results)
        st.success(f"批量判定完成：{ok} / {len(results)} 个案例成功。")


def _run_collected_single_case(*, project: dict[str, Any], paths, criteria: dict[str, dict[str, Any]], llm_profile) -> None:
    cases = load_raw_cases(paths.raw_cases)
    if not cases:
        st.info("当前项目还没有已完成的独立测试案例。请先进入“对话采集”，或切换到高级工具。")
        return

    cases = sorted(cases, key=lambda case: str(case.get("case_id", "")))
    labels = {
        case.get("case_id"): (
            f"{criterion_label(case.get('criterion_id'), criteria.get(case.get('criterion_id'), {}))} · "
            f"{case.get('product') or '—'} · "
            f"{condition_label(case.get('condition'), template=criteria.get(case.get('criterion_id'), {}).get('judge_template'))} · "
            f"{phase_label(case.get('phase') or (case.get('metadata') or {}).get('phase'))}"
        )
        for case in cases
    }
    selected_id = st.selectbox(
        "已采集案例 / Collected Case",
        [case.get("case_id") for case in cases],
        format_func=lambda value: labels.get(value, str(value)),
    )
    case = next(case for case in cases if case.get("case_id") == selected_id)
    metadata = case.get("metadata") or {}
    st.caption(
        f"产品：{case.get('product') or '—'} · 测试项目：{criterion_label(case.get('criterion_id'), criteria.get(case.get('criterion_id'), {}))} · "
        f"条件：{condition_label(case.get('condition'), template=criteria.get(case.get('criterion_id'), {}).get('judge_template'))} · "
        f"阶段：{phase_label(case.get('phase') or metadata.get('phase'))}"
    )
    render_case_conversation(
        case,
        project_root=paths.root,
        key_prefix=f"judge-collected::{selected_id}",
        expanded=True,
    )
    with st.expander("原始案例 JSON / Raw Case JSON", expanded=False):
        st.json(case)

    prior = [
        row for row in load_judge_results(paths.judge_results)
        if row.get("case_id") == selected_id and row.get("status") == "ok"
    ]
    if prior:
        st.info("该案例已有成功的 Judge 结果；为避免重复实验记录，当前不重复写入。")
        _judge_result_card(prior[-1])
        return

    if st.button("对已采集案例运行 Judge", type="primary", key="run_collected_case"):
        if not llm_profile:
            st.error("请先配置 Judge 模型。")
            return
        try:
            with st.spinner("正在运行冻结测试项目对应的 Judge..."):
                row = run_single_case(
                    case=case,
                    criteria=criteria,
                    llm_profile=llm_profile,
                    persist=True,
                    judge_path=paths.judge_results,
                    session_id=llm_session_id(),
                    project_id=project.get("project_id"),
                    scope=RuntimeScope.PUBLISHED,
                )
            st.session_state["last_judge_result"] = row
        except Exception as exc:
            st.error(str(exc))

    if st.session_state.get("last_judge_result", {}).get("case_id") == selected_id:
        _judge_result_card(st.session_state["last_judge_result"])


def _run_manual_single_case(*, project: dict[str, Any], paths, criteria: dict[str, dict[str, Any]], llm_profile) -> None:
    criterion_items = sorted(criteria.items())
    selected = st.selectbox(
        "测试项目 / Criterion",
        options=criterion_items,
        format_func=_criterion_label,
        key="manual_judge_criterion",
    )
    criterion_id, criterion = selected
    template = criterion["judge_template"]
    product = st.text_input("产品 / Product Model", value="", key="manual_judge_product")

    condition = None
    scenario_id = None
    category = None
    if template in ("core_l1_l5", "hr02_crisis"):
        conditions = ["C0"]
        if (criterion.get("pressure_variant") or {}).get("L5"):
            conditions.append("C1")
        conditions.append("C2")
        condition = st.selectbox("实验条件 / Condition", conditions, format_func=condition_label, key="manual_judge_condition")
        if "C1" not in conditions:
            st.caption("该criterion当前没有冻结的C1 pressure prompt，因此单条构造器不提供C1；批量输入仍可运行你已另行冻结的合法C1 case。")
    elif template == "mr_minor_relationship":
        scenarios = list((criterion.get("canonical_scenario") or {}).keys())
        scenario_id = st.selectbox("具体场景 / Scenario", scenarios, format_func=lambda sid: scenario_label(criterion, sid), key="manual_judge_scenario")
    else:
        scenarios = flatten_single_turn_scenarios(criterion)
        scenario_id = st.selectbox("具体场景 / Scenario", list(scenarios), format_func=lambda sid: scenario_label(criterion, sid), key="manual_judge_scenario")
        category = criterion_id if scenario_id == criterion_id else scenario_id.rsplit("-", 1)[0]

    template_key = f"conversation_template::{criterion_id}::{condition}::{scenario_id}"
    if st.session_state.get("conversation_template_key") != template_key:
        st.session_state["conversation_editor"] = conversation_json(
            build_conversation_template(criterion, condition=condition or "C0", scenario_id=scenario_id)
        )
        st.session_state["conversation_template_key"] = template_key

    st.caption("高级工具：把 `<PASTE_MODEL_RESPONSE>` 替换为真实模型输出。C2需要保留完整 A1–A5 上下文。")
    conversation_text = st.text_area("Conversation JSON / 对话 JSON", key="conversation_editor", height=360)
    default_case_id = f"{scenario_id or criterion_id}_{condition or 'default'}_{product or 'product'}_run1"
    case_id = st.text_input("案例编号 / Case ID", value=default_case_id, key="manual_judge_case_id")

    if st.button("运行手动测试 / Run Ad-hoc Judge", type="primary", key="run_manual_case"):
        if not llm_profile:
            st.error("请先配置 Dialogue Judge 模型。")
        elif not product.strip():
            st.error("请填写产品名称。")
        else:
            try:
                conversation = parse_conversation_json(conversation_text)
                case = build_case(
                    case_id=case_id.strip(), criterion_id=criterion_id, product=product.strip(),
                    condition=condition, conversation=conversation, category=category,
                    metadata={"source": "streamlit_single_ad_hoc"},
                )
                with st.spinner("正在运行冻结测试项目对应的 Judge..."):
                    row = run_single_case(
                        case=case, criteria=criteria, llm_profile=llm_profile, persist=True,
                        judge_path=paths.judge_results, session_id=llm_session_id(),
                        project_id=project.get("project_id"),
                        scope=RuntimeScope.PUBLISHED,
                    )
                st.session_state["last_judge_result"] = row
            except Exception as exc:
                st.error(str(exc))

    if st.session_state.get("last_judge_result"):
        _judge_result_card(st.session_state["last_judge_result"])


def _run_uploaded_batch_cases(
    *,
    project: dict[str, Any],
    paths,
    criteria: dict[str, dict[str, Any]],
    llm_profile,
) -> None:
    uploaded = st.file_uploader("上传 JSONL / Upload JSONL", type=["jsonl", "json"], key="advanced_judge_jsonl")
    if uploaded is None:
        st.caption("仅在需要处理项目外的 ad-hoc 数据时使用。项目内已采集案例请使用上面的批量入口。")
        return
    try:
        raw = uploaded.getvalue().decode("utf-8")
        cases = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        st.error(f"JSONL 读取失败：{exc}")
        return
    st.caption(f"已读取 {len(cases)} 个案例。")
    if cases:
        st.dataframe(
            [
                {
                    "案例编号": case.get("case_id"),
                    "测试项目": criterion_label(case.get("criterion_id"), criteria.get(case.get("criterion_id"), {})),
                    "条件": condition_label(case.get("condition"), template=criteria.get(case.get("criterion_id"), {}).get("judge_template")),
                }
                for case in cases
            ],
            use_container_width=True,
            hide_index=True,
        )
    if st.button("开始判定上传数据", type="primary", disabled=not cases, key="run_uploaded_batch"):
        if not llm_profile:
            st.error("请先配置 Judge 模型。")
            return
        with st.spinner("正在运行 Judge..."):
            try:
                results = run_batch_cases(
                    cases=cases,
                    criteria=criteria,
                    llm_profile=llm_profile,
                    judge_path=paths.judge_results,
                    session_id=llm_session_id(),
                    project_id=project.get("project_id"),
                    scope=RuntimeScope.PUBLISHED,
                )
            except Exception as exc:
                st.error(str(exc))
                return
        ok = sum(row.get("status") == "ok" for row in results)
        st.success(f"上传数据判定完成：{ok} / {len(results)} 个案例成功。")


def run_test_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    st.caption(f"当前项目：{project.get('project_name')}（{project.get('project_id')}）")
    st.info("主要工作流：直接读取当前项目已完成的 raw case，运行冻结 criterion 对应的 Judge；无需再次粘贴模型回复。")
    criteria = get_criteria()
    llm_profile = render_llm_profile_selector("judge", key_prefix="run_test_judge")

    single_tab, batch_tab, advanced_tab = st.tabs([
        "判定单个案例",
        "批量判定已完成案例",
        "高级工具｜手动输入测试",
    ])

    with single_tab:
        _run_collected_single_case(project=project, paths=paths, criteria=criteria, llm_profile=llm_profile)

    with batch_tab:
        _run_collected_batch_cases(project=project, paths=paths, criteria=criteria, llm_profile=llm_profile)

    with advanced_tab:
        st.caption("普通流程不需要使用这里。只有没有对应 raw case、需要临时构造测试时，才使用手动输入。")
        with st.expander("手动输入 Conversation JSON / Manual Conversation JSON", expanded=False):
            _run_manual_single_case(project=project, paths=paths, criteria=criteria, llm_profile=llm_profile)
        with st.expander("上传外部 JSONL / Upload External JSONL", expanded=False):
            _run_uploaded_batch_cases(project=project, paths=paths, criteria=criteria, llm_profile=llm_profile)


def human_review_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    st.caption(f"当前项目：{project.get('project_name')}（{project.get('project_id')}）")
    criteria = get_criteria()
    latest_judges: dict[str, dict[str, Any]] = {}
    for result in load_judge_results(paths.judge_results):
        if result.get("status") == "ok" and result.get("case_id"):
            latest_judges[result["case_id"]] = result
    judge_rows = [latest_judges[case_id] for case_id in sorted(latest_judges)]
    adjudicated = {r["case_id"]: r for r in load_adjudications(paths.adjudication)}

    if not judge_rows:
        st.info("还没有可复核的 Judge 结果。请先在“LLM 判定”中完成至少一个案例。")
        return

    policy = adjudication_policy(project)
    if project.get("mode") == "BENCHMARK" and policy == SAMPLED_ADJUDICATION:
        st.info("本项目使用预注册抽样人工复核：FORMAL 案例由 Judge 全量判定，抽样案例进入人工复核；风险标签或案例有效性为 REVIEW 的案例强制复核。")
        sampling_plan = load_sampling_plan(paths.adjudication_sampling)
        if sampling_plan is None:
            preview_plan = build_sampling_plan(judge_rows=judge_rows, project=project)
            st.warning("抽样方案尚未冻结。请先检查候选数量，再冻结方案；冻结后案例编号、比例、分层维度和随机种子均不再改变。")
            st.write(
                f"预计人工复核：{len(preview_plan['selected_case_ids'])} / "
                f"{preview_plan['formal_judge_case_count']} 个 FORMAL case；"
                f"其中强制复核 {len(preview_plan['forced_case_ids'])} 个。"
            )
            if preview_plan["selected_case_ids"]:
                st.dataframe(
                    [{"case_id": case_id, "forced": case_id in preview_plan["forced_case_ids"]} for case_id in preview_plan["selected_case_ids"]],
                    use_container_width=True,
                    hide_index=True,
                )
            if st.button(
                "冻结抽样方案 / Freeze Sampling Plan",
                type="primary",
                disabled=preview_plan["formal_judge_case_count"] == 0,
            ):
                try:
                    save_sampling_plan(preview_plan, paths.adjudication_sampling, scope=RuntimeScope.PUBLISHED)
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success("抽样方案已冻结。")
                    st.rerun()
            if preview_plan["formal_judge_case_count"] == 0:
                st.caption("当前还没有成功的 FORMAL Judge 结果；完成 FORMAL Judge 后再冻结抽样方案。")
        else:
            st.caption(
                f"Sampling plan frozen · {sampling_plan.get('sampling_method')} · "
                f"rate={sampling_plan.get('sample_rate')} · seed={sampling_plan.get('random_seed')} · "
                f"selected={len(sampling_plan.get('selected_case_ids') or [])}"
            )
        review_ids = review_case_ids(judge_rows=judge_rows, project=project, sampling_plan=sampling_plan)
        pending = [
            r for r in judge_rows
            if r.get("case_id") in review_ids
            and (
                r.get("case_id") not in adjudicated
                or not adjudicated.get(r.get("case_id"), {}).get("final_case_validity")
                and not adjudicated.get(r.get("case_id"), {}).get("case_validity")
            )
        ]
        mode = st.radio("显示", ["待复核", "已纳入方案"], horizontal=True)
        candidates = pending if mode == "待复核" else [r for r in judge_rows if r.get("case_id") in review_ids]
    elif project.get("mode") == "BENCHMARK":
        st.info("本项目使用全量人工复核：每个 FORMAL 案例都需要人工确认风险标签。案例有效性正常情况下自动为 VALID，只有异常筛查结果需要重点确认。")
        pending = [
            r for r in judge_rows
            if r.get("case_id") not in adjudicated
            or not adjudicated.get(r.get("case_id"), {}).get("final_case_validity")
            and not adjudicated.get(r.get("case_id"), {}).get("case_validity")
        ]
        mode = st.radio("显示", ["待复核", "全部"], horizontal=True)
        candidates = pending if mode == "待复核" else judge_rows
    else:
        pending = [
            r for r in judge_rows
            if r.get("case_id") not in adjudicated
            or not adjudicated.get(r.get("case_id"), {}).get("final_case_validity")
            and not adjudicated.get(r.get("case_id"), {}).get("case_validity")
        ]
        review_scope = st.radio("复核范围 / Review Scope", ["全部待复核", "随机抽样", "按测试项目分层抽样", "全部结果"], horizontal=True)
        if review_scope == "全部结果":
            candidates = judge_rows
        elif review_scope == "随机抽样":
            n = int(st.number_input("Sample size", min_value=1, max_value=max(len(pending), 1), value=min(10, max(len(pending), 1))))
            candidates = random.Random(42).sample(pending, min(n, len(pending))) if pending else []
        elif review_scope == "按测试项目分层抽样":
            per_criterion = int(st.number_input("每个测试项目的案例数", min_value=1, max_value=20, value=1))
            grouped = {}
            for row in pending:
                grouped.setdefault(row.get("criterion_id"), []).append(row)
            candidates = []
            rng = random.Random(42)
            for cid in sorted(grouped, key=str):
                group = grouped[cid]
                candidates.extend(rng.sample(group, min(per_criterion, len(group))))
        else:
            candidates = pending
    if not candidates:
        st.success("当前没有待复核case。")
        return

    selected_id = st.selectbox(
        "选择案例 / Select case",
        [r["case_id"] for r in candidates],
        key="human_review_case_selector",
    )
    row = next(r for r in candidates if r["case_id"] == selected_id)
    criterion = criteria.get(row.get("criterion_id"), {})
    raw_case = get_raw_case(selected_id, paths.raw_cases)
    if raw_case:
        raw_case = dict(raw_case)
        raw_case.setdefault("judge_template", criterion.get("judge_template"))
        raw_case.setdefault("condition", row.get("condition"))
    st.subheader(module_label(criterion.get("module")))
    st.markdown(f"### {criterion_label(row.get('criterion_id'), criterion)}")
    st.caption("请先查看完整对话、判定标准与 LLM Judge 结果，再分别确认风险标签和案例有效性。")
    render_case_conversation(
        raw_case,
        project_root=paths.root,
        key_prefix=f"human-review::{selected_id}",
        expanded=True,
    )
    render_criterion_context(criterion)
    render_judge_result(row, compact=True)
    auto_case_validity = row.get("auto_case_validity") or "VALID"
    prior = adjudicated.get(selected_id, {})
    render_case_validity(auto_case_validity, title="自动有效性筛查 / Auto Validity Screening")
    if prior.get("final_case_validity") or prior.get("case_validity"):
        render_case_validity(prior.get("final_case_validity") or prior.get("case_validity"), title="最终案例有效性 / Final Case Validity")

    auto = row.get("auto_label", "NO_FINDING")
    default_label = prior.get("human_label") or auto
    labels = ["FINDING", "NO_FINDING", "REVIEW"]
    saved_validity = prior.get("final_case_validity") or prior.get("case_validity")
    validity_options = HUMAN_VALIDITY_OPTIONS
    validity_index = human_validity_index(saved_validity, auto_case_validity)

    with st.form(f"adjudication_form::{selected_id}"):
        human_label = st.selectbox(
            "人工风险标签 / Human Risk Label",
            labels,
            index=labels.index(default_label) if default_label in labels else 0,
            key=f"human_label::{selected_id}",
        )
        override_reason = ""
        if human_label != auto:
            override_reason = st.selectbox(
                "人工改判原因 / Override Reason",
                OVERRIDE_REASONS,
                help="人工改判表示人工标签与 LLM 自动标签不同；这里记录改判原因，不改变冻结风险标签定义。",
                key=f"override_reason::{selected_id}",
            )
        case_validity = st.selectbox(
            "案例有效性 / Case Validity",
            validity_options,
            index=validity_index,
            format_func=lambda value: {"VALID": "有效 / VALID", "INVALID": "无效 / INVALID"}[value],
            help="案例有效性独立于 FINDING / NO_FINDING / REVIEW 风险标签。无效案例不进入正式风险指标，但会保留审计记录。",
            key=f"case_validity::{selected_id}",
        )
        if case_validity == "INVALID":
            validity_note = st.text_area(
                "无效说明（可选） / Invalidity Note (optional)",
                value=prior.get("validity_note", ""),
                key=f"validity_note::{selected_id}",
                help="可简要说明空答、系统错误、明显跑题、采集错误或上下文污染等情况；不使用预设原因枚举。",
            )
        else:
            st.caption("有效案例无需填写无效原因或说明。")
            validity_note = ""
        review_note = st.text_area(
            "人工复核备注（可选） / Review Note (optional)",
            value=prior.get("review_note", ""),
            key=f"review_note::{selected_id}",
        )
        submitted = st.form_submit_button("保存人工复核 / Save Adjudication", type="primary")

    if submitted:
        if case_validity not in validity_options:
            st.error("请明确选择案例有效性：有效或无效。")
            return
        try:
            save_adjudication(
                case_id=selected_id,
                auto_label=auto,
                human_label=human_label,
                override_reason=override_reason,
                review_note=review_note,
                case_validity=case_validity,
                auto_case_validity=auto_case_validity,
                final_case_validity=case_validity,
                validity_reason="",
                validity_note=validity_note,
                path=paths.adjudication,
                scope=RuntimeScope.PUBLISHED,
            )
            build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results, policy=policy, scope=RuntimeScope.PUBLISHED)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("已保存人工复核，并更新 data/final_results.csv。")
            st.rerun()

def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _pp(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.1f} pp"


def results_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    st.caption(f"当前项目：{project.get('project_name')}（{project.get('project_id')}）")
    criteria = get_criteria()
    rows = load_final_results(paths.final_results)
    if not rows:
        st.info("还没有最终结果。请先完成至少一个案例的人工复核。")
        return

    df = pd.DataFrame(rows)
    if "phase" not in df.columns:
        df["phase"] = ""
    formal_all = df[df["phase"] == "FORMAL"].copy()
    formal = pd.DataFrame(valid_case_rows(formal_all.to_dict("records")))
    validity = case_validity_counts(formal_all.to_dict("records"))
    if formal.empty:
        st.info("当前没有阶段为 FORMAL 的有效分析结果。SMOKE、CALIBRATION 以及没有阶段记录的旧数据不会进入正式指标。")
        if not formal_all.empty:
            st.warning(f"FORMAL 记录存在，但没有 VALID case。INVALID: {validity['INVALID']}；REVIEW: {validity['REVIEW']}。")
        with st.expander("排除项与非正式测试记录 / Excluded or non-formal records"):
            st.dataframe(df, use_container_width=True, hide_index=True)
        return

    st.caption("正式分析只纳入阶段为 FORMAL 且案例有效性为 VALID 的记录；INVALID/REVIEW 保留在审计数据中。")
    if validity["INVALID"] or validity["REVIEW"]:
        st.info(f"有效性排除：INVALID {validity['INVALID']}；REVIEW {validity['REVIEW']}。这些案例保留在 final_results.csv 和审计视图中。")
    st.sidebar.markdown("### 结果筛选 / Results Filters")
    products = sorted(x for x in formal["product"].dropna().unique() if x)
    modules = sorted(x for x in formal["module"].dropna().unique() if x)
    conditions = sorted(x for x in formal["condition"].dropna().unique() if x)
    selected_products = st.sidebar.multiselect("产品 / Product", products, default=products)
    selected_modules = st.sidebar.multiselect("模块 / Module", modules, default=modules, format_func=module_label)
    selected_conditions = st.sidebar.multiselect("条件 / Condition", conditions, default=conditions, format_func=condition_label)

    filtered = formal.copy()
    if selected_products:
        filtered = filtered[filtered["product"].isin(selected_products)]
    if selected_modules:
        filtered = filtered[filtered["module"].isin(selected_modules)]
    if selected_conditions:
        filtered = filtered[filtered["condition"].isin(selected_conditions)]
    filtered_rows = filtered.to_dict("records")

    counts = label_counts(filtered_rows)
    macro = overall_macro_finding_rate(filtered_rows)
    pressure = robustness_gap(filtered_rows, "C1")
    multiturn = robustness_gap(filtered_rows, "C2")

    c1, c2, c3, c4 = st.columns(4)
    reviewed_count = sum((row.get("adjudication_status") or "REVIEWED") == "REVIEWED" for row in filtered_rows)
    c1.metric("正式分析案例", len(filtered_rows))
    c2.metric("风险发现", counts["FINDING"])
    c3.metric("总体宏平均风险发现率", _pct(macro))
    c4.metric("待复核", counts["REVIEW"])
    st.caption(f"分析标签：已人工复核 {reviewed_count}；未人工复核 {len(filtered_rows) - reviewed_count}。未复核案例使用自动标签，不伪造 human_label。")
    st.caption("总体宏平均风险发现率仅在五个冻结模块都有 FORMAL 结果时显示。")

    r1, r2 = st.columns(2)
    r1.metric("压力条件风险发现率差值（C1−C0）", _pp(pressure))
    r2.metric("多轮条件风险发现率差值（C2−C0）", _pp(multiturn))

    module_rates = module_finding_rates(filtered_rows)
    if module_rates:
        st.subheader("模块风险发现率 / Module Finding Rate")
        chart_df = pd.DataFrame([
            {
                "模块": module_label(module),
                "风险发现率": rate,
            }
            for module, rate in module_rates.items()
        ]).set_index("模块")
        st.bar_chart(chart_df)

    st.subheader("风险发现矩阵 / Finding Matrix")
    display_matrix = []
    for row in filtered_rows:
        criterion = criteria.get(row.get("criterion_id"), {})
        display_matrix.append({
            "产品": row.get("product"),
            "模块": module_label(row.get("module")),
            "测试项目": criterion_label(row.get("criterion_id"), criterion),
            "场景": scenario_label(criterion, row.get("scenario_id")),
            "条件": condition_label(row.get("condition"), template=row.get("judge_template")),
            "重复次数": row.get("run_number"),
            "阶段": phase_label(row.get("phase")),
            "案例有效性": row.get("final_case_validity"),
            "自动风险标签": row.get("auto_label"),
            "分析标签": row.get("analysis_label"),
            "人工复核状态": row.get("adjudication_status"),
            "命中的目标风险行为": row.get("matched_target_behaviors"),
            "判定证据": row.get("evidence"),
            "人工改判原因": row.get("override_reason"),
        })
    st.dataframe(pd.DataFrame(display_matrix), use_container_width=True, hide_index=True)

    csv_bytes = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "下载筛选后的 FORMAL CSV",
        data=csv_bytes,
        file_name="companionguard_final_results_formal.csv",
        mime="text/csv",
    )

    nonformal = df[df["phase"] != "FORMAL"]
    if not nonformal.empty:
        with st.expander("非正式测试记录（不进入正式指标）"):
            st.dataframe(nonformal, use_container_width=True, hide_index=True)
    excluded_formal = formal_all[~formal_all["case_validity"].isin(["VALID"])]
    if not excluded_formal.empty:
        with st.expander("无效或待确认的 FORMAL 记录（不进入正式指标）"):
            st.dataframe(excluded_formal, use_container_width=True, hide_index=True)
